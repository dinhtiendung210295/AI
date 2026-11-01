import runpy,unittest
from pathlib import Path
from types import SimpleNamespace
M=runpy.run_path(str(Path(__file__).parents[1]/'native_picking_batch_pilot.py'))
class Tests(unittest.TestCase):
    def test_ten_details_use_one_create_and_one_unreserve_with_readback(self):
        source={};moves={};groups=[];journal={'groups':{},'rounding_differences':[]};calls=[];created={}
        for i in range(1,11):
            source[i]=dict(id=i,move_id=[i,'M'],product_id=[1,'P'],product_uom_id=[1,'U'],qty_done=1.,location_id=[5,'S'],location_dest_id=[9,'D'],lot_id=False,owner_id=False,package_id=False,result_package_id=False,date='2026-09-01 00:00:00')
            moves[i]=dict(id=i,picking_id=[i,'Pick'],state='done',date=source[i]['date'],quantity_done=1.,product_id=[1,'P'],product_uom=[1,'U'],location_id=[5,'S'],location_dest_id=[9,'D'],move_line_ids=[i],write_date='stamp')
            journal['groups'][str(i)]={'move_pairs':{i:100+i}}
            groups.append((dict(source={'id':i},moves=[i]),i,200+i))
        def source_read(model,ids,fields):return [dict((source if model=='stock.move.line' else moves)[i]) for i in ids]
        def target_read(model,ids,fields):
            if model=='stock.move':return [dict(id=i,quantity=0,move_line_ids=[]) for i in ids]
            return [dict(id=i,**created[i]) for i in ids]
        def mutate(model,method,args,**kwargs):
            calls.append((model,method,args))
            if method=='create':
                for n,v in enumerate(args[0],1000):created[n]=v
                return list(created)
        attached=[]
        r=SimpleNamespace(sl=source,sm=moves,maps={'stock.move.line':{},'product.product':{1:1},'uom.uom':{1:1},'stock.location':{5:5,9:9}},tu={1:{'rounding':.01}},j=journal,a=SimpleNamespace(read=source_read),b=SimpleNamespace(read=target_read,scan=lambda *a:[]),mutate=mutate,persist=lambda:None,attach_many=lambda model,pairs:attached.extend(pairs))
        M['prepare_root_details_together'](r,groups,{'rounded':lambda q,p:q})
        self.assertEqual(len([x for x in calls if x[1]=='create']),1)
        self.assertEqual(len([x for x in calls if x[1]=='do_unreserve']),1)
        self.assertEqual(len(attached),10)
if __name__=='__main__':unittest.main()
