import argparse
import json
from pathlib import Path
from . import core, ollama


def main():
    parser = argparse.ArgumentParser(description='Paired-pod anomaly research prototype')
    sub = parser.add_subparsers(dest='command', required=True)
    sim = sub.add_parser('simulate', help='Record synthetic matched pods as CSV')
    sim.add_argument('output'); sim.add_argument('--seconds', type=float, default=60)
    sim.add_argument('--rate', type=int, default=20); sim.add_argument('--seed', type=int, default=42)
    sim.add_argument('--inject', type=float, default=0, help='Synthetic pod A magnetic offset in µT')
    reg = sub.add_parser('preregister', help='Freeze baseline-derived engineering thresholds before a trial')
    reg.add_argument('baseline'); reg.add_argument('output'); reg.add_argument('--factor', type=float, default=3)
    ana = sub.add_parser('analyze'); ana.add_argument('recording'); ana.add_argument('protocol'); ana.add_argument('output')
    trial = sub.add_parser('plan'); trial.add_argument('public'); trial.add_argument('private'); trial.add_argument('--repeats', type=int, default=4)
    sub.add_parser('models', help='List currently available Ollama Cloud models')
    ai = sub.add_parser('explain', help='Send only the selected result JSON to Ollama Cloud')
    ai.add_argument('report'); ai.add_argument('--model', required=True)
    ui = sub.add_parser('serve', help='Launch the local web dashboard')
    ui.add_argument('--port', type=int, default=8765)
    ui.add_argument('--data-dir', default='data/ui')
    ui.add_argument('--private-dir', default='private/ui')
    args = parser.parse_args()
    try:
        if args.command == 'simulate':
            core.simulate(args.output, args.seconds, args.rate, args.seed, args.inject)
        elif args.command == 'preregister':
            core.preregister(args.baseline, args.output, args.factor)
        elif args.command == 'analyze':
            result = core.analyze(args.recording, args.protocol)
            core.save_new(args.output, result)
            print(json.dumps(result, indent=2))
        elif args.command == 'plan':
            core.plan(args.public, args.private, args.repeats)
        elif args.command == 'models':
            print(json.dumps(ollama.models(), indent=2))
        elif args.command == 'explain':
            print(ollama.explain(json.loads(Path(args.report).read_text()), args.model))
        elif args.command == 'serve':
            from .server import serve
            serve(args.port, args.data_dir, args.private_dir)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f'Error: {exc}\n')
