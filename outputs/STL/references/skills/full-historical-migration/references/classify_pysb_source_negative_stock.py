"""Evidence source stock immediately before consumption for pending shortages."""
import runpy,json,bisect
from pathlib import Path
from collections import defaultdict
from decimal import Decimal,ROUND_HALF_UP
ROOT=Path(__file__).resolve().parents[6]
H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/complete_pysb_stock_migration.py'))
def main():
 m=H['Completion']();rid=H['rid'];require=H['require'];events=[x for x in m.j['event_results'].values() if x['status']=='blocked_stock'];pids=set()
 for event in events:
  for x in m.expected(event):pids.add(rid(x['product_id']))
 products=H['index'](m.a.read('product.product',sorted(pids),['name','uom_id']));uoms=H['index'](m.a.search_read('uom.uom',[],['factor','rounding']))
 quants=m.a.search_read('stock.quant',[['company_id','=',1],['product_id','in',sorted(pids)]],['product_id','location_id','lot_id','package_id','owner_id','quantity'])
 lines=m.a.search_read('stock.move.line',[['company_id','=',1],['product_id','in',sorted(pids)],['state','=','done'],['move_id.date','>=','2026-06-30 16:00:00'],['qty_done','>',0]],['move_id','product_id','product_uom_id','qty_done','location_id','location_dest_id','lot_id','package_id','result_package_id','owner_id','date'])
 require(len(lines)<100000,'Source ledger truncated');moves=H['index'](m.a.read('stock.move',sorted({rid(x['move_id']) for x in lines}),['date','state','company_id']))
 current=defaultdict(float);timeline=defaultdict(list)
 for q in quants:current[tuple(rid(q[k]) for k in ['product_id','location_id','lot_id','package_id','owner_id'])]+=q['quantity']
 def qty(x):
  base=uoms[rid(products[rid(x['product_id'])]['uom_id'])];value=x['qty_done']*base['factor']/uoms[rid(x['product_uom_id'])]['factor'];return float(Decimal(str(value/base['rounding'])).quantize(Decimal('1'),rounding=ROUND_HALF_UP))*base['rounding']
 for x in lines:
  mid=rid(x['move_id']);order=(moves[mid]['date'],mid);pid=rid(x['product_id']);lot=rid(x['lot_id']);owner=rid(x['owner_id']);value=qty(x)
  timeline[(pid,rid(x['location_id']),lot,rid(x['package_id']),owner)].append((order,-value))
  timeline[(pid,rid(x['location_dest_id']),lot,rid(x['result_package_id']),owner)].append((order,value))
 indexed={}
 for key,changes in timeline.items():
  changes.sort();orders=[];prefix=[0.0]
  for order,delta in changes:orders.append(order);prefix.append(prefix[-1]+delta)
  indexed[key]=(orders,prefix)
 rows=[]
 for event in sorted(events,key=lambda e:(e['date'],e['source'])):
  shortage={tuple(x['key']):x for x in event['shortage']};groups=defaultdict(list)
  for x in m.expected(event):
   if m.quantkey(x) in shortage:groups[(rid(x['move_id']),m.quantkey(x))].append(x)
  for (mid,targetkey),parts in groups.items():
   x=parts[0];sourcekey=(rid(x['product_id']),rid(x['location_id']),rid(x['lot_id']),rid(x['package_id']),rid(x['owner_id']));source=m.sm.get(mid) or m.mm[mid];order=(source['date'],mid);orders,prefix=indexed.get(sourcekey,([], [0.0]));pos=bisect.bisect_left(orders,order);available=current[sourcekey]-(prefix[-1]-prefix[pos]);required=sum(qty(x) for x in parts)
   rows.append({'event':event,'source_move':mid,'source_line_ids':[x['id'] for x in parts],'source_key':sourcekey,'target_key':targetkey,'source_move_date':source['date'],'source_product_name':products[sourcekey[0]]['name'],'source_quantity_before_move':available,'source_required_base_qty':required,'source_current_quantity':current[sourcekey],'source_would_be_negative':available-required < -1e-5,'target_shortage':shortage[targetkey]})
 output={'database':m.a.db,'company_id':1,'source_quants':quants,'source_done_lines':lines,'source_done_moves':list(moves.values()),'rows':rows,'summary':{'pending_events':len(events),'shortage_move_rows':len(rows),'source_negative_rows':sum(x['source_would_be_negative'] for x in rows),'other_rows':sum(not x['source_would_be_negative'] for x in rows)}}
 H['H']['save'](m.path.parent/'source-negative-stock-classification.json',output);print(json.dumps(output['summary']),flush=True)
if __name__=='__main__':main()
