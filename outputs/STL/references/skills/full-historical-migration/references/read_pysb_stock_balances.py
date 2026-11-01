"""Read full source quantity ledger for mapped products, for opening/closing gap reports."""
import runpy,json,socket
from pathlib import Path
ROOT=Path(__file__).resolve().parents[6];OUT=ROOT/'outputs/pysb-stock-migration-20261012'
H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/confirm_pysb_july_po_staging.py'))
def main():
 socket.setdefaulttimeout(120);r=H['Reader'](ROOT/'mcp-server-odoo/envs/v14-prod/.env');p=json.loads((OUT/'execution-manifest.json').read_text(encoding='utf8'));pids=[int(i) for i in p['maps']['product.product']]
 quants=r.search_read('stock.quant',[['company_id','=',1],['product_id','in',pids]],['product_id','location_id','lot_id','package_id','owner_id','quantity'])
 H['save'](OUT/'source-balance-quants.json',quants);print('source quants',len(quants),flush=True)
 lines=r.search_read('stock.move.line',[['company_id','=',1],['product_id','in',pids],['state','=','done'],['date','>=','2026-06-30 16:00:00'],['qty_done','>',0]],['move_id','picking_id','product_id','product_uom_id','qty_done','location_id','location_dest_id','lot_id','date','package_id','result_package_id','owner_id'])
 H['require'](len(lines)<100000,'Source ledger search truncated')
 H['save'](OUT/'source-balance-movements.json',lines)
 lots=r.read('stock.production.lot',{x['lot_id'][0] for x in quants+lines if x['lot_id']},['name','product_id','company_id'])
 H['save'](OUT/'source-balance-lots.json',lots)
 uid=r.read('res.users',[r.uid],['tz']);H['save'](OUT/'source-balance-context.json',{'user_timezone':uid[0]['tz'],'source_db':r.db,'company_id':1,'cutoff_opening_utc':'2026-06-30 16:00:00','cutoff_closing_utc':'2026-07-31 16:00:00'})
 print('source movements since July',len(lines),flush=True)
if __name__=='__main__':main()
