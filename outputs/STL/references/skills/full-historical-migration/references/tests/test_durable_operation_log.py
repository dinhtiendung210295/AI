import json
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

Log = runpy.run_path(str(Path(__file__).parents[1] / 'production_operation_log.py'))['OperationLog']


class DurableLogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.log = Log(self.temp.name, {'database': 'fake', 'company_id': 1, 'scope_hash': 'test'})

    def intent(self, oid='a'):
        self.log.append_intent({'operation_id': oid, 'phase': 'confirm-po', 'target_id': 1})

    def test_resume_pending_blocks_second_mutation(self):
        self.intent()
        resumed = Log(self.temp.name, self.log.identity)
        self.assertIn('a', resumed.unresolved())
        with self.assertRaises(RuntimeError):
            resumed.append_intent({'operation_id': 'b'})

    def test_uncertain_readback_resolves_without_second_intent(self):
        self.intent()
        self.log.mark_uncertain('a', 'connection lost')
        self.log.append_result('a', {'readback': True, 'state': 'purchase'})
        self.assertEqual({}, self.log.unresolved())
        self.log.build_checkpoint()
        self.log.assert_checkpoint_current()
        with self.assertRaises(RuntimeError):
            self.intent()

    def test_old_checkpoint_rejected_after_new_event(self):
        self.log.build_checkpoint()
        self.intent()
        with self.assertRaises(RuntimeError):
            self.log.assert_checkpoint_current()

    def test_incomplete_tail_rejected(self):
        self.log.path.write_bytes(b'{')
        with self.assertRaises(RuntimeError):
            Log(self.temp.name, self.log.identity)

    def test_corruption_rejected(self):
        self.intent()
        text = self.log.path.read_text(encoding='utf8').replace('confirm-po', 'confirm-so')
        self.log.path.write_text(text, encoding='utf8')
        with self.assertRaises(RuntimeError):
            Log(self.temp.name, self.log.identity)

    def test_identity_rejected(self):
        self.intent()
        with self.assertRaises(RuntimeError):
            Log(self.temp.name, {'database': 'other'})

    def test_fsync_failure_prevents_caller_reaching_rpc(self):
        with patch('os.fsync', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.intent()
        self.assertEqual([], self.log.events)
        self.assertIn('a', Log(self.temp.name, self.log.identity).unresolved())

    def test_result_requires_intent(self):
        with self.assertRaises(RuntimeError):
            self.log.append_result('missing', {})

    def test_integer_mapping_keys_and_tuples_survive_replay(self):
        self.log.append_intent({'operation_id': 'a', 'maps': {2: (10, 'label'), 11: [20, 'other']}})
        self.log.append_result('a', {'returned': True})
        resumed = Log(self.temp.name, self.log.identity)
        self.assertEqual({}, resumed.unresolved())
        self.assertEqual([10, 'label'], resumed.events[0]['payload']['maps']['2'])

    def test_result_cannot_be_overwritten(self):
        self.intent()
        self.log.append_result('a', {'state': 'purchase'})
        with self.assertRaises(RuntimeError):
            self.log.mark_uncertain('a', 'late error')

    def test_same_length_external_edit_rejected_before_next_append(self):
        self.intent()
        original=self.log.path.read_text(encoding='utf8')
        self.log.path.write_text(original.replace('confirm-po','confirm-so'),encoding='utf8')
        with self.assertRaises(RuntimeError):self.log.append_result('a',{})

    def test_external_valid_append_requires_handoff(self):
        self.intent();self.log.append_result('a',{})
        other=Log(self.temp.name,self.log.identity)
        other.append_intent({'operation_id':'other'});other.append_result('other',{})
        with self.assertRaises(RuntimeError):self.log.append_intent({'operation_id':'b'})

    def test_unchanged_file_avoids_full_replay_until_checkpoint(self):
        with patch.object(self.log,'replay',wraps=self.log.replay) as replay:
            self.intent();self.log.append_result('a',{})
            self.assertEqual(0,replay.call_count)
            self.log.build_checkpoint()
            self.assertEqual(1,replay.call_count)


if __name__ == '__main__':
    unittest.main()
