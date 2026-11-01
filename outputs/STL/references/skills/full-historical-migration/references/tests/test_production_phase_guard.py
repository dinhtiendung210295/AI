import json
import os
import runpy
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

guard = runpy.run_path(str(Path(__file__).parents[1] / 'production_phase_guard.py'))['require_access']


class GuardTests(unittest.TestCase):
    def test_stock_session_token_requires_matching_process_and_enabled_phase(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'PYSB_PHASE_TOKEN':'stock-nonce'}):
            directory=Path(temp);phase=directory/'phases';phase.mkdir()
            identity={'scope_hash':'frozen'}
            (phase/'phased-control-enabled.json').write_text(json.dumps(dict(identity=identity,supported_phases=['stock'])),encoding='utf8')
            active=dict(identity=identity,phase='stock',token='stock-nonce',pid=os.getpid())
            (phase/'active-phase.json').write_text(json.dumps(active),encoding='utf8')
            guard(directory=directory)
            active['pid']=-1
            (phase/'active-phase.json').write_text(json.dumps(active),encoding='utf8')
            with self.assertRaises(RuntimeError):guard(directory=directory)

    def test_only_current_controller_token_can_write(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            phase = directory / 'phases'
            phase.mkdir()
            identity = {'scope_hash': 'frozen'}
            (phase / 'phased-control-enabled.json').write_text(json.dumps(dict(identity=identity, supported_phases=['confirm-po'])), encoding='utf8')
            active = dict(identity=identity, phase='confirm-po', token='nonce', pid=os.getpid())
            (phase / 'active-phase.json').write_text(json.dumps(active), encoding='utf8')
            guard('nonce', directory)
            for token in (None, 'old'):
                with self.assertRaises(RuntimeError):
                    guard(token, directory)
            active['phase'] = 'stock'
            (phase / 'active-phase.json').write_text(json.dumps(active), encoding='utf8')
            with self.assertRaises(RuntimeError):
                guard('nonce', directory)
