import runpy,unittest
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
class Reader:
    def call(self,*args,**kwargs):return []
    def scan(self,model,domain,fields):
        return [] if any(x[0]=='name' for x in domain) else [{'id':5,'name':'10082026','product_id':[101,'P'],'company_id':[1,'C']}]
class Tests(unittest.TestCase):
    def test_mo_reuses_existing_api_lot_instead_of_duplicate_creation(self):
        M=runpy.run_path(str(BASE/'migrate_pysb_independent_mos.py'));r=M['Run'].__new__(M['Run'])
        r.maps={'stock.lot':{}};r.lots={10:{'name':'10082026','product_id':[1,'P']}};r.mapped=lambda model,sid:101
        r.b=Reader();r.j={};r.persist=lambda:None;r.mutate=lambda *a,**k:self.fail('Existing lot must not be created again')
        attached=[];r.attach=lambda *args:attached.append(args)
        self.assertEqual(r.lot(10),5);self.assertEqual(attached,[('stock.lot',10,5)])
    def test_inventory_reuses_existing_api_lot_instead_of_duplicate_creation(self):
        M=runpy.run_path(str(BASE/'migrate_pysb_inventory_adjustments.py'));r=M['Run'].__new__(M['Run'])
        r.maps={'product.product':{1:101},'stock.lot':{}};r.lots={10:{'name':'10082026','product_id':[1,'P']}}
        r.b=Reader();r.j={};r.persist=lambda:None;r.mutate=lambda *a,**k:self.fail('Existing lot must not be created again')
        attached=[];r.attach=lambda *args:attached.append(args)
        self.assertEqual(r.lot(10),5);self.assertEqual(attached,[('stock.lot',10,5)])
if __name__=='__main__':unittest.main()
