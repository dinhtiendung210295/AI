"""Complete source-negative credits for already replayed later consumption."""
from complete_pysb_stock_migration import Completion,rid,require,index,load,OUT
from execute_pysb_stock_migration import save
from datetime import datetime,timedelta,timezone
from collections import defaultdict
from xmlrpc.client import Fault
import json
def main():
 m=Completion();proof=load('later-source-negative-consumption-proof.json');m.uoms=index(m.b.search_read('uom.uom',[],['factor','rounding']))
 for x in proof:
  line=next(a for a in x['source_lines'] if tuple(rid(a[k]) for k in ['product_id','location_id','lot_id','package_id','owner_id'])==tuple(x['source_key']));key=m.quantkey(line);mid=x['source_move'];token='later_negative_credit_'+str(mid)
  alltemps=m.j.setdefault('temporary_negative_stock_adjustments',[])
  if any(r['token']==token and r['status']=='verified' for r in alltemps):continue
  credited=sum(r['delta'] for r in alltemps if r['status']=='verified' and tuple(r['key'])==key and any(e.get('source_move')==mid for e in r['source_evidence']))
  delta=round(x['negative_portion']-credited,2)
  if delta<=0:continue
  require(delta<=7 and x['source_before']-x['source_consumption']<0,'Negative proof invalid')
  require(m.b.read('stock.move',[x['target_move']],['state'])[0]['state']=='done','Consumption not replayed')
  pid,loc,lot,pkg,owner=key;require(not pkg and not owner,'Unexpected temporary dimensions');qdomain=[['company_id','=',1],['product_id','=',pid],['location_id','=',loc],['lot_id','=',lot],['package_id','=',False],['owner_id','=',False]]
  qs=m.b.search_read('stock.quant',qdomain,['quantity']);require(len(qs)==1,'Missing or multiple stock quants');current=qs[0]['quantity'];domain=[['company_id','=',1],['product_id','=',pid],['is_inventory','=',True]];before=m.b.call('stock.move','search',[domain])
  date=(datetime.strptime(x['date'],'%Y-%m-%d %H:%M:%S')-timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S');ref=f"PYSB-TEMP-NEG | v14 {x['source_document'][1]} | source move {mid} | incremental {delta} | REVIEW REQUIRED"
  evidence={'source_move':mid,'source_line_ids':[line['id']],'source_key':x['source_key'],'target_key':list(key),'source_quantity_before_move':x['source_before'],'source_required_base_qty':x['source_consumption'],'source_would_be_negative':True,'event':x['event']}
  note={'purpose':'TEMPORARY NEGATIVE-SOURCE CREDIT FOR ALREADY REPLAYED LATER CONSUMPTION; NOT A REAL SOURCE ADJUSTMENT','source_proof':x,'credited_before':credited,'negative_portion':x['negative_portion'],'incremental_credit':delta,'reason':'Earlier source document waited for another SKU; later already replayed source-negative move consumed physical stock. Complete its evidenced negative credit without duplicating that move.','effective_utc':date,'actual_created_utc':datetime.now(timezone.utc).isoformat(),'review_status':'TEMPORARY_PENDING_RECONCILIATION'}
  rec={'token':token,'event':x['event'],'key':list(key),'date':date,'delta':delta,'source_evidence':[evidence],'status':'intent','reference':ref,'approved_by':'Bruce','review_status':'TEMPORARY_PENDING_RECONCILIATION','not_an_actual_v14_inventory_adjustment':True,'note':note};alltemps.append(rec);m.persist()
  m.mutate('stock.quant','write',[[qs[0]['id']],{'inventory_quantity':current+delta}],{'context':{'inventory_mode':True}})
  try:m.mutate('stock.quant','action_apply_inventory',[[qs[0]['id']]],{'context':{'inventory_mode':True,'inventory_name':ref}})
  except Fault as e:
   if 'cannot marshal None' not in str(e):raise
  new=m.b.search_read('stock.move',domain,['state','quantity','location_id','location_dest_id','move_line_ids']);new=[v for v in new if v['id'] not in before];require(len(new)==1 and new[0]['state']=='done' and abs(new[0]['quantity']-delta)<1e-6,'Temporary result uncertain');v=new[0];require(rid(v['location_id'])==11 and rid(v['location_dest_id'])==loc,'Wrong temporary route')
  m.mutate('stock.move','write',[[v['id']],{'date':date,'origin':ref,'inventory_name':ref,'description_picking_manual':json.dumps(note,ensure_ascii=False)}]);m.mutate('stock.move.line','write',[v['move_line_ids'],{'date':date}]);m.mutate('ir.model.data','create',[{'module':'pysb_temporary_inventory','name':token,'model':'stock.move','res_id':v['id'],'noupdate':True}])
  require(abs(sum(a['quantity'] for a in m.b.search_read('stock.quant',qdomain,['quantity']))-current-delta)<1e-6,'Temporary quantity mismatch')
  rec.update(status='verified',target_move=v['id'],before_quantity=current,after_quantity=current+delta,deltas=[[[pid,11,lot,False,False],-delta],[list(key),delta]]);m.persist();print(json.dumps({'source_move':mid,'negative_portion':x['negative_portion'],'credited_before':credited,'incremental':delta,'target_adjustment':v['id']}),flush=True)
if __name__=='__main__':main()
