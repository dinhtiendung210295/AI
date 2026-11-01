import copy
import runpy
import unittest
from pathlib import Path
from unittest.mock import patch
M=runpy.run_path(str(Path(__file__).resolve().parents[1]/'run_pysb_independent_work_queue.py'))

class Tests(unittest.TestCase):
    def journals(self):
        return {'independent-receipts-journal.json':{'operations':[]},
                'independent-inventory-journal.json':{'operations':[],'groups':{}},
                'independent-mo-journal.json':{'operations':[],'mos':{}},
                'independent-delivery-journal.json':{'operations':[],'groups':{}},
                'independent-invoice-journal.json':{'operations':[],'documents':{}}}
    def test_uncertain_receipt_or_any_writer_stops_queue(self):
        for name in self.journals():
            data=self.journals();data[name]['operations']=[{'status':'uncertain'}]
            with self.subTest(name=name),patch.dict(M['totals'].__globals__,{'load':lambda n:data[n]}),self.assertRaises(RuntimeError):M['totals']()
    def test_prepared_unverified_delivery_stops_queue(self):
        data=self.journals();data['independent-delivery-journal.json']['groups']['1']={'phase':'chain_prepared'}
        with patch.dict(M['totals'].__globals__,{'load':lambda n:data[n]}),self.assertRaises(RuntimeError):M['totals']()
    def test_explicit_hold_is_separate_from_completed_count(self):
        data=self.journals();data['independent-delivery-journal.json']['groups']={'1':{'phase':'completed'},'2':{'phase':'confirmation_held','execution_hold':True}}
        with patch.dict(M['totals'].__globals__,{'load':lambda n:data[n]}):counts=M['totals']()
        self.assertEqual(counts['groups:independent-delivery-journal.json'],1)
        self.assertEqual(counts['execution_holds:independent-delivery-journal.json'],1)
    def test_failed_writer_command_is_called_once_and_propagated(self):
        class Result:returncode=7
        with patch.object(M['run'].__globals__['subprocess'],'run',return_value=Result()) as mocked:
            with self.assertRaises(SystemExit) as error:M['run']('migrate_pysb_independent_deliveries.py','--mode','batch')
            self.assertEqual(error.exception.code,7);self.assertEqual(mocked.call_count,1)
if __name__=='__main__':unittest.main()
