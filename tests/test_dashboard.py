"""Exercise dashboard HTTP boundaries and workflows against an ephemeral local server."""
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from anomaly_observatory.server import DashboardServer, Workspace


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.store = Workspace(root/'data', root/'private')
        self.server = DashboardServer(('127.0.0.1', 0), self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.token = self.call('/api/state')[1]['csrf']

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def call(self, path, data=None, headers=None):
        request_headers = {} if data is None else {
            'Content-Type': 'application/json', 'X-Observatory-Token': getattr(self, 'token', '')}
        request_headers.update(headers or {})
        request = Request(self.base+path, headers=request_headers,
                          data=None if data is None else json.dumps(data).encode())
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            body = response.read()
            if response.headers.get_content_type() == 'application/json':
                body = json.loads(body)
            return response.status, body

    def baseline(self):
        status, result = self.call('/api/record', dict(kind='baseline', label='Baseline', seconds=2))
        self.assertEqual(status, 200, result)
        return result

    def test_demo_records_real_analysis_and_downloads(self):
        status, run = self.call('/api/demo', {})
        self.assertEqual(status, 200, run)
        self.assertTrue(run['report']['channels']['magnetic_uT']['flagged'])
        self.assertEqual(sum(v['flagged'] for v in run['report']['channels'].values()), 1)
        status, detail = self.call(f'/api/runs/{run["id"]}')
        self.assertEqual(status, 200)
        self.assertEqual(detail['total_samples'], 600)
        self.assertEqual(detail['meta']['source'], 'SIMULATED')
        status, csv = self.call(f'/api/runs/{run["id"]}/csv')
        self.assertEqual(status, 200)
        self.assertEqual(len(csv.decode().splitlines()), 1201)
        self.assertEqual(self.call(f'/api/runs/{run["id"]}/report')[1], run['report'])
        fresh = Workspace(self.store.root, self.store.private)
        self.assertEqual(len(fresh.state()['runs']), 2)

    def test_baseline_must_be_frozen_and_protocol_cannot_change(self):
        base = self.baseline()
        trial = dict(kind='trial', label='Trial', seconds=2, seed=9, baseline_id=base['id'])
        self.assertEqual(self.call('/api/record', trial)[0], 400)
        self.assertEqual(len(self.store.state()['runs']), 1)
        status, frozen = self.call('/api/freeze', dict(id=base['id'], factor=3))
        self.assertEqual(status, 200)
        self.assertEqual(self.call('/api/freeze', dict(id=base['id'], factor=6))[0], 400)
        self.assertEqual(self.store.protocol(base['id'])['sha256'], frozen['sha256'])
        self.assertEqual(self.call('/api/record', trial)[0], 200)

    def test_csv_validation_and_import_provenance(self):
        base = self.baseline()
        self.call('/api/freeze', dict(id=base['id']))
        csv = (self.store.directory(base['id'])/'recording.csv').read_text()
        status, result = self.call('/api/record',dict(kind='baseline',source='import',label='Imported',csv=csv))
        self.assertEqual(status, 200, result)
        self.assertEqual(result['source'], 'UNVERIFIED IMPORT')
        status, result = self.call('/api/record',dict(kind='baseline',source='import',label='Bad',csv='wrong,header\n'))
        self.assertEqual(status, 400)
        self.assertIn('CSV header', result['error'])
        self.assertEqual(len(list(self.store.root.iterdir())), 2)

    def test_private_key_not_served_or_exposed_in_state(self):
        status, plan = self.call('/api/plan', dict(repeats=2))
        self.assertEqual(status, 200)
        self.assertEqual(len(plan['runs']), 6)
        self.assertTrue(all('condition' not in run for run in plan['runs']))
        key = json.loads((self.store.private/plan['key_filename']).read_text())
        self.assertEqual([run['condition'] for run in key].count('active'), 2)
        for path in [f'/private/{plan["key_filename"]}', '/api/runs/../../private/key', '/server.py']:
            self.assertEqual(self.call(path)[0], 404)
        self.assertNotIn('condition', json.dumps(self.call('/api/state')[1]))

    def test_csrf_origin_and_host_are_enforced(self):
        self.assertEqual(self.call('/api/demo', {}, {'X-Observatory-Token':''})[0], 403)
        self.assertEqual(self.call('/api/demo', {}, {'Origin':'https://example.com'})[0], 400)
        self.assertEqual(self.call('/api/state', headers={'Host':'attacker.example'})[0], 400)
        self.assertEqual(self.store.state()['runs'], [])

    def test_cloud_only_sends_selected_report(self):
        run = self.call('/api/demo', {})[1]
        with patch.dict(os.environ, {'OLLAMA_API_KEY':'private-test-key'}):
            state = self.call('/api/state')[1]
            self.assertTrue(state['cloud_configured'])
            self.assertNotIn('private-test-key', json.dumps(state))
        with patch('anomaly_observatory.server.ollama.models',return_value={'models':[{'name':'current-model'}]}):
            self.assertEqual(self.call('/api/models', {})[1]['models'][0]['name'], 'current-model')
        with patch('anomaly_observatory.server.ollama.explain', return_value='Advisory notes') as explain:
            status, response = self.call('/api/explain', dict(id=run['id'],model='current-model'))
            self.assertEqual(status, 200)
            self.assertEqual(response['text'], 'Advisory notes')
            explain.assert_called_once_with(run['report'], 'current-model', None)

    def test_saved_cloud_key_stays_on_the_server(self):
        secret = 'dashboard-key-not-for-the-browser'
        self.assertFalse(self.call('/api/state')[1]['cloud_configured'])
        self.assertEqual(self.call('/api/cloud-key', dict(key=' bad key'))[0], 400)
        status, saved = self.call('/api/cloud-key', dict(key=secret))
        self.assertEqual(status, 200, saved)
        self.assertEqual(saved, dict(cloud_configured=True))
        self.assertNotIn(secret, json.dumps(saved))
        state = self.call('/api/state')[1]
        self.assertTrue(state['cloud_configured'])
        self.assertNotIn(secret, json.dumps(state))
        self.assertEqual((self.store.private/'ollama-api-key').read_text().strip(), secret)
        self.assertEqual(self.call('/private/ollama-api-key')[0], 404)
        with patch('anomaly_observatory.server.ollama.models', return_value={'models': []}) as models:
            self.assertEqual(self.call('/api/models', {})[0], 200)
            models.assert_called_once_with(secret)

    def test_invalid_parameters_fail_without_partial_recording(self):
        for field, value in [('seconds', 0), ('seconds', 301), ('rate', 1.5), ('seed', -1), ('injection', float('inf'))]:
            data = dict(kind='baseline', label='Invalid', seconds=2)
            data[field] = value
            self.assertEqual(self.call('/api/record',data)[0], 400)
        self.assertEqual(list(self.store.root.iterdir()), [])

    def test_assets_served_and_unknown_paths_rejected(self):
        for path, marker in [('/',b'Observation workspace'),('/app.js',b'renderChart'),('/style.css',b'@media')]:
            status, body = self.call(path)
            self.assertEqual(status, 200)
            self.assertIn(marker, body)
        self.assertEqual(self.call('/api/unknown')[0], 404)
        self.assertEqual(self.call('/api/unknown',{})[0], 404)


if __name__ == '__main__':
    unittest.main()
