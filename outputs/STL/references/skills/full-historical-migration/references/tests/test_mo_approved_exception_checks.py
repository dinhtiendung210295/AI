import copy
import runpy
import unittest
from pathlib import Path
F=runpy.run_path(str(Path(__file__).resolve().parents[1]/'mo_approved_exception_checks.py'))['annotate']


class Tests(unittest.TestCase):
    def fixture(self):
        metric={'source':.62448,'target':.62,'delta':-.00448,'match':False}
        move={'source_move':10,'issues':['move_dimensions_or_state_not_verified'],'metrics':{'demand':dict(metric),'done':dict(metric)},'match':False}
        report={'rows':[{'match':False,'issues':[],'metrics':{'planned':{'match':True}},'moves':[move]}],'summary':{}}
        expected={10:{label:{'source':.62448,'target':.62,'proof':'approved'} for label in ['demand','done']}}
        return report,expected

    def test_approved_exception_keeps_original_failed_metrics(self):
        report,expected=self.fixture();F(report,{10:'approved_exception'},expected)
        row=report['rows'][0]
        self.assertTrue(row['accepted_with_approved_exceptions'])
        self.assertFalse(row['match'])
        self.assertFalse(row['moves'][0]['metrics']['done']['match'])
        self.assertEqual(row['moves'][0]['metrics']['done']['source'],.62448)

    def test_unverified_dimensions_cannot_be_waived(self):
        report,expected=self.fixture();F(report,{10:'unresolved'},expected)
        self.assertFalse(report['rows'][0]['accepted_with_approved_exceptions'])

    def test_demand_permission_cannot_waive_done_difference(self):
        report,expected=self.fixture();del expected[10]['done']
        F(report,{10:'approved_exception'},expected)
        self.assertFalse(report['rows'][0]['accepted_with_approved_exceptions'])

    def test_wrong_target_or_other_issue_blocks(self):
        for mutation in ['target','issue','header']:
            report,expected=self.fixture()
            if mutation=='target':expected[10]['done']['target']=.63
            elif mutation=='issue':report['rows'][0]['moves'][0]['issues'].append('wrong_mo_or_move_role')
            else:report['rows'][0]['issues'].append('different:date_finished')
            F(report,{10:'approved_exception'},expected)
            self.assertFalse(report['rows'][0]['accepted_with_approved_exceptions'])


if __name__=='__main__':unittest.main()
