"""Repair staging-only finished-move preparation; keep consumed raw moves done.

Odoo 19 counts picked finished quantities as already produced before Mark Done.
Main finished lines must therefore remain unpicked until the standard button runs.
"""
import runpy,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[6];OUT=ROOT/'outputs/pysb-stock-migration-20261012'
H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/execute_pysb_stock_migration.py'))
def main():
 m=H['Migration']();require=H['require'];rid=H['rid']
 require(m.j.get('approved_two_decimal_rounding'),'Rounding approval missing')
 mos=m.b.read('mrp.production',list(m.maps['mrp.production'].values()),['state','product_id','product_qty','move_raw_ids','move_finished_ids','extra_cost'])
 inverse={t:s for s,t in m.maps['mrp.production'].items()};cancelled=[x for x in mos if x['state']=='cancel']
 require({x['id'] for x in cancelled}=={70,71,72},'Unexpected cancelled MO')
 repair=[]
 for target in cancelled:
  source=m.mos[inverse[target['id']]]
  raw=m.b.read('stock.move',target['move_raw_ids'],['state','quantity','value'])
  require(all(x['state']=='done' and x['quantity']>0 for x in raw),'Raw recovery state differs')
  finished=m.b.read('stock.move',target['move_finished_ids'],['state','quantity','move_line_ids'])
  require(all(x['state']=='cancel' and x['quantity']==0 and not x['move_line_ids'] for x in finished),'Finished recovery state differs')
  repair.append({'source_mo':source['id'],'target_mo':target['id'],'raw_already_done':raw,'finished_before':finished,'extra_cost_before':target['extra_cost'],'extra_cost_recovery':sum(x['value'] for x in raw)/source['product_qty']})
 m.j['MO_recovery']=repair;m.persist()
 for item in repair:
  source=m.mos[item['source_mo']];target=item['target_mo'];finishedids=[m.maps['stock.move'][i] for i in source['move_finished_ids'] if i in m.maps['stock.move']]
  m.mutate('stock.move','write',[finishedids,{'state':'confirmed','picked':False}])
  m.mutate('mrp.production','write',[[target],{'state':'confirmed','extra_cost':item['extra_cost_recovery'],'date_start':source['date_start'] or source['date_planned_start'],'date_finished':source['date_finished']}])
  lines=[x for x in m.ml.values() if rid(x['move_id']) in source['move_finished_ids'] and x['qty_done']>0]
  values=[{'company_id':1,'move_id':m.maps['stock.move'][rid(x['move_id'])],'product_id':m.maps['product.product'][rid(x['product_id'])],'product_uom_id':m.maps['uom.uom'][rid(x['product_uom_id'])],
   'location_id':m.maps['stock.location'][rid(x['location_id'])],'location_dest_id':m.maps['stock.location'][rid(x['location_dest_id'])],'quantity':x['qty_done'],'lot_id':m.maps['stock.lot'].get(rid(x['lot_id']),False),'picked':False,'date':x['date']} for x in lines]
  ids=m.mutate('stock.move.line','create',[values]);require(len(ids)==len(lines),'Missing restored finished lines')
  m.maps['stock.move.line'].update({x['id']:t for x,t in zip(lines,ids)});m.persist()
  # Original detail XML IDs were removed when the cancelled lines were deleted.
  m.attach('stock.move.line',[(x['id'],t) for x,t in zip(lines,ids)])
 main=[]
 for source in m.mos.values():
  if source['id'] not in m.maps['mrp.production']:continue
  main.extend(m.maps['stock.move'][i] for i in source['move_finished_ids'] if i in m.maps['stock.move'] and rid(m.mm[i]['product_id'])==rid(source['product_id']))
 for batch in H['chunks'](main,100):m.mutate('stock.move','write',[batch,{'picked':False}])
 states=m.b.read('mrp.production',list(m.maps['mrp.production'].values()),['state','qty_produced'])
 require(all(x['state'] in ['confirmed','progress','to_close'] and x['qty_produced']==0 for x in states),'Finished preparation still counted as produced')
 m.j['MO_finished_preparation_corrected']=True;m.persist();print(json.dumps({'restored_MO':len(repair),'finished_moves_unpicked':len(main),'raw_consumption_repeated':False}),flush=True)
if __name__=='__main__':main()
