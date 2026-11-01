"""Resume only the two previously excluded MOs after operator tracking change."""
import copy,json
from execute_pysb_stock_migration import Migration,require,rid,save,OUT

def main():
 m=Migration();source_ids=[21709,21789];pid=m.maps['product.product'][42847]
 fresh=m.b.read('product.product',[pid],['tracking','write_date'])[0]
 require(fresh['tracking']=='none','Operator tracking change not saved')
 approved=m.j.setdefault('approved_operator_master_changes',[])
 if not any(e.get('target_product')==pid and e.get('value')=='none' for e in approved):approved.append({'source_product':42847,'target_product':pid,'field':'tracking','value':'none','evidence':fresh,'reason':'Operator confirmed saved quantity tracking for historical untracked material'})
 for p in m.p['target_products']:
  if p['id']==pid:p['tracking']='none'
 for p in m.j['baseline_products']:
  if p['id']==pid:p['tracking']='none'
 m.p['blocked_mo']=[s for s in m.p['blocked_mo'] if s not in source_ids]
 m.p['mo_exceptions']=[e for e in m.p.get('mo_exceptions',[]) if not(e.get('source_id')==42847 and e.get('reason')=='tracking_mismatch')]
 save(OUT/'execution-manifest.json',m.p);m.persist()
 original=m.mos;m.mos={s:original[s] for s in source_ids};phases=copy.deepcopy(m.j['phases'])
 m.j['phases']['mo']=False;m.j['reviewed_mo_resume']=True
 try:m.prepare_mos('field')
 finally:m.mos=original;m.j['phases']=phases;m.persist()
 mids={i for s in source_ids for k in ['move_raw_ids','move_finished_ids'] for i in original[s][k] if m.mm[i]['state']=='done'}
 pending=[x for x in m.ml.values() if rid(x['move_id']) in mids and x['qty_done']>0 and x['id'] not in m.maps['stock.move.line']]
 existing=m.b.search_read('stock.move.line',[['move_id','in',[m.maps['stock.move'][i] for i in mids]],['company_id','=',1]],['state'])
 require(all(x['state']!='done' for x in existing) or not pending,'Already completed MO needs readback')
 if pending:
  require(not any(x['id'] in m.maps['stock.move.line'].values() for x in existing),'Partial detail preparation needs review')
  if existing:m.mutate('stock.move.line','unlink',[[x['id'] for x in existing]])
  values=[]
  for x in pending:
   require(not x['owner_id'],'Unexpected owner')
   primary_finished=bool(m.mm[rid(x['move_id'])]['production_id']) and rid(x['product_id'])==rid(original[rid(m.mm[rid(x['move_id'])]['production_id'])]['product_id'])
   values.append({'company_id':1,'move_id':m.maps['stock.move'][rid(x['move_id'])],'product_id':m.maps['product.product'][rid(x['product_id'])],'product_uom_id':m.maps['uom.uom'][rid(x['product_uom_id'])],'location_id':m.maps['stock.location'][rid(x['location_id'])],'location_dest_id':m.maps['stock.location'][rid(x['location_dest_id'])],'lot_id':m.maps['stock.lot'].get(rid(x['lot_id']),False),'quantity':x['qty_done'],'picked':not primary_finished,'date':x['date'],'package_id':m.maps['stock.package'].get(rid(x['package_id']),False),'result_package_id':m.maps['stock.package'].get(rid(x['result_package_id']),False)})
  ids=m.mutate('stock.move.line','create',[values]);require(len(ids)==len(pending),'Incomplete detail creation')
  m.maps['stock.move.line'].update({x['id']:t for x,t in zip(pending,ids)});m.persist();m.attach('stock.move.line',[(x['id'],t) for x,t in zip(pending,ids)])
 save(OUT/'resumed-untracked-material-mo-event-keys.json',['mo:'+str(s) for s in source_ids])
 print(json.dumps({'prepared':[{'source':s,'target':m.maps['mrp.production'][s],'name':original[s]['name']} for s in source_ids]}))
if __name__=='__main__':main()
