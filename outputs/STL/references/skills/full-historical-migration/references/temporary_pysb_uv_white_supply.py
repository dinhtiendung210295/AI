"""Explicitly approved temporary replacement for missing PO-04604 receipt."""
from complete_pysb_stock_migration import Completion,rid,require,load
from datetime import datetime,timedelta
from xmlrpc.client import Fault
import json
def main():
 m=Completion();token='uv_white_po04604_temporary_supply';existing=[r for r in m.j.get('temporary_negative_stock_adjustments',[]) if r['token']==token];require(not existing,'Already started: inspect before retry')
 d=load('supporting-stock-discovery.json');sources=[s for s in d['moves'] if s['id'] in [529698,529699,529700]];require(len(sources)==3 and all(rid(s['company_id'])==1 and s['state']=='done' for s in sources),'Invalid source group')
 key=[118976,5,28195,False,False];lot=m.b.read('stock.lot',[key[2]],['name','product_id','company_id'])[0];require(rid(lot['product_id'])==key[0] and rid(lot['company_id'])==1,'Wrong lot')
 qdomain=[['company_id','=',1],['product_id','=',key[0]],['location_id','=',key[1]],['lot_id','=',key[2]],['package_id','=',False],['owner_id','=',False]];qs=m.b.search_read('stock.quant',qdomain,['quantity']);require(len(qs)<=1,'Ambiguous quant');current=qs[0]['quantity'] if qs else 0;delta=round(4-current,2);require(delta>0 and delta<=4,'Supply changed; review shortage')
 date=(datetime.strptime(min(s['date'] for s in sources),'%Y-%m-%d %H:%M:%S')-timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S');ref='PYSB-TEMP-SUPPLY | UV WHITE | PO-04604 NOT IMPORTED | v14 inventory 3977 | REVIEW REQUIRED'
 note={'purpose':'TEMPORARY SUPPLY, NOT ACTUAL V14 INVENTORY ADJUSTMENT','approved_by':'Bruce','approval':'hãy điều chỉnh tạm trước','missing_source_receipt':'PO-04604, 24 September 2026; not imported','source_adjustment_moves':[529698,529699,529700],'target_lot':lot,'delta':delta,'effective_utc':date,'follow_up':'When the real PO-04604 receipt is migrated, reverse this temporary supply with an explicit counterpart to avoid duplicate quantity. Do not reverse now: it funds the actual source lot adjustment.'}
 rec={'token':token,'key':key,'date':date,'delta':delta,'source_evidence':[],'status':'intent','reference':ref,'approved_by':'Bruce','review_status':'TEMPORARY_PENDING_REAL_RECEIPT_RECONCILIATION','not_an_actual_v14_inventory_adjustment':True,'note':note};m.j.setdefault('temporary_negative_stock_adjustments',[]).append(rec);m.persist()
 domain=[['company_id','=',1],['product_id','=',key[0]],['is_inventory','=',True]];before=set(m.b.call('stock.move','search',[domain]));qid=qs[0]['id'] if qs else m.mutate('stock.quant','create',[{'product_id':key[0],'location_id':key[1],'lot_id':key[2]}],{'context':{'inventory_mode':True}})
 m.mutate('stock.quant','write',[[qid],{'inventory_quantity':current+delta}],{'context':{'inventory_mode':True}})
 try:m.mutate('stock.quant','action_apply_inventory',[[qid]],{'context':{'inventory_mode':True,'inventory_name':ref}})
 except Fault as e:
  if 'cannot marshal None' not in str(e):raise
 new=[x for x in m.b.search_read('stock.move',domain,['state','quantity','location_id','location_dest_id','move_line_ids']) if x['id'] not in before];require(len(new)==1,'Uncertain result; no retry');v=new[0];require(v['state']=='done' and abs(v['quantity']-delta)<1e-6 and (rid(v['location_id']),rid(v['location_dest_id']))==(11,5),'Wrong supply')
 m.mutate('stock.move','write',[[v['id']],{'date':date,'origin':ref,'inventory_name':ref,'description_picking_manual':json.dumps(note,ensure_ascii=False)}]);m.mutate('stock.move.line','write',[v['move_line_ids'],{'date':date}]);require(abs(sum(q['quantity'] for q in m.b.search_read('stock.quant',qdomain,['quantity']))-current-delta)<1e-6,'Quantity mismatch')
 rec.update(status='verified',target_move=v['id'],before_quantity=current,after_quantity=current+delta,deltas=[[key,delta],[[key[0],11,key[2],False,False],-delta]]);m.persist();print(json.dumps({'temporary_move':v['id'],'delta':delta,'lot':lot['name'],'effective_utc':date}))
if __name__=='__main__':main()
