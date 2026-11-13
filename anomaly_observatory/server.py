"""Local-only dashboard, backed by the same acquisition and analysis functions as the CLI."""
import json
import math
import os
import re
import secrets
import shutil
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit

from . import core, ollama

MAX_BODY = 8 * 1024 * 1024
ID = re.compile(r'^[0-9a-f]{32}$')


def number(data, key, default, low, high, integer=False):
    raw = data.get(key, default)
    if isinstance(raw, bool):
        raise ValueError(f'{key} must be a number')
    value = float(raw)
    if not math.isfinite(value) or not low <= value <= high or (integer and value != int(value)):
        raise ValueError(f'{key} must be {"an integer " if integer else ""}between {low} and {high}')
    return int(value) if integer else value


class Workspace:
    def __init__(self, data_dir, private_dir):
        self.root = Path(data_dir).resolve()
        self.private = Path(private_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.private.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()

    def directory(self, run_id):
        if not isinstance(run_id, str) or not ID.fullmatch(run_id):
            raise ValueError('Invalid recording ID')
        path = self.root / run_id
        if not path.is_dir():
            raise ValueError('Recording not found')
        return path

    def metadata(self, run_id):
        return json.loads((self.directory(run_id) / 'run.json').read_text())

    def state(self):
        with self.lock:
            runs = [json.loads(p.read_text()) for p in self.root.glob('*/run.json')]
            plans = [json.loads(p.read_text()) for p in self.root.glob('plan-*.json')]
        return dict(runs=sorted(runs, key=lambda r: r['created'], reverse=True),
                    plans=sorted(plans, key=lambda p: p['created'], reverse=True),
                    cloud_configured=bool(os.environ.get('OLLAMA_API_KEY')))

    def create(self, data):
        kind = data.get('kind')
        if kind not in ('baseline', 'trial'):
            raise ValueError('Choose baseline or trial')
        label = data.get('label', '').strip()
        if not label or len(label) > 80:
            raise ValueError('Give the recording a name of 1–80 characters')
        source = data.get('source', 'simulate')
        if source not in ('simulate', 'import'):
            raise ValueError('Unknown source')
        run_id = uuid.uuid4().hex
        folder = self.root / run_id
        folder.mkdir()
        try:
            path = folder / 'recording.csv'
            if source == 'simulate':
                seconds = number(data, 'seconds', 30, 1, 300)
                rate = number(data, 'rate', 20, 1, 100, integer=True)
                seed = number(data, 'seed', 42, 0, 2**32-1, integer=True)
                injection = number(data, 'injection', 0, -100, 100)
                core.simulate(path, seconds, rate, seed, injection)
                provenance = 'SIMULATED'
            else:
                content = data.get('csv')
                if not isinstance(content, str) or len(content.encode()) > MAX_BODY:
                    raise ValueError('Upload a CSV smaller than 8 MB')
                path.write_text(content, encoding='utf-8')
                provenance = 'UNVERIFIED IMPORT'
            pairs = core.load_pairs(path)
            # Enforce finite scores too: extreme finite inputs can overflow RMS calculations.
            if not all(math.isfinite(value) for value in core.scores(path).values()):
                raise ValueError('Channel values exceed the supported numeric range')
            meta = dict(id=run_id, kind=kind, label=label, source=provenance,
                        created=datetime.now(timezone.utc).isoformat(), samples=len(pairs),
                        duration_s=pairs[-1]['A'][0]-pairs[0]['A'][0], sha256=core.digest(path))
            if kind == 'trial':
                baseline = self.directory(data.get('baseline_id'))
                base_meta = self.metadata(data.get('baseline_id'))
                if base_meta['kind'] != 'baseline' or not (baseline / 'protocol.json').exists():
                    raise ValueError('Freeze a baseline protocol before creating a trial')
                shutil.copyfile(baseline / 'protocol.json', folder / 'protocol.json')
                result = core.analyze(path, folder / 'protocol.json')
                core.save_new(folder / 'report.json', result)
                meta.update(baseline_id=base_meta['id'], baseline_label=base_meta['label'], report=result)
            core.save_new(folder / 'run.json', meta)
            return meta
        except Exception:
            shutil.rmtree(folder)
            raise

    def freeze(self, data):
        run_id = data.get('id')
        folder = self.directory(run_id)
        meta = self.metadata(run_id)
        if meta['kind'] != 'baseline':
            raise ValueError('Only baselines can have a frozen protocol')
        if (folder / 'protocol.json').exists():
            raise ValueError('This protocol is already frozen; create a new baseline to change the rule')
        core.preregister(folder / 'recording.csv', folder / 'protocol.json',
                         number(data, 'factor', 3, 1.01, 100))
        return self.protocol(run_id)

    def protocol(self, run_id):
        path = self.directory(run_id) / 'protocol.json'
        if not path.exists():
            return None
        return dict(spec=json.loads(path.read_text()), sha256=core.digest(path))

    def recording(self, run_id):
        meta = self.metadata(run_id)
        pairs = core.load_pairs(self.directory(run_id) / 'recording.csv')
        # Visualization only is decimated. All raw samples enter the analysis and download.
        stride = max(1, math.ceil(len(pairs) / 600))
        indices = sorted(set(range(0, len(pairs), stride)) | {len(pairs)-1})
        return dict(meta=meta, protocol=self.protocol(run_id), chart=[
            dict(t=pairs[i]['A'][0], a=pairs[i]['A'][1], b=pairs[i]['B'][1]) for i in indices],
            plotted_samples=len(indices), total_samples=len(pairs))

    def plan(self, data):
        plan_id = uuid.uuid4().hex
        public = self.root / f'plan-{plan_id}-public.tmp'
        private = self.private / f'operator-key-{plan_id}.json'
        core.plan(public, private, number(data, 'repeats', 4, 1, 100, integer=True))
        value = dict(id=plan_id, created=datetime.now(timezone.utc).isoformat(),
                     runs=json.loads(public.read_text()), key_filename=private.name)
        core.save_new(self.root / f'plan-{plan_id}.json', value)
        public.unlink()
        return value

    def demo(self):
        baseline = self.create(dict(kind='baseline', source='simulate', label='Demo · quiet baseline', seed=42))
        self.freeze(dict(id=baseline['id'], factor=3))
        return self.create(dict(kind='trial', source='simulate', label='Demo · magnetic offset', seed=91,
                                injection=1, baseline_id=baseline['id']))


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, workspace):
        self.workspace = workspace
        self.token = secrets.token_urlsafe(32)
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Do not log upload data, AI requests or authorization headers.
        pass

    def trusted(self):
        port = self.server.server_port
        allowed = {f'127.0.0.1:{port}', f'localhost:{port}'}
        host = self.headers.get('Host', '')
        if host not in allowed:
            raise ValueError('Use the dashboard through its printed localhost URL')
        origin = self.headers.get('Origin')
        if origin and origin not in {f'http://{h}' for h in allowed}:
            raise ValueError('Cross-origin requests are not accepted')

    def reply(self, status, content, content_type='application/json; charset=utf-8', attachment=None):
        if not isinstance(content, bytes):
            content = json.dumps(content, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if attachment:
            self.send_header('Content-Disposition', f'attachment; filename="{attachment}"')
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        try:
            self.trusted()
            path = urlsplit(self.path).path
            static = {'/': ('index.html', 'text/html; charset=utf-8'),
                      '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                      '/style.css': ('style.css', 'text/css; charset=utf-8')}
            if path in static:
                name, mime = static[path]
                return self.reply(200, files('anomaly_observatory').joinpath('web', name).read_bytes(), mime)
            store = self.server.workspace
            if path == '/api/state':
                value = store.state()
                for run in value['runs']:
                    run['protocol'] = store.protocol(run['id'])
                return self.reply(200, dict(**value, csrf=self.server.token))
            match = re.fullmatch(r'/api/runs/([0-9a-f]{32})(?:/(csv|report|protocol))?', path)
            if match:
                run_id, download = match.groups()
                if download:
                    name, mime = {'csv': ('recording.csv', 'text/csv; charset=utf-8'),
                                  'report': ('report.json', 'application/json'),
                                  'protocol': ('protocol.json', 'application/json')}[download]
                    file = store.directory(run_id) / name
                    if not file.exists():
                        return self.reply(404, dict(error='File not available for this recording'))
                    return self.reply(200, file.read_bytes(), mime, f'{run_id}-{name}')
                return self.reply(200, store.recording(run_id))
            return self.reply(404, dict(error='Not found'))
        except (ValueError, OSError, KeyError, TypeError, OverflowError) as exc:
            self.reply(400, dict(error=str(exc)))

    def do_POST(self):
        try:
            self.trusted()
            if not secrets.compare_digest(self.headers.get('X-Observatory-Token', ''), self.server.token):
                return self.reply(403, dict(error='Refresh the dashboard before making changes'))
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.reply(415, dict(error='Expected application/json'))
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > MAX_BODY:
                return self.reply(413, dict(error='Request must be between 1 byte and 8 MB'))
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object')
            store = self.server.workspace
            path = urlsplit(self.path).path
            if path == '/api/models':
                return self.reply(200, ollama.models())
            if path == '/api/explain':
                run = store.metadata(data.get('id'))
                if 'report' not in run:
                    raise ValueError('Select an analyzed trial first')
                model = data.get('model')
                if not isinstance(model, str) or not model.strip() or len(model) > 200:
                    raise ValueError('Choose an available model')
                return self.reply(200, dict(text=ollama.explain(run['report'], model)))
            with store.lock:
                if path == '/api/record':
                    value = store.create(data)
                elif path == '/api/freeze':
                    value = store.freeze(data)
                elif path == '/api/plan':
                    value = store.plan(data)
                elif path == '/api/demo':
                    value = store.demo()
                else:
                    return self.reply(404, dict(error='Not found'))
            self.reply(200, value)
        except (ValueError, OSError, KeyError, TypeError, OverflowError) as exc:
            self.reply(400, dict(error=str(exc)))
        except Exception:
            self.reply(500, dict(error='The operation failed. Check the local server and try again.'))


def serve(port=8765, data_dir='data/ui', private_dir='private/ui'):
    server = DashboardServer(('127.0.0.1', port), Workspace(data_dir, private_dir))
    print(f'Anomaly Observatory: http://127.0.0.1:{server.server_port}', flush=True)
    print('Local access only. Press Ctrl+C to stop.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
