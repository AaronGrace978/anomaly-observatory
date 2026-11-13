import csv
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from anomaly_observatory import core, ollama


class ObservatoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.baseline = self.root / 'baseline.csv'
        self.protocol = self.root / 'protocol.json'
        core.simulate(self.baseline, seconds=10)
        core.preregister(self.baseline, self.protocol)

    def test_null_and_injected_signal(self):
        for injection in (0, 1):
            path = self.root / f'trial-{injection}.csv'
            core.simulate(path, seconds=10, seed=8, injection=injection)
            result = core.analyze(path, self.protocol)
            self.assertEqual(result['source'], 'SIMULATED')
            self.assertEqual(result['channels']['magnetic_uT']['flagged'], bool(injection))
            self.assertFalse(result['channels']['temperature_c']['flagged'])

    def test_missing_pair_rejected(self):
        lines = self.baseline.read_text().splitlines()
        path = self.root / 'broken.csv'
        path.write_text('\n'.join(lines[:-1]) + '\n')
        with self.assertRaisesRegex(ValueError, 'Missing'):
            core.load_pairs(path)

    def test_nonfinite_rejected(self):
        path = self.root / 'bad.csv'
        path.write_text(self.baseline.read_text().replace('50.', 'nan', 1))
        with self.assertRaises(ValueError):
            core.load_pairs(path)

    def test_baseline_cannot_be_trial(self):
        with self.assertRaisesRegex(ValueError, 'separate recording'):
            core.analyze(self.baseline, self.protocol)

    def test_outputs_not_overwritten(self):
        with self.assertRaises(FileExistsError):
            core.preregister(self.baseline, self.protocol)

    def test_blinding_balanced_and_key_private(self):
        public, private = self.root/'plan.json', self.root/'key.json'
        core.plan(public, private, 5)
        plan, key = json.loads(public.read_text()), json.loads(private.read_text())
        self.assertTrue(all('condition' not in run for run in plan))
        self.assertEqual([r['condition'] for r in key].count('sham'), 5)
        self.assertEqual(private.stat().st_mode & 0o777, 0o600)

    def test_cloud_key_required(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'OLLAMA_API_KEY'):
                ollama.models()

    def test_cloud_uses_selected_model(self):
        with patch.object(ollama, 'request', return_value={'message': {'content': 'Review'}}) as request:
            self.assertEqual(ollama.explain({'source': 'SIMULATED'}, 'chosen-model'), 'Review')
            self.assertEqual(request.call_args.args[1]['model'], 'chosen-model')

if __name__ == '__main__':
    unittest.main()
