"""Use existing cleaned v19 SO shipping/vendor partners on migrated stock headers."""
import runpy,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[6];OUT=ROOT/'outputs/pysb-stock-migration-20261012'
H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/execute_pysb_stock_migration.py'))
def main():
 m=H['Migration']();rid=H['rid'];index=H['index'];ad=H['load']('v14-prod-dependencies.json');sd=index(ad['so']);pd=index(ad['po']);sl=index(m.sa['sol']);pl=index(ad['pol'])
 tso=index(m.b.read('sale.order',[m.maps['sale.order'][s] for s in sd],['company_id','partner_shipping_id']));tpo=index(m.b.read('purchase.order',[m.maps['purchase.order'][s] for s in pd],['company_id','partner_id']))
 byname={x['name']:('so',x['id']) for x in sd.values()};byname.update({x['name']:('po',x['id']) for x in pd.values()});bymove={}
 source_pick_names={x['name']:x for x in m.sp.values()}
 def origin_order(p,seen=None):
  seen=set() if seen is None else seen
  if p['id'] in seen:return None
  seen.add(p['id']);origin=p['origin'] or ''
  if origin in byname:return byname[origin]
  prior=source_pick_names.get(origin.removeprefix('Return of '))
  return origin_order(prior,seen) if prior else None
 for move in m.sm.values():
  order=None
  if move['sale_line_id'] and rid(move['sale_line_id']) in sl:order=('so',rid(sl[rid(move['sale_line_id'])]['order_id']))
  elif move['purchase_line_id'] and rid(move['purchase_line_id']) in pl:order=('po',rid(pl[rid(move['purchase_line_id'])]['order_id']))
  if order:bymove[move['id']]=order
 current=index(m.b.read('stock.picking',list(m.maps['stock.picking'].values()),['company_id','partner_id']));changes=[];exceptions=[]
 for source,target in m.maps['stock.picking'].items():
  p=m.sp[source]
  if not p['partner_id']:desired=False
  else:
   order=origin_order(p);orders=set()
   for i in p['move_lines']:
    if i in bymove:orders.add(bymove[i])
    elif i in m.sm and rid(m.sm[i]['origin_returned_move_id']) in bymove:orders.add(bymove[rid(m.sm[i]['origin_returned_move_id'])])
   if not order and len(orders)==1:order=next(iter(orders))
   if order:
    kind,oid=order;record=tso[m.maps['sale.order'][oid]] if kind=='so' else tpo[m.maps['purchase.order'][oid]]
    H['require'](rid(record['company_id'])==1,'Wrong company');desired=rid(record['partner_shipping_id' if kind=='so' else 'partner_id'])
   else:desired=m.maps['res.partner'].get(rid(p['partner_id']),False)
   if not desired:exceptions.append({'source_picking':source,'target_picking':target,'source_partner':p['partner_id'],'origin':p['origin']})
  H['require'](rid(current[target]['company_id'])==1,'Wrong stock company')
  if rid(current[target]['partner_id'])!=desired:changes.append([target,desired])
 m.matrix('stock.picking',['.id','partner_id/.id'],changes);m.j['picking_partner_alignment']={'updated':len(changes),'exceptions':exceptions,'basis':'Existing cleaned v19 SO partner_shipping_id / PO partner_id; no contact creation or edits.'};m.persist()
 moves=index(m.b.read('stock.move',list(m.maps['stock.move'].values()),['picking_id','company_id']))
 lines=m.b.read('stock.move.line',list(m.maps['stock.move.line'].values()),['move_id','picking_id','company_id']);links=[]
 for line in lines:
  move=moves[rid(line['move_id'])];desired=rid(move['picking_id'])
  H['require'](rid(line['company_id'])==1 and rid(move['company_id'])==1,'Wrong stock line company')
  if rid(line['picking_id'])!=desired:links.append([line['id'],desired])
 m.matrix('stock.move.line',['.id','picking_id/.id'],links);m.j['stock_line_picking_alignment']={'updated':len(links),'basis':'picking_id must match its existing stock.move picking_id'};m.persist()
 print(json.dumps(m.j['picking_partner_alignment'],ensure_ascii=False),flush=True)
if __name__=='__main__':main()
