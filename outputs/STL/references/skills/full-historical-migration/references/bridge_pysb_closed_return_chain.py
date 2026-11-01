"""Approved +1/-1 stock bridge, native chronological validation, exact read-back."""
from complete_pysb_stock_migration import Completion,rid,require
from datetime import datetime,timedelta
from xmlrpc.client import Fault
import json
def main():
 m=Completion();key=[115572,5,26672,False,False];source=[185315,185316,185319,185320]
 rows=[r for r in m.j['supporting_source_transfers'] if r['source_picking'] in source]
 groups={s:[r for r in rows if r['source_picking']==s] for s in source};require(all(len(v)==2 for v in groups.values()),'Wrong chain')
 ops=m.j.setdefault('approved_closed_loop_stock_bridge',{})
 require(not ops,'Bridge already started: inspect journal before rerunning')
 qdomain=[['company_id','=',1],['product_id','=',key[0]],['location_id','=',key[1]],['lot_id','=',key[2]],['package_id','=',False],['owner_id','=',False]]
 def quantity():
  qs=m.b.search_read('stock.quant',qdomain,['quantity']);require(len(qs)==1,'Ambiguous quant');return qs[0]
 baseline=quantity()['quantity'];require(abs(baseline)<1e-6,'Stock changed; reconsider bridge')
 ops.update(status='intent',key=key,before_quantity=baseline,source_pickings=source,approved_by='Bruce',approval='Cho phép cấp tạm rồi trừ lại ngay',reason='v14 has historical supply; later replayed deliveries consumed current stock. Replay zero-net transfer/return loop, then reverse bridge immediately. Not a real v14 adjustment.');m.persist()
 def adjust(delta,date,token,opposing=None):
  q=quantity();domain=[['company_id','=',1],['product_id','=',key[0]],['is_inventory','=',True]];old=set(m.b.call('stock.move','search',[domain]));ref='PYSB-TEMP-BRIDGE | SO-53565 | lot 20250627 | '+token+' | counterpart '+str(opposing or 'pending')
  rec={'token':token,'key':key,'date':date,'delta':delta,'source_evidence':[],'status':'intent','reference':ref,'approved_by':'Bruce','review_status':'PAIRED_BRIDGE_PENDING_REVERSAL','not_an_actual_v14_inventory_adjustment':True,'note':dict(ops)};m.j.setdefault('temporary_negative_stock_adjustments',[]).append(rec);m.persist()
  m.mutate('stock.quant','write',[[q['id']],{'inventory_quantity':q['quantity']+delta}],{'context':{'inventory_mode':True}})
  try:m.mutate('stock.quant','action_apply_inventory',[[q['id']]],{'context':{'inventory_mode':True,'inventory_name':ref}})
  except Fault as e:
   if 'cannot marshal None' not in str(e):raise
  new=[x for x in m.b.search_read('stock.move',domain,['state','quantity','location_id','location_dest_id','move_line_ids']) if x['id'] not in old];require(len(new)==1,'Read-back uncertain');v=new[0];require(v['state']=='done' and abs(v['quantity']-abs(delta))<1e-6,'Adjustment mismatch');require((rid(v['location_id']),rid(v['location_dest_id']))==((11,5) if delta>0 else (5,11)),'Wrong bridge route')
  m.mutate('stock.move','write',[[v['id']],{'date':date,'origin':ref,'inventory_name':ref,'description_picking_manual':json.dumps(dict(ops),ensure_ascii=False)}]);m.mutate('stock.move.line','write',[v['move_line_ids'],{'date':date}]);require(abs(quantity()['quantity']-q['quantity']-delta)<1e-6,'Quant mismatch')
  rec.update(status='verified',target_move=v['id'],before_quantity=q['quantity'],after_quantity=quantity()['quantity'],deltas=[[key,delta],[[key[0],11,key[2],False,False],-delta]]);m.persist();return rec
 credit=adjust(1,'2026-07-22 01:31:05','closed_loop_53565_credit');ops.update(status='credited',credit_move=credit['target_move']);m.persist()
 for s in source:
  rs=groups[s];p=rs[0]['target_picking'];state=m.b.read('stock.picking',[p],['state'])[0]['state'];require(state not in ['done','cancel'],'Unexpected state')
  result=m.mutate('stock.picking','button_validate',[[p]],{'context':{'skip_backorder':True,'skip_redirection':True,'picking_ids_not_to_backorder':[p]}});require(not isinstance(result,dict) or not result.get('res_model'),'Wizard: inspect before retry');require(m.b.read('stock.picking',[p],['state'])[0]['state']=='done','Not done');ops.setdefault('done_pickings',[]).append(p);m.persist();print(json.dumps({'source_picking':s,'target_picking':p,'state':'done'}),flush=True)
 require(abs(quantity()['quantity']-baseline-1)<1e-6,'Loop changed bridge stock')
 debit=adjust(-1,'2026-07-22 01:37:16','closed_loop_53565_reversal',credit['target_move']);credit['counterpart_move']=debit['target_move'];debit['counterpart_move']=credit['target_move']
 for r in [credit,debit]:
  r['review_status']='PAIRED_BRIDGE_REVERSED';m.mutate('stock.move','write',[[r['target_move']],{'description_picking_manual':json.dumps(r,ensure_ascii=False)}])
 require(abs(quantity()['quantity']-baseline)<1e-6,'Bridge not fully reversed');ops.update(status='verified_reversed',reversal_move=debit['target_move'],after_quantity=quantity()['quantity']);m.persist();print(json.dumps(ops))
if __name__=='__main__':main()
