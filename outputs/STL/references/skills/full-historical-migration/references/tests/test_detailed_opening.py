import runpy
import unittest
from pathlib import Path

M=runpy.run_path(str(Path(__file__).resolve().parents[1]/'inspect_pysb_detailed_opening.py'))
collect=M['collect']

class Reader:
    source=True
    changed=False
    def __init__(self,*args):self.r=type('Identity',(),{'db':'fake'})();self.calls=0
    def scan(self,model,domain,fields):
        if model=='stock.quant':
            self.calls+=1
            return [{'id':1,'product_id':[1,'P'],'location_id':[10,'Stock'],'lot_id':[20,'LOT'],'package_id':[30,'Pack'],'owner_id':[40,'Owner'],'quantity':100+(1 if self.changed and self.calls>1 else 0)}]
        return [{'id':2,'product_id':[1,'P'],'product_uom_id':[2,'kg'],'location_id':[11,'Vendor'],'location_dest_id':[10,'Stock'],'lot_id':[20,'LOT'],'package_id':False,'result_package_id':[30,'Pack'],'owner_id':[40,'Owner'],'date':'2026-08-01 00:00:00',('qty_done' if self.source else 'quantity'):0.025}]
    def read(self,model,ids,fields):
        if model=='product.product':return [{'id':1,'uom_id':[1,'g']}]
        if model=='uom.uom':return [{'id':1,'factor':1},{'id':2,'factor':0.001 if self.source else 1000}]
        return [{'id':10,'usage':'internal'},{'id':11,'usage':'supplier'}]

class Tests(unittest.TestCase):
    def setUp(self):
        self.g=collect.__globals__;self.old={k:self.g[k] for k in ['ReadOnly','save']}
        self.g['ReadOnly']=Reader;self.g['save']=lambda *args:None
        Reader.source=True;Reader.changed=False
    def tearDown(self):self.g.update(self.old)
    def test_v14_inverse_factor_and_destination_package(self):
        self.assertEqual(collect('test',(),[1],'2026-08-01',True),[{'key':[1,10,20,30,40],'quantity':75}])
    def test_v19_direct_factor(self):
        Reader.source=False
        self.assertEqual(collect('test',(),[1],'2026-08-01',False)[0]['quantity'],75)
    def test_concurrent_stock_change_rejected(self):
        Reader.changed=True
        with self.assertRaisesRegex(RuntimeError,'quants changed'):collect('test',(),[1],'2026-08-01',True)

if __name__=='__main__':unittest.main()
