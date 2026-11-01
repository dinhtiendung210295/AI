"""Quantity-only opening/closing comparison by product and lot name."""
import runpy,json,html
from pathlib import Path
from collections import defaultdict
from decimal import Decimal,ROUND_HALF_UP
ROOT=Path(__file__).resolve().parents[6];OUT=ROOT/'outputs/pysb-stock-migration-20261012'
H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/confirm_pysb_july_po_staging.py'))
def load(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def rid(v):return v[0] if v else False
def main():
 a=H['Reader'](ROOT/'mcp-server-odoo/envs/v14-prod/.env');b=H['Reader'](ROOT/'mcp-server-odoo/envs/v19-staging/.env');p=load('execution-manifest.json');mapping={int(s):t for s,t in p['maps']['product.product'].items()};reverse={t:s for s,t in mapping.items()}
 src=load('v14-prod-dependencies.json');su={x['id']:x for x in src['uoms']};sp={x['id']:x for x in src['products']};sp.update({x['id']:x for x in load('mo-details.json')['products']})
 sp.update({x['id']:x for x in a.read('product.product',list(mapping),['name','uom_id'])})
 locations={}
 for label,reader in [('source',a),('target',b)]:
  warehouses=reader.search_read('stock.warehouse',[['company_id','=',1]],['view_location_id'])
  locations[label]={x['id'] for x in reader.search_read('stock.location',[['id','child_of',[rid(x['view_location_id']) for x in warehouses]]],['usage'])}

 sq=a.search_read('stock.quant',[['company_id','=',1],['product_id','in',list(mapping)]],['product_id','location_id','lot_id','quantity']);sm=a.search_read('stock.move.line',[['company_id','=',1],['product_id','in',list(mapping)],['state','=','done'],['move_id.date','>=','2026-06-30 16:00:00'],['qty_done','>',0]],['move_id','product_id','product_uom_id','qty_done','location_id','location_dest_id','lot_id','date']);sl={x['id']:x['name'] for x in a.read('stock.production.lot',{rid(x['lot_id']) for x in sq+sm if x['lot_id']},['name'])}
 tq=b.search_read('stock.quant',[['company_id','=',1],['product_id','in',list(reverse)]],['product_id','location_id','lot_id','quantity']);tm=b.search_read('stock.move.line',[['company_id','=',1],['product_id','in',list(reverse)],['state','=','done'],['move_id.date','>=','2026-06-30 16:00:00']],['move_id','product_id','location_id','location_dest_id','lot_id','date','quantity_product_uom'])
 H['require'](len(tm)<100000 and len(sm)<100000,'Lot ledger truncated');
 for reader,lines in [(a,sm),(b,tm)]:
  dates={x['id']:x['date'] for x in reader.read('stock.move',{rid(x['move_id']) for x in lines},['date'])}
  for x in lines:x['date']=dates[rid(x['move_id'])]
 tl={x['id']:x['name'] for x in b.read('stock.lot',{rid(x['lot_id']) for x in tq+tm if x['lot_id']},['name'])};stored={x['id']:x['is_storable'] for x in b.read('product.product',list(reverse),['is_storable'])}
 aliases=load('execution-journal.json').get('approved_opening_lot_aliases',[])
 for alias in aliases:
  if alias['source_lot'] in sl:sl[alias['source_lot']]=alias['target_name']
 H['save'](OUT/'closing-lot-report-inputs.json',{'source_quants':sq,'source_lines':sm,'source_lots':sl,'source_products':sp,'source_uoms':su,'target_quants':tq,'target_lines':tm,'target_lots':tl,'warehouse_locations':{k:sorted(v) for k,v in locations.items()},'stored':stored,'mapping':mapping})
 data={}
 for label,quants,moves,lots in [('source',sq,sm,sl),('target',tq,tm,tl)]:
  balances=defaultdict(float)
  for q in quants:
   pid=rid(q['product_id']);sid=pid if label=='source' else reverse[pid]
   if stored[mapping[sid]] and rid(q['location_id']) in locations[label]:balances[(sid,lots.get(rid(q['lot_id']),''))]+=q['quantity']
  for period,cutoff in [('opening','2026-06-30 16:00:00'),('closing','2026-07-31 16:00:00')]:
   result=defaultdict(float,balances)
   for x in moves:
    if x['date']<cutoff:continue
    pid=rid(x['product_id']);sid=pid if label=='source' else reverse[pid]
    if not stored[mapping[sid]]:continue
    if label=='target':qty=x['quantity_product_uom']
    else:
     base=su[rid(sp[sid]['uom_id'])];qty=x['qty_done']/su[rid(x['product_uom_id'])]['factor']*base['factor'];qty=float(Decimal(str(qty/base['rounding'])).quantize(Decimal('1'),rounding=ROUND_HALF_UP))*base['rounding']
    key=(sid,lots.get(rid(x['lot_id']),''))
    if rid(x['location_id']) in locations[label]:result[key]+=qty
    if rid(x['location_dest_id']) in locations[label]:result[key]-=qty
   data[(label,period)]=result
 rows=[]
 for key in sorted(set().union(*(set(v) for v in data.values()))):
  s,lot=key;so=data['source','opening'][key];to=data['target','opening'][key];sc=data['source','closing'][key];tc=data['target','closing'][key]
  if max(abs(so),abs(to),abs(sc),abs(tc))<1e-6:continue
  rows.append({'source_product':s,'target_product':mapping[s],'product':sp[s]['name'],'lot':lot,'source_opening':so,'target_opening':to,'opening_delta':to-so,'source_closing':sc,'target_closing':tc,'closing_delta':tc-sc})
 summary={'product_lot_rows':len(rows),'opening_mismatches':sum(abs(x['opening_delta'])>1e-5 for x in rows),'closing_mismatches':sum(abs(x['closing_delta'])>1e-5 for x in rows),'valuation_compared':False,'scope':'Mapped products, company warehouse location trees, is_storable only; lot names within each product; quantity in product base unit; stock.move date for cutoffs, as in native qty_available.'}
 crosscheck=[]
 if (OUT/'product-opening-closing-report.json').exists():
  sums=defaultdict(lambda:defaultdict(float))
  for row in rows:
   for k in ['source_opening','target_opening','source_closing','target_closing']:sums[row['source_product']][k]+=row[k]
  for row in load('product-opening-closing-report.json')['rows']:
   if not stored[mapping[row['source_product']]]:continue
   for k in ['source_opening','target_opening','source_closing','target_closing']:
    value=sums[row['source_product']][k]
    if abs(value-row[k])>0.001:crosscheck.append({'source_product':row['source_product'],'period':k,'lot_sum':value,'native_qty':row[k]})
 summary['lot_totals_match_native_product_report']=not crosscheck
 H['save'](OUT/'lot-opening-closing-report.json',{'summary':summary,'rows':rows,'approved_lot_aliases':aliases,'native_product_crosscheck':{'differences':crosscheck,'totals_match':not crosscheck}})
 esc=lambda v:html.escape(str(v));body=''.join('<tr>'+''.join('<td>'+esc(x[k])+'</td>' for k in ['product','lot','source_opening','target_opening','opening_delta','source_closing','target_closing','closing_delta'])+'</tr>' for x in rows)
 (OUT/'lot-opening-closing-report.html').write_text('<!doctype html><meta charset="utf-8"><title>Pao Yeang - Lot quantities</title><style>body{font:14px Arial;margin:24px}table{border-collapse:collapse}td,th{padding:6px;border:1px solid #ddd}</style><h1>T?n ??u v? cu?i th?ng 7 theo s?n ph?m / lot</h1><p>Ch? so s? l??ng, kh?ng so ??nh gi?. V? tr? n?i b?, s?n ph?m qu?n l? t?n. ??n v? c? s? c?a s?n ph?m.</p><pre>'+esc(summary)+'</pre><table><tr><th>S?n ph?m</th><th>Lot</th><th>??u v14</th><th>??u v19</th><th>L?ch ??u</th><th>Cu?i v14</th><th>Cu?i v19</th><th>L?ch cu?i</th></tr>'+body+'</table>',encoding='utf8');print(json.dumps(summary),flush=True)
if __name__=='__main__':main()
