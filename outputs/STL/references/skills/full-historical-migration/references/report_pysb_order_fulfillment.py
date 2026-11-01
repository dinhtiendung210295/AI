"""Read-only SO delivered/PO received comparison after historical stock migration."""
import runpy,json,socket
from pathlib import Path
ROOT=Path(__file__).resolve().parents[6];OUT=ROOT/'outputs/pysb-stock-migration-20261012'
H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/confirm_pysb_july_po_staging.py'))
def main():
 socket.setdefaulttimeout(120);a=H['Reader'](ROOT/'mcp-server-odoo/envs/v14-prod/.env');b=H['Reader'](ROOT/'mcp-server-odoo/envs/v19-staging/.env');p=json.loads((OUT/'execution-manifest.json').read_text(encoding='utf8'));report={'rows':[],'summary':{}}
 for model,qty,ordered,unit in [('sale.order.line','qty_delivered','product_uom_qty','product_uom'),('purchase.order.line','qty_received','product_qty','product_uom')]:
  mapping={int(s):t for s,t in p['maps'][model].items()}
  # Include only the authoritative imported order-line scope, not unrelated import examples.
  sourcefile='v14-prod-snapshot.json' if model=='sale.order.line' else 'v14-prod-dependencies.json';key='sol' if model=='sale.order.line' else 'pol'
  ids=[x['id'] for x in json.loads((OUT/sourcefile).read_text(encoding='utf8'))[key]]
  source=a.read(model,ids,['order_id','product_id','display_type',qty,ordered,unit]);target=b.read(model,[mapping[i] for i in ids],['order_id','product_id','display_type',qty,ordered,'product_uom_id']);ti={x['id']:x for x in target}
  types={x['id']:x['type'] for x in b.read('product.product',{x['product_id'][0] for x in target if x['product_id']},['type'])};rows=[]
  for s in source:
   t=ti[mapping[s['id']]]
   if s['display_type'] or not t['product_id'] or types[t['product_id'][0]]=='service':continue
   rows.append({'model':model,'source_line':s['id'],'target_line':t['id'],'source_order':s['order_id'][1],'target_order':t['order_id'][1],'product':s['product_id'][1],'ordered_source':s[ordered],'ordered_target':t[ordered],'fulfilled_source':s[qty],'fulfilled_target':t[qty],'delta':t[qty]-s[qty],'match':abs(t[qty]-s[qty])<=0.00501})
  report['rows']+=rows;report['summary'][model]={'goods_lines':len(rows),'matched':sum(x['match'] for x in rows),'mismatch':sum(not x['match'] for x in rows)};print(model,report['summary'][model],flush=True)
 H['save'](OUT/'order-fulfillment-report.json',report)
if __name__=='__main__':
 import sys
 if '--production-evidence-dir' in sys.argv:
  import argparse
  parser=argparse.ArgumentParser()
  parser.add_argument('--production-evidence-dir',type=Path,required=True)
  args=parser.parse_args()
  verify=runpy.run_path(str(Path(__file__).with_name('verify_pysb_prod_orders.py')))
  raise SystemExit(verify['run'](args.production_evidence_dir))
 main()
