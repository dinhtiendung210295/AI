"""Read-only evidence for original moves of unresolved in-scope returns."""
import json
import runpy
from pathlib import Path
BASE=Path(__file__).parent
I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'))
OUT=I['OUT']
def load(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def rid(x):return x[0] if isinstance(x,list) and x else x or False

def main():
    coverage=load('after-run-stock-coverage.json')
    source={x['id']:x for x in load('source-moves.json')}
    pending=[source[x['source_move_id']] for x in coverage['results'] if x['category']=='return' and x['status']=='unresolved']
    origins=sorted({rid(x['origin_returned_move_id']) for x in pending if x['origin_returned_move_id']})
    outside=[sid for sid in origins if sid not in source]
    a=I['ReadOnly']('v14-prod',('http://175.145.85.151','paoyeang_live'))
    b=I['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    extra=a.read('stock.move',outside,list(next(iter(source.values()))))
    extra_lines=a.read('stock.move.line',sorted({i for x in extra for i in x['move_line_ids']}),list(load('source-move-lines.json')[0]))
    names=['stock_move_'+str(sid) for sid in origins]
    records=b.scan('ir.model.data',[['module','=','pysb_v14'],['model','=','stock.move'],['name','in',names]],['name','model','res_id'])
    target=b.read('stock.move',sorted({x['res_id'] for x in records}),['name','state','company_id','date','product_id','product_uom','quantity','product_uom_qty','location_id','location_dest_id','picking_id','move_line_ids','origin_returned_move_id','sale_line_id','purchase_line_id'])
    details=b.read('stock.move.line',sorted({i for x in target for i in x['move_line_ids']}),['state','company_id','date','product_id','product_uom_id','quantity','location_id','location_dest_id','lot_id','owner_id','package_id','result_package_id'])
    I['save']('return-origin-live-evidence.json',{'read_only':True,'source_pending_return_moves':[x['id'] for x in pending],'source_origin_ids':origins,'source_origins_outside_frozen_scope':extra,'source_origin_outside_details':extra_lines,'target_xmlids':records,'target_origins':target,'target_details':details,'policy':'Dependency evidence only. No original transaction outside frozen scope is created or changed; mapping alone does not prove completion.'})
    print(json.dumps({'pending_returns':len(pending),'originals':len(origins),'outside_originals':len(outside),'target_originals_with_xmlid':len(target)}),flush=True)
if __name__=='__main__':main()
