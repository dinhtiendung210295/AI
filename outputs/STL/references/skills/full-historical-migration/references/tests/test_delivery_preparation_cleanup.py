import copy,runpy,unittest
from pathlib import Path
G=runpy.run_path(str(Path(__file__).resolve().parents[1]/'delivery_preparation_cleanup_guard.py'))['check']
class Tests(unittest.TestCase):
    def data(self):
        original={'id':1,'product_id':10,'product_uom':20,'sale_line_id':30,'company_id':1,'location_id':5,'location_dest_id':9,'picking_id':40,'state':'confirmed','quantity':0,'picked':False,'move_line_ids':[],'move_orig_ids':[],'move_dest_ids':[],'product_uom_qty':3}
        extra=dict(original,id=2,product_uom_qty=6,create_uid=2,rule_id=False,origin=False)
        source={'product_uom_qty':6,'quantity_done':6}
        op={'model':'stock.move','method':'create','status':'returned','result':2,'args':[dict(extra)]}
        return extra,original,source,op,10,20,30,1,2
    def test_only_job_created_unconsumed_demand_duplicate_allowed(self):self.assertTrue(G(*self.data()))
    def test_done_picked_quantities_or_external_links_block_cleanup(self):
        for changed in [{'state':'done'},{'quantity':1},{'picked':True},{'move_line_ids':[4]},{'move_dest_ids':[99]},{'bom_line_id':7},{'purchase_line_id':8}]:
            args=list(self.data());args[0].update(changed)
            with self.subTest(changed=changed),self.assertRaises(ValueError):G(*args)
    def test_uncertain_creation_or_other_record_blocks_cleanup(self):
        for changed in [{'status':'uncertain'},{'result':9}]:
            args=list(self.data());args[3].update(changed)
            with self.subTest(changed=changed),self.assertRaises(ValueError):G(*args)
    def test_correct_original_demand_or_other_product_cannot_be_deleted(self):
        for changed in [{'product_uom_qty':6},{'product_id':11}]:
            args=list(self.data());args[1].update(changed)
            with self.subTest(changed=changed),self.assertRaises(ValueError):G(*args)
if __name__=='__main__':unittest.main()
