import json,runpy,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
release=runpy.run_path(str(Path(__file__).parents[1]/'scoped_delivery_reservations.py'))['release']

class Tests(unittest.TestCase):
    def fixture(self,directory,picked=False,known=True):
        phase=directory/'phases';phase.mkdir()
        (phase/'operator-reservation-release-approval.json').write_text(json.dumps(dict(approved=True,company_id=1,target_database='py19-main-33843450')),encoding='utf8')
        entry=dict(status='verified_confirmed',target_id=3,before={'picking_ids':[]},picking_ids=[4],moves=[dict(id=5,picking_id=[4,'P'])])
        (phase/'so-confirmation-journal.json').write_text(json.dumps({'orders':{'7':entry} if known else {}}),encoding='utf8')
        state={'released':False,'writes':[]}
        def scan(model,domain,fields):
            if model=='stock.quant':return [dict(id=9,product_id=[1,'P'],location_id=[2,'L'],lot_id=False,quantity=2,reserved_quantity=1 if state['released'] else 3,package_id=False,owner_id=False)]
            return [dict(id=10,move_id=[5,'M'],picking_id=[4,'P'],company_id=[1,'C'],product_id=[1,'P'],location_id=[2,'L'],lot_id=False,quantity=2,picked=picked,state='assigned')]
        def read(model,ids,fields):
            if model=='stock.picking':return [dict(id=4,company_id=[1,'C'],state='assigned',sale_id=[3,'SO'],move_ids=[5],date_done=False)]
            if model=='stock.move.line':return [dict(id=10,picked=picked,state='assigned')]
            if fields==['quantity','move_line_ids']:return [dict(id=5,quantity=0,move_line_ids=[])]
            return [dict(id=5,company_id=[1,'C'],state='assigned',picked=False,move_line_ids=[10],purchase_line_id=False,production_id=False,raw_material_production_id=False,product_id=[1,'P'])]
        def mutate(model,method,args,**kw):
            state['writes'].append((model,method,args));state['released']=True
        r=SimpleNamespace(reservation_evidence_dir=directory,b=SimpleNamespace(scan=scan,read=read),mutate=mutate,j={},persist=lambda:None)
        return r,state
    def test_only_scoped_native_hold_is_released_with_unchanged_physical_stock(self):
        with tempfile.TemporaryDirectory() as tmp:
            r,s=self.fixture(Path(tmp));release(r,{(1,2,False):1},{99})
            self.assertEqual(s['writes'],[('stock.picking','do_unreserve',[[4]])])
            self.assertEqual(r.j['scoped_reservation_releases'][0]['status'],'verified_released')
    def test_picked_or_unknown_owner_never_mutates(self):
        for picked,known in [(True,True),(False,False)]:
            with tempfile.TemporaryDirectory() as tmp:
                r,s=self.fixture(Path(tmp),picked,known)
                with self.assertRaises(RuntimeError):release(r,{(1,2,False):1},{99})
                self.assertEqual(s['writes'],[])
    def test_physical_shortage_cannot_be_solved_by_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            r,s=self.fixture(Path(tmp))
            with self.assertRaisesRegex(RuntimeError,'Physical stock shortage'):release(r,{(1,2,False):5},{99})
            self.assertEqual(s['writes'],[])
    def test_foreign_picking_is_preserved_while_known_migration_allocation_is_released(self):
        with tempfile.TemporaryDirectory() as tmp:
            r,s=self.fixture(Path(tmp));original_scan=r.b.scan;original_read=r.b.read
            def scan(model,domain,fields):
                rows=original_scan(model,domain,fields)
                if model=='stock.move.line':rows.append({**rows[0],'id':44,'move_id':[45,'Foreign'],'picking_id':[46,'Foreign']})
                return rows
            def read(model,ids,fields):
                rows=original_read(model,ids,fields)
                if model=='stock.picking':rows.append({**rows[0],'id':46,'sale_id':False,'move_ids':[45]})
                return rows
            r.b.scan=scan;r.b.read=read;release(r,{(1,2,False):1},{99})
            self.assertEqual(s['writes'],[('stock.picking','do_unreserve',[[4]])])
            self.assertEqual(r.j['scoped_reservation_releases'][0]['excluded_non_scoped_pickings'][0]['id'],46)

if __name__=='__main__':unittest.main()
