import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mo_quantity_checks import compare_mos

class MOChecks(unittest.TestCase):
    def setUp(self):
        self.s={'id':1,'name':'MO','state':'done','company_id':[1,'PYSB'],'date_finished':'2026-08-02 00:00:00','product_id':[3,'Finished'],'product_uom_id':[4,'Unit'],'product_qty':10,'qty_produced':8,'move_raw_ids':[5],'move_finished_ids':[6,7]}
        self.t={**self.s,'id':2,'product_id':[30,'Finished'],'product_uom_id':[40,'Unit'],'move_raw_ids':[50],'move_finished_ids':[60,70]}
        self.sm=[{'id':i,'state':'done','product_uom':[4,'Unit'],'product_uom_qty':v,'quantity_done':v} for i,v in [(5,12),(6,8),(7,2)]]
        self.tm=[{**x,'id':x['id']*10,'quantity':x['quantity_done']} for x in self.sm]
        self.maps={'mrp.production':{1:2},'product.product':{3:30},'uom.uom':{4:40},'stock.move':{5:50,6:60,7:70}}
    def check(self):
        return compare_mos([self.s],[self.t],self.sm,self.tm,self.maps,{4:{'rounding':0.01}},{5:'verified',6:'verified',7:'verified'})['rows'][0]
    def test_partial_output_and_byproduct(self):self.assertTrue(self.check()['match'])
    def test_duplicate_consumption(self):
        self.tm[0]['quantity']=24
        self.assertFalse(self.check()['match'])
    def test_missing_byproduct(self):
        self.t['move_finished_ids']=[60]
        self.assertFalse(self.check()['match'])
    def test_planned_quantity_not_ignored(self):
        self.t['product_qty']=11
        self.assertFalse(self.check()['match'])
    def test_wrong_historical_date(self):
        self.t['date_finished']='2026-10-24 00:00:00'
        self.assertFalse(self.check()['match'])
    def test_historical_start_uses_source_plan_if_actual_missing(self):
        self.s['date_start']=False;self.s['date_planned_start']='2026-08-01 00:00:00';self.t['date_start']='2026-10-24 00:00:00'
        self.assertIn('different:date_start',self.check()['issues'])
    def test_missing_mapping_not_skipped(self):
        self.maps['mrp.production']={}
        self.assertFalse(self.check()['match'])

if __name__=='__main__':unittest.main()
