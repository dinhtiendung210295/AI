"""Read-back recovery and batched preparation of old-PO standalone receipts."""
import json,runpy,html,re
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[6]
H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/complete_pysb_stock_migration.py'))
def main():
 m=H['Completion']();rid=H['rid'];req=H['require'];save=H['H']['save'];d=H['load']('old-po-late-receipts-discovery.json');moves={x['id']:x for x in d['moves']};picks={x['id']:x for x in d['pickings']};lines=defaultdict(list)
 for x in d['lines']:
  if x['qty_done']>0:lines[rid(x['move_id'])].append(x)
 records=m.j['standalone_source_receipts'];known={x['source_move']:x['target_move'] for x in records};known.update(m.maps['stock.move']);m.uoms=H['index'](m.b.search_read('uom.uom',[],['name','factor','rounding']))
 by_pick=defaultdict(list)
 for sid,s in moves.items():
  if sid in m.maps['stock.move'] or not lines[sid]:continue
  rec=next((r for r in records if r['source_move']==sid),None)
  if rec and rec['status']=='verified':continue
  req(not rec or rec['status']=='prepared','Unexpected interrupted move; read-back required')
  req(rid(s['product_id']) in m.maps['product.product'],'Missing product mapping')
  for x in lines[sid]:req(not x['package_id'] and not x['result_package_id'] and not x['owner_id'],'Unexpected package/owner');req(not x['lot_id'] or rid(x['lot_id']) in m.maps['stock.lot'],'Missing lot mapping')
  by_pick[rid(s['picking_id'])].append(sid)
 targettypes={x['id']:x for x in m.b.search_read('stock.picking.type',[['company_id','=',1]],['code'])}
 existing=m.b.search_read('stock.picking',[['company_id','=',1],['origin','=like','PYSB-OLD-PO-SUPPLY%']],['note','state','move_ids'])
 targetpick={}
 for p in existing:
  if not p['note']:
   req(p['state']=='cancel','Unidentified active standalone picking needs review');continue
  note=json.loads(html.unescape(re.sub('<[^>]+>','',p['note'])));sid=note['source_picking']['id']
  if sid in by_pick: req(sid not in targetpick,'Duplicate source picking target');targetpick[sid]=p['id'];req(p['state'] not in ['done','cancel'],'Picking already finalized')
 # All previously prepared lines must still match exactly; no retry by guessing.
 prepared=[r for r in records if r['status']=='prepared'];actual=m.b.read('stock.move.line',[i for r in prepared for i in r['target_lines']],['move_id','quantity','lot_id','product_id','location_id','location_dest_id','picked'])
 grouped=defaultdict(list)
 for x in actual:grouped[rid(x['move_id'])].append(x)
 for r in prepared:
  expected=sorted((m.effective_qty(x),m.maps['stock.lot'].get(rid(x['lot_id']),False)) for x in lines[r['source_move']]);got=sorted((x['quantity'],rid(x['lot_id'])) for x in grouped[r['target_move']]);req(expected==got and all(x['picked'] for x in grouped[r['target_move']]),'Prepared lines changed')
 missingp=[p for p in by_pick if p not in targetpick];values=[]
 for p in missingp:
  sp=picks[p];s=moves[by_pick[p][0]];typ=m.maps['stock.picking.type'][rid(sp['picking_type_id'])];req(typ in targettypes,'Missing picking type')
  ref=f"PYSB-OLD-PO-SUPPLY | v14 {sp['name']} | {sp['origin']}";note={'purpose':'REAL V14 LATE RECEIPT / RELATED RETURN FROM PRE-JULY PO; NO PO IMPORT','source_database':m.a.db,'company_id':1,'source_picking':sp,'source_moves':by_pick[p]}
  values.append({'company_id':1,'picking_type_id':typ,'location_id':m.maps['stock.location'][rid(s['location_id'])],'location_dest_id':m.maps['stock.location'][rid(s['location_dest_id'])],'scheduled_date':sp['date_done'],'origin':ref,'note':json.dumps(note,ensure_ascii=False),'move_type':'direct'})
 if values:
  ids=m.mutate('stock.picking','create',[values]);req(len(ids)==len(values),'Picking create length mismatch');targetpick.update(zip(missingp,ids))
 external=m.b.search_read('ir.model.data',[['module','=','pysb_standalone_supply'],['model','=','stock.picking']],['name','res_id']);ext={x['name']:x['res_id'] for x in external};values=[]
 for p,t in targetpick.items():
  name='source_picking_'+str(p)
  if name in ext:req(ext[name]==t,'External picking conflict')
  else:values.append({'module':'pysb_standalone_supply','name':name,'model':'stock.picking','res_id':t,'noupdate':True})
 if values:m.mutate('ir.model.data','create',[values])
 missing=[i for ids in by_pick.values() for i in ids if i not in known];values=[]
 for sid in missing:
  s=moves[sid];p=rid(s['picking_id']);sp=picks[p];ref=f"PYSB-OLD-PO-SUPPLY | v14 {sp['name']} | {sp['origin']}";v=m.mv(s,picking=targetpick[p]);v.update(purchase_line_id=False,sale_line_id=False,origin=ref,description_picking_manual=json.dumps({'source_move':s,'source_lines':lines[sid]},ensure_ascii=False));values.append(v)
 for start in range(0,len(missing),100):
  batch=missing[start:start+100];ids=m.mutate('stock.move','create',[values[start:start+100]]);req(len(ids)==len(batch),'Move create length mismatch')
  for sid,mid in zip(batch,ids):
   s=moves[sid];p=rid(s['picking_id']);known[sid]=mid;records.append({'source_move':sid,'source_picking':p,'target_picking':targetpick[p],'target_move':mid,'status':'created','date':s['date'],'source_qty':sum(x['qty_done'] for x in lines[sid]),'reference':values[missing.index(sid)]['origin'],'note':{'source_picking':picks[p],'source_move':s}})
  m.persist();print(json.dumps({'moves_created':start+len(batch),'total':len(missing)}),flush=True)
 values=[];owners=[]
 for r in records:
  if r['status']!='created':continue
  for x in lines[r['source_move']]:
   values.append({'company_id':1,'picking_id':r['target_picking'],'move_id':r['target_move'],'product_id':m.maps['product.product'][rid(x['product_id'])],'product_uom_id':m.maps['uom.uom'][rid(x['product_uom_id'])],'quantity':m.effective_qty(x),'picked':True,'location_id':m.maps['stock.location'][rid(x['location_id'])],'location_dest_id':m.maps['stock.location'][rid(x['location_dest_id'])],'lot_id':m.maps['stock.lot'].get(rid(x['lot_id']),False),'date':r['date']});owners.append(r)
 for start in range(0,len(values),200):
  batch=values[start:start+200];ids=m.mutate('stock.move.line','create',[batch]);req(len(ids)==len(batch),'Line create length mismatch')
  for r,lid in zip(owners[start:start+200],ids):r.setdefault('target_lines',[]).append(lid)
  m.persist();print(json.dumps({'lines_created':start+len(batch),'total':len(values)}),flush=True)
 for r in records:
  if r['status']=='created':
   deltas=defaultdict(float)
   for x in lines[r['source_move']]:deltas[m.quantkey(x)]-=m.qty(x);deltas[m.quantkey(x,True)]+=m.qty(x)
   r.update(status='prepared',deltas=[[list(k),v] for k,v in deltas.items()])
 m.persist()
 # Import links in one batch before validating: native push skips an existing
 # destination move, preventing duplicate storage operations.
 linkrows=[]
 for r in records:
  sid=r['source_move']
  if r['status']!='prepared' or sid not in moves:continue
  dest=[known[i] for i in moves[sid]['move_dest_ids'] if i in known]
  if dest:linkrows.append([r['target_move'],','.join(str(i) for i in dest)])
 if linkrows:m.matrix('stock.move',['.id','move_dest_ids/.id'],linkrows)
 pending=[(p,ids) for p,ids in by_pick.items() if any(r['source_move'] in ids and r['status']=='prepared' for r in records)]
 # Reuse the native validation and read-back logic from the first implementation.
 code=(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/import_pysb_all_old_po_receipts.py').read_text(encoding='utf8');section=code[code.index(' for p,ids in sorted(pending,'):code.index(" m.j['old_po_receipt_exceptions']")]
 environment={**globals(),**locals()}
 exec(compile('if True:\n'+section,'<native-receipt-validation>','exec'),environment,environment)
 m.j['old_po_receipt_exceptions']=[];m.persist();save(m.path.parent/'all-old-po-receipts-report.json',{'records':records,'exceptions':[]});print('Finished batched standalone receipt replay',flush=True)
if __name__=='__main__':main()
