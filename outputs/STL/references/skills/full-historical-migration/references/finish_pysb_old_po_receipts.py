"""Complete prepared old-PO chains in batches, with read-back and UTC dates."""
import json,runpy
from collections import defaultdict,Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[6]
H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/complete_pysb_stock_migration.py'))
def main():
 m=H['Completion']();rid=H['rid'];req=H['require'];save=H['H']['save'];d=H['load']('old-po-late-receipts-discovery.json');sources={x['id']:x for x in d['moves']};sp={x['id']:x for x in d['pickings']};records=m.j['standalone_source_receipts'];m.uoms=H['index'](m.b.search_read('uom.uom',[],['name','factor','rounding']));groups=defaultdict(list);src_lines=defaultdict(list)
 for x in d['lines']:
  if x['qty_done']>0:src_lines[rid(x['move_id'])].append(x)
 for r in records:
  if r['source_move'] in sources:groups[r['target_picking']].append(r)
 known={r['source_move']:r['target_move'] for r in records};known.update(m.maps['stock.move']);links=[]
 for r in records:
  sid=r['source_move']
  if sid not in sources or r['status']=='verified':continue
  s=sources[sid];dest=[known[i] for i in s['move_dest_ids'] if i in known]
  if not dest and m.locations[m.maps['stock.location'][rid(s['location_id'])]]['usage']=='supplier':
   origin=sp[rid(s['picking_id'])]['origin'];lots={rid(x['lot_id']) for x in src_lines[sid]}
   dest=[known[i] for i,t in sources.items() if i in known and rid(t['product_id'])==rid(s['product_id']) and rid(t['location_id'])==rid(s['location_dest_id']) and sp[rid(t['picking_id'])]['origin']==origin and lots & {rid(x['lot_id']) for x in src_lines[i]}]
  if dest:links.append([r['target_move'],','.join(str(i) for i in dest)])
 if links:m.matrix('stock.move',['.id','move_dest_ids/.id'],links)
 states={x['id']:x for x in m.b.read('stock.picking',list(groups),['state','move_ids'])}
 # The stopped writer may already have validated a picking. Read state first.
 for p,rs in groups.items():
  req(set(states[p]['move_ids'])=={r['target_move'] for r in rs},'Unexpected extra move')
  if states[p]['state']=='done':
   for r in rs:r['status']='native_done_pending_dates'
 byday=defaultdict(list)
 for p,rs in groups.items():
  if states[p]['state']=='done':continue
  req(states[p]['state'] not in ['cancel','draft'],'Unexpected picking state')
  byday[sp[rs[0]['source_picking']]['date_done'][:10]].append(p)
 m.persist()
 for day,remaining in sorted(byday.items()):
  while remaining:
   balance=m.ledger(m.b.search_read('stock.quant',[['company_id','=',1]],['product_id','location_id','lot_id','package_id','owner_id','quantity']));chosen=[]
   for p in sorted(remaining,key=lambda p:sp[groups[p][0]['source_picking']]['date_done']):
    need=defaultdict(float)
    for r in groups[p]:
     for x in src_lines[r['source_move']]:
      key=m.quantkey(x)
      if m.product[key[0]]['is_storable'] and m.locations[key[1]]['usage'] in ['internal','transit']:need[key]+=m.qty(x)
    shortage=[{'key':list(k),'available':balance[k],'required':q} for k,q in need.items() if balance[k]+1e-6<q]
    if shortage:
     for r in groups[p]:r['shortage']=shortage
     continue
    for k,q in need.items():balance[k]-=q
    chosen.append(p)
    if len(chosen)==30:break
   if not chosen:
    for p in remaining:
     for r in groups[p]:r['status']='blocked_stock'
    m.persist();break
   result=m.mutate('stock.picking','button_validate',[chosen],{'context':{'skip_backorder':True,'skip_redirection':True,'picking_ids_not_to_backorder':chosen}})
   if isinstance(result,dict) and result.get('res_model')=='expiry.picking.confirmation':
    ctx=result.get('context',{});m.j.setdefault('historical_expiry_acknowledgements',[]).append({'kind':'old_po_receipt','targets':chosen,'warning':result});m.persist()
    wizard=m.mutate('expiry.picking.confirmation','create',[{'lot_ids':ctx.get('default_lot_ids',[]),'picking_ids':[(6,0,chosen)]}],{'context':ctx})
    m.mutate('expiry.picking.confirmation','process',[[wizard]],{'context':ctx})
   elif isinstance(result,dict) and result.get('res_model'):raise RuntimeError('Unexpected native wizard; read-back before retry: '+str(result))
   actual=m.b.read('stock.picking',chosen,['state','move_ids']);req(all(x['state']=='done' and set(x['move_ids'])=={r['target_move'] for r in groups[x['id']]} for x in actual),'Native batch not fully done')
   for p in chosen:
    for r in groups[p]:r['status']='native_done_pending_dates';r.pop('shortage',None)
   m.persist();remaining=[p for p in remaining if p not in chosen];print(json.dumps({'day':day,'native_done_picks':len(chosen),'remaining_day':len(remaining)}),flush=True)
 done=[r for r in records if r['status']=='native_done_pending_dates'];pickrows={r['target_picking']:sp[r['source_picking']]['date_done'] for r in done}
 if pickrows:m.matrix('stock.picking',['.id','date_done'],[[p,date] for p,date in pickrows.items()])
 if done:m.matrix('stock.move',['.id','date'],[[r['target_move'],r['date']] for r in done]);m.matrix('stock.move.line',['.id','date'],[[i,r['date']] for r in done for i in r.get('target_lines',[r.get('target_line')]) if i])
 actual=m.b.read('stock.move.line',[i for r in done for i in r.get('target_lines',[r.get('target_line')]) if i],['move_id','product_id','product_uom_id','location_id','location_dest_id','lot_id','quantity','date','state']);by_move=defaultdict(list)
 for x in actual:by_move[rid(x['move_id'])].append(x)
 for r in done:
  expected=sorted((m.maps['product.product'][rid(x['product_id'])],m.maps['uom.uom'][rid(x['product_uom_id'])],m.maps['stock.location'][rid(x['location_id'])],m.maps['stock.location'][rid(x['location_dest_id'])],m.maps['stock.lot'].get(rid(x['lot_id']),False),m.effective_qty(x)) for x in src_lines[r['source_move']]);got=sorted(tuple(rid(x[k]) for k in ['product_id','product_uom_id','location_id','location_dest_id','lot_id'])+(x['quantity'],) for x in by_move[r['target_move']]);req(expected==got and all(x['state']=='done' and x['date']==r['date'] for x in by_move[r['target_move']]),'Final source/target detail mismatch')
  r.update(status='verified',target_qty=sum(x['quantity'] for x in by_move[r['target_move']]),after_lines=by_move[r['target_move']])
 m.persist()
 # Cancel only untouched push-route duplicates outside the planned target IDs.
 all_known_pickings={r['target_picking'] for r in records}
 extras=m.b.search_read('stock.picking',[['company_id','=',1],['origin','=like','PYSB-OLD-PO-SUPPLY%'],['id','not in',sorted(all_known_pickings)],['state','!=','cancel']],['state','move_ids'])
 if extras:
  ms=m.b.read('stock.move',[i for p in extras for i in p['move_ids']],['state','quantity','move_line_ids','rule_id']);req(all(x['state'] not in ['done','cancel'] and x['quantity']==0 and not x['move_line_ids'] and x['rule_id'] for x in ms),'Unexpected push picking; do not cancel')
  m.j['old_po_auto_push_cleanup']={'before_pickings':extras,'before_moves':ms};m.persist();m.mutate('stock.picking','action_cancel',[[p['id'] for p in extras]]);m.j['old_po_auto_push_cleanup']['after']=m.b.read('stock.picking',[p['id'] for p in extras],['state']);m.persist()
 m.j['old_po_receipt_exceptions']=[];m.persist();save(m.path.parent/'all-old-po-receipts-report.json',{'records':records,'summary':dict(Counter(r['status'] for r in records))});print(json.dumps({'standalone_records':dict(Counter(r['status'] for r in records))}),flush=True)
if __name__=='__main__':main()
