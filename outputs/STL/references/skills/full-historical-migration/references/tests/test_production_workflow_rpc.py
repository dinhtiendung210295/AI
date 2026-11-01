import runpy
import unittest
from pathlib import Path
M=runpy.run_path(str(Path(__file__).resolve().parents[1]/'production_workflow_rpc.py'))

class Tests(unittest.TestCase):
    def test_workflows_do_not_inherit_archive_read_context(self):
        original={'context':{'active_test':False,'allowed_company_ids':[2],'send_email':False}}
        actual=M['workflow_options'](original)
        self.assertTrue(actual['context']['active_test']);self.assertEqual(actual['context']['allowed_company_ids'],[1]);self.assertFalse(actual['context']['send_email'])
        self.assertFalse(original['context']['active_test'])
    def test_wrong_database_blocked_before_any_rpc(self):
        reader=type('Reader',(),{'url':'https://py19.odoo.com','db':'staging'})()
        with self.assertRaisesRegex(RuntimeError,'identity mismatch'):M['call'](reader,'sale.order','action_confirm',[[1]])

if __name__=='__main__':unittest.main()
