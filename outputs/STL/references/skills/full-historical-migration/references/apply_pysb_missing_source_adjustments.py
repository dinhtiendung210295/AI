"""Replay evidenced missing v14 inventory deltas, with existing products/lots only."""
import runpy,json
from pathlib import Path
from decimal import Decimal,ROUND_HALF_UP
from xmlrpc.client import Fault
ROOT=Path(__file__).resolve().parents[6]
H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/execute_pysb_stock_migration.py'))
def main():
 m=H['Migration']();rid=H['rid'];require=H['require'];c=H['load']('missing-source-adjustment-candidates.json');sources=H['index'](H['load']('supplementary-source-adjustment-details.json'))
 products=H['index'](m.b.read('product.product',sorted({x['target_key'][0] for x in c}),['tracking','uom_id','is_storable']));uoms=H['index'](m.b.search_read('uom.uom',[],['factor','rounding']))
 for x in sorted(c,key=lambda x:(x['date'],x['source_move'])):
  sid=x['source_move'];source=sources[sid];key=x['target_key'];pid,location,lot,package,owner=key
  require(source['state']=='done' and rid(source['company_id'])==1 and rid(source['location_id'])==14,'Source is not a done company-1 inventory increase')
  require(not x['same_date_qty_candidates'],'Possible duplicate requires review')
  product=products[pid];unit=uoms[m.maps['uom.uom'][rid(source['product_uom'])]];base=uoms[rid(product['uom_id'])];qty=float(Decimal(str(source['quantity_done']*unit['factor']/base['factor'])).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP))
  require(product['is_storable'] and (product['tracking']=='none' or bool(lot)) and (product['tracking']!='serial' or abs(qty-1)<1e-6),'Unsupported tracking or storage')
  require(m.maps['stock.location'][rid(source['location_dest_id'])]==location,'Wrong location')
  external=H['H']['external'](m.b,'stock.move').get(sid)
  if external:continue
  domain=[['company_id','=',1],['product_id','=',pid],['is_inventory','=',True]];before=m.b.call('stock.move','search',[domain])
  qdomain=[['company_id','=',1],['product_id','=',pid],['location_id','=',location],['lot_id','=',lot],['package_id','=',package],['owner_id','=',False]]
  quants=m.b.search_read('stock.quant',qdomain,['quantity']);require(len(quants)<=1,'Multiple quants need review')
  if not quants:
   qid=m.mutate('stock.quant','create',[{'product_id':pid,'location_id':location,'lot_id':lot,'package_id':package}],{'context':{'inventory_mode':True}});current=0.0
  else:qid=quants[0]['id'];current=quants[0]['quantity']
  record={'source_move':sid,'source_line':x['source_line'],'date':source['date'],'target_key':key,'before_quantity':current,'delta':qty,'status':'intent'};m.j.setdefault('supplementary_adjustment_operations',[]).append(record);m.persist()
  m.mutate('stock.quant','write',[[qid],{'inventory_quantity':current+qty}],{'context':{'inventory_mode':True}})
  try:m.mutate('stock.quant','action_apply_inventory',[[qid]],{'context':{'inventory_mode':True,'inventory_name':f"v14 {sid}: {source['name']}"}})
  except Fault as exc:
   if 'cannot marshal None' not in str(exc):raise
  moves=m.b.search_read('stock.move',domain,['state','quantity','location_id','location_dest_id','move_line_ids']);new=[a for a in moves if a['id'] not in before]
  require(len(new)==1 and new[0]['state']=='done' and abs(new[0]['quantity']-qty)<1e-6 and rid(new[0]['location_dest_id'])==location and rid(new[0]['location_id'])==11,'Uncertain inventory result')
  move=new[0];m.attach('stock.move',[(sid,move['id'])]);m.mutate('stock.move','write',[[move['id']],{'date':source['date']}]);m.mutate('stock.move.line','write',[move['move_line_ids'],{'date':source['date']}])
  actual=m.b.search_read('stock.quant',qdomain,['quantity']);require(abs(sum(a['quantity'] for a in actual)-(current+qty))<1e-6,'Wrong inventory delta')
  record.update(status='verified',target_move=move['id'],after_quantity=current+qty)
  m.j.setdefault('supplementary_inventory_adjustments',[]).append({'source_move':sid,'target_move':move['id'],'source_qty':source['quantity_done'],'target_qty':qty,'date':source['date'],'deltas':[[[pid,11,lot,False,False],-qty],[key,qty]]});m.persist()
  print(json.dumps({'source':sid,'target':move['id'],'delta':qty,'status':'verified'}),flush=True)
 H['save'](m.path.parent/'supplementary-adjustment-results.json',m.j['supplementary_inventory_adjustments'])
if __name__=='__main__':main()
