"""Resolve mapped NOVA and replace untouched default routes with exact source routes."""
from execute_pysb_stock_migration import Migration,rid,require,index,save,OUT
import json
def main(fixed_sources=None,old_targets=None,journal_key='consignment_route_resume'):
 m=Migration();fixed_sources=fixed_sources or {184943,185163,185164,185165,185166,185215,185557,185558,185559,185562,185563,185564};old_targets=old_targets or [1472,1473,1474,1475,1595,1596,1597,1598,1599,1600,1601,1602]
 require(not m.j.get(journal_key),'Already started; readback review required')
 old=m.b.read('stock.picking',old_targets,['state','move_ids']);moves=m.b.read('stock.move',[i for p in old for i in p['move_ids']],['state','quantity','move_line_ids'])
 require(all(x['state'] not in ['done','cancel'] for x in old+moves),'Original route already posted')
 oldlines=m.b.read('stock.move.line',[i for x in moves for i in x['move_line_ids']],['state','picked'])
 require(all(x['state']!='done' and not x['picked'] for x in oldlines),'Original route has picked operations')
 source_moves=[s for s in m.sm.values() if rid(s['picking_id']) in fixed_sources]
 for x in m.sl.values():
  if rid(x['move_id']) in {s['id'] for s in source_moves} and x['qty_done']>0:
   require(not x['owner_id'],'Owner mismatch');require(m.product[m.maps['product.product'][rid(x['product_id'])]]['tracking']=='none' or x['lot_id'],'Unresolved source lot')
 m.j[journal_key]={'status':'intent','old_pickings':old,'old_moves':moves,'source_pickings':sorted(fixed_sources)};m.persist()
 m.mutate('stock.picking','action_cancel',[old_targets])
 records=m.j['supporting_source_transfers'];pm=m.maps['stock.picking'];mm=m.maps['stock.move'];lm=m.maps['stock.move.line']
 for r in records:
  if r['source_picking'] in fixed_sources and r['source_picking'] in [184943,185215]:
   require(r['status']=='verified','NOVA supporting picking not verified');pm[r['source_picking']]=r['target_picking'];mm[r['source_move']]=r['target_move']
   xs=[x for x in m.sl.values() if rid(x['move_id'])==r['source_move'] and x['qty_done']>0];require(len(xs)==len(r['target_lines'])==1,'Unexpected NOVA line split');lm[xs[0]['id']]=r['target_lines'][0]
   r['status']='integrated_original_scope';m.j['completed_events'].append('picking:'+str(r['source_picking']));p=m.sp[r['source_picking']]
   m.j['event_results']['picking:'+str(p['id'])]={'status':'done','kind':'picking','source':p['id'],'target':pm[p['id']],'date':p['date_done'],'reference':p['name']}
 m.persist()
 newp=[m.sp[s] for s in sorted(fixed_sources) if s not in pm]
 vals=[{'company_id':1,'picking_type_id':m.maps['stock.picking.type'][rid(p['picking_type_id'])],'location_id':m.maps['stock.location'][rid(p['location_id'])],'location_dest_id':m.maps['stock.location'][rid(p['location_dest_id'])],'scheduled_date':p['scheduled_date'],'origin':p['origin'],'partner_id':m.maps['res.partner'].get(rid(p['partner_id']),False),'note':'PYSB source route replay: replaces untouched default-route pickings; source '+p['name']} for p in newp]
 tids=m.mutate('stock.picking','create',[vals]);require(len(tids)==len(newp),'Incomplete picking creation');pm.update({p['id']:t for p,t in zip(newp,tids)});m.persist()
 newm=[s for s in source_moves if s['id'] not in mm];tids=m.mutate('stock.move','create',[[m.mv(s,picking=pm[rid(s['picking_id'])],state='cancel' if s['state']=='cancel' else 'confirmed') for s in newm]]);require(len(tids)==len(newm),'Incomplete move creation');mm.update({s['id']:t for s,t in zip(newm,tids)});m.persist()
 known={r['source_move']:r['target_move'] for r in m.j.get('standalone_source_receipts',[])+records};known.update(mm)
 m.matrix('stock.move',['.id','move_orig_ids/.id','move_dest_ids/.id','origin_returned_move_id/.id'],[[mm[s['id']],','.join(str(known[i]) for i in s['move_orig_ids'] if i in known),','.join(str(known[i]) for i in s['move_dest_ids'] if i in known),known.get(rid(s['origin_returned_move_id']),False)] for s in newm])
 xs=[x for x in m.sl.values() if rid(x['move_id']) in {s['id'] for s in newm} and x['qty_done']>0]
 vals=[{'company_id':1,'picking_id':pm[rid(x['picking_id'])],'move_id':mm[rid(x['move_id'])],'product_id':m.maps['product.product'][rid(x['product_id'])],'product_uom_id':m.maps['uom.uom'][rid(x['product_uom_id'])],'location_id':m.maps['stock.location'][rid(x['location_id'])],'location_dest_id':m.maps['stock.location'][rid(x['location_dest_id'])],'lot_id':m.maps['stock.lot'].get(rid(x['lot_id']),False),'quantity':x['qty_done'],'picked':True,'date':x['date'],'package_id':m.maps['stock.package'].get(rid(x['package_id']),False),'result_package_id':m.maps['stock.package'].get(rid(x['result_package_id']),False)} for x in xs]
 tids=m.mutate('stock.move.line','create',[vals]);require(len(tids)==len(xs),'Incomplete lines');lm.update({x['id']:t for x,t in zip(xs,tids)});m.persist()
 m.attach('stock.picking',[(s,pm[s]) for s in fixed_sources]);m.attach('stock.move',[(s['id'],mm[s['id']]) for s in source_moves]);m.attach('stock.move.line',[(x['id'],lm[x['id']]) for x in m.sl.values() if rid(x['move_id']) in {s['id'] for s in source_moves} and x['qty_done']>0])
 resolved=[e for e in m.p['exceptions'] if e['type']=='unmatched_existing_move' and e.get('target') in {i for p in old for i in p['move_ids']} or e['type']=='missing_mapping' and e.get('model')=='stock.location' and e.get('id')==170]
 m.p['exceptions']=[e for e in m.p['exceptions'] if e not in resolved];m.j[journal_key].update(status='prepared',resolved_exceptions=resolved);save(OUT/'execution-manifest.json',m.p);m.persist();print(json.dumps({'prepared_source_pickings':len(fixed_sources),'new_pickings':len(newp),'replaced_untouched_pickings':len(old)}))
if __name__=='__main__':main()
