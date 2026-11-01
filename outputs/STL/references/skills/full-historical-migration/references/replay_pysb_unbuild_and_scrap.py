"""Native stock replay of two source Unbuild pairs and one standard Scrap."""
from complete_pysb_stock_migration import Completion,rid,index,load,OUT
from execute_pysb_stock_migration import save,require
from collections import defaultdict
import json
def main():
 m=Completion();d=load('closing-gap-source-documents.json');sources=index(d['moves']);lines=defaultdict(list)
 for x in d['lines']:
  if x['qty_done']>0:lines[rid(x['move_id'])].append(x)
 m.uoms=index(m.b.search_read('uom.uom',[],['factor','rounding']));ops=m.j.setdefault('closing_unbuild_scrap_operations',{})
 def stock():return m.ledger(m.b.search_read('stock.quant',[['company_id','=',1]],['product_id','location_id','lot_id','package_id','owner_id','quantity']))
 for ref,ids in [('UB/00618',[502306,502307]),('UB/00619',[502674,502675]),('SP/00084',[507906])]:
  if ops.get(ref,{}).get('status')=='verified':continue
  require(ref not in ops,'Interrupted operation: read-back before retry');ss=[sources[i] for i in ids];xs=[x for i in ids for x in lines[i]];before=stock();delta=defaultdict(float);need=defaultdict(float)
  for x in xs:
   require(not x['package_id'] and not x['result_package_id'] and not x['owner_id'],'Unexpected stock dimensions');a=m.quantkey(x);b=m.quantkey(x,True);q=m.qty(x);delta[a]-=q;delta[b]+=q
   if m.locations[a[1]]['usage'] in ['internal','transit']:need[a]+=q
  require(all(before[k]+1e-6>=q for k,q in need.items()),'Missing stock: '+str([(k,before[k],q) for k,q in need.items() if before[k]+1e-6<q]))
  require(not m.b.search_read('ir.model.data',[['module','=','pysb_v14'],['model','=','stock.move'],['name','in',['stock_move_'+str(i) for i in ids]]],['res_id']),'Source already mapped')
  op={'status':'intent','source_moves':ss,'source_lines':xs,'before':[[list(k),before[k]] for k in delta],'deltas':[[list(k),q] for k,q in delta.items()],'reference':ref};ops[ref]=op;m.persist();targetpick=False
  if ref.startswith('UB/'):
   first=ss[0];targetpick=m.mutate('stock.picking','create',[{'company_id':1,'picking_type_id':7,'location_id':m.maps['stock.location'][rid(first['location_id'])],'location_dest_id':m.maps['stock.location'][rid(first['location_dest_id'])],'scheduled_date':first['date'],'origin':'PYSB-UNBUILD | v14 '+ref,'note':json.dumps(op,ensure_ascii=False)}]);op['target_picking']=targetpick;m.persist()
   values=[]
   for s in ss:
    v=m.mv(s,picking=targetpick);v.update(sale_line_id=False,purchase_line_id=False,origin='PYSB-UNBUILD | v14 '+ref,description_picking_manual=json.dumps(s,ensure_ascii=False));values.append(v)
   targetids=m.mutate('stock.move','create',[values]);op['target_moves']=targetids;m.persist()
   for s,t in zip(ss,targetids):
    vals=[{'company_id':1,'picking_id':targetpick,'move_id':t,'product_id':m.maps['product.product'][rid(x['product_id'])],'product_uom_id':m.maps['uom.uom'][rid(x['product_uom_id'])],'quantity':m.effective_qty(x),'picked':True,'location_id':m.maps['stock.location'][rid(x['location_id'])],'location_dest_id':m.maps['stock.location'][rid(x['location_dest_id'])],'lot_id':m.maps['stock.lot'].get(rid(x['lot_id']),False)} for x in lines[s['id']]];m.mutate('stock.move.line','create',[vals])
   result=m.mutate('stock.picking','button_validate',[[targetpick]],{'context':{'skip_backorder':True,'skip_redirection':True,'picking_ids_not_to_backorder':[targetpick]}});require(not isinstance(result,dict) or not result.get('res_model'),'Unexpected wizard; read-back required');require(m.b.read('stock.picking',[targetpick],['state'])[0]['state']=='done','Unbuild pair incomplete');m.mutate('stock.picking','write',[[targetpick],{'date_done':max(s['date'] for s in ss)}])
  else:
   x=xs[0];scrap=m.mutate('stock.scrap','create',[{'company_id':1,'product_id':m.maps['product.product'][rid(x['product_id'])],'product_uom_id':m.maps['uom.uom'][rid(x['product_uom_id'])],'scrap_qty':m.effective_qty(x),'lot_id':m.maps['stock.lot'].get(rid(x['lot_id']),False),'location_id':m.maps['stock.location'][rid(x['location_id'])],'scrap_location_id':m.maps['stock.location'][rid(x['location_dest_id'])],'origin':'PYSB-SOURCE-SCRAP | v14 '+ref}]);op['target_scrap']=scrap;m.persist();result=m.mutate('stock.scrap','action_validate',[[scrap]]);require(not isinstance(result,dict) or not result.get('res_model'),'Scrap wizard; read-back required');actual=m.b.read('stock.scrap',[scrap],['state','move_ids']);require(actual[0]['state']=='done' and len(actual[0]['move_ids'])==1,'Scrap incomplete');targetids=actual[0]['move_ids'];op['target_moves']=targetids;m.persist()
  for s,t in zip(ss,targetids):
   v=m.b.read('stock.move',[t],['state','move_line_ids'])[0];require(v['state']=='done','Move not done');got=m.b.read('stock.move.line',v['move_line_ids'],['product_id','product_uom_id','quantity','location_id','location_dest_id','lot_id']);expected=sorted((m.maps['product.product'][rid(x['product_id'])],m.maps['uom.uom'][rid(x['product_uom_id'])],m.effective_qty(x),m.maps['stock.location'][rid(x['location_id'])],m.maps['stock.location'][rid(x['location_dest_id'])],m.maps['stock.lot'].get(rid(x['lot_id']),False)) for x in lines[s['id']]);require(expected==sorted((rid(x['product_id']),rid(x['product_uom_id']),x['quantity'],rid(x['location_id']),rid(x['location_dest_id']),rid(x['lot_id'])) for x in got),'Detail mismatch');m.mutate('stock.move','write',[[t],{'date':s['date'],'origin':'PYSB-SOURCE | v14 '+ref,'description_picking_manual':json.dumps(op,ensure_ascii=False)}]);m.mutate('stock.move.line','write',[v['move_line_ids'],{'date':s['date']}]);m.attach('stock.move',[(s['id'],t)])
   dd=defaultdict(float)
   for x in lines[s['id']]:dd[m.quantkey(x)]-=m.qty(x);dd[m.quantkey(x,True)]+=m.qty(x)
   m.j.setdefault('supporting_source_transfers',[]).append({'source_move':s['id'],'source_picking':False,'target_picking':targetpick,'target_move':t,'status':'verified','date':s['date'],'source_qty':s['quantity_done'],'target_qty':sum(x['quantity'] for x in got),'reference':ref,'target_lines':v['move_line_ids'],'deltas':[[list(k),q] for k,q in dd.items()],'kind':'unbuild' if ref.startswith('UB/') else 'scrap'})
  after=stock();require(all(abs(after[k]-before[k]-q)<1e-6 for k,q in delta.items()),'Stock delta mismatch');op.update(status='verified',after=[[list(k),after[k]] for k in delta]);m.persist();print(json.dumps({'reference':ref,'target_moves':targetids,'status':'verified'}),flush=True)
if __name__=='__main__':main()
