"""Read-only source/target stock migration inventory, company 1 only."""
import json, runpy, socket
from pathlib import Path
from collections import Counter
ROOT = Path(__file__).resolve().parents[6]
H = runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/confirm_pysb_july_po_staging.py'))
Reader, save, require = [H[k] for k in ['Reader','save','require']]
def main():
    socket.setdefaulttimeout(90)
    out = ROOT/'outputs/pysb-stock-migration-20261012'
    so = json.loads((ROOT/'outputs/pysb-so-confirm-20261012-staging/so-delivery-handoff.json').read_text(encoding='utf8'))
    po = json.loads((ROOT/'outputs/pysb-po-confirm-20261012-staging/po-receipt-handoff.json').read_text(encoding='utf8'))
    summary = {}
    for version in ['v14-prod','v19-staging']:
        r = Reader(ROOT/f'mcp-server-odoo/envs/{version}/.env')
        require(r.db == ('paoyeang_live' if version=='v14-prod' else 'py19-staging-39654560'), 'Wrong database')
        source = version=='v14-prod'
        data = {'database':r.db,'company':r.read('res.company',[1],['name']), 'schemas':{}}
        models = ['sale.order.line','purchase.order','stock.picking','stock.move','stock.move.line','stock.lot' if not source else 'stock.production.lot','stock.location','stock.picking.type','stock.route' if not source else 'stock.location.route','repacking.order','repacking.order.line','mrp.production']
        for model in models:
            print(json.dumps({'version':version,'schema':model}),flush=True)
            data['schemas'][model] = r.call(model,'fields_get',[],{'attributes':['type','relation','readonly','store','selection']})
        def read(model, ids=None, domain=None):
            meta=data['schemas'][model]
            candidates={
                'sale.order.line':'order_id product_id product_uom product_uom_id product_uom_qty route_id route_ids display_type',
                'purchase.order':'name company_id picking_ids order_line',
                'stock.picking':'name state company_id picking_type_id location_id location_dest_id origin scheduled_date date_done move_ids move_lines backorder_id partner_id',
                'stock.move':'name state company_id picking_id sale_line_id purchase_line_id product_id product_uom product_uom_qty quantity quantity_done location_id location_dest_id move_orig_ids move_dest_ids move_line_ids origin_returned_move_id returned_move_ids date raw_material_production_id production_id',
                'stock.move.line':'move_id picking_id company_id product_id product_uom_id qty_done quantity lot_id lot_name location_id location_dest_id date owner_id package_id result_package_id state',
                'stock.location':'name complete_name usage company_id location_id active',
                'stock.picking.type':'name code company_id warehouse_id default_location_src_id default_location_dest_id use_create_lots use_existing_lots',
                'repacking.order':'name company_id state date_confirm date_complete reference_no task_description product_id qty_consume product_uom_id lot_consume_id picking_type_id location_src_id location_dest_id production_location_id origin repacking_line_ids',
                'repacking.order.line':'repacking_order_id product_id product_uom_id qty_produce packing_ratio qty_consume_actual qty_consume_actual_uom qty_consume_expect lot_produce_id mrp_production_id state',
            }.get(model,'name product_id company_id ref rule_ids')
            fields=['id']+[k for k in candidates.split() if k in meta]
            print(json.dumps({'version':version,'read':model,'count':len(ids) if ids is not None else 'search'}),flush=True)
            return r.read(model,ids,fields) if ids is not None else r.search_read(model,domain,fields)
        def checkpoint(phase):
            save(out/f'{version}-snapshot.json',data)
            print(json.dumps({'version':version,'phase':phase}),flush=True)
        soids=[x['source_id' if source else 'target_id'] for x in so]
        poids=[x['v14_id' if source else 'v19_id'] for x in po]
        orders=r.read('sale.order',soids,['picking_ids','order_line'])
        pos=read('purchase.order',poids)
        data['sol']=read('sale.order.line',[i for x in orders for i in x['order_line']])
        picks=set(i for x in orders+pos for i in x['picking_ids'])
        data['pickings']=read('stock.picking',sorted(picks))
        mids=[i for p in data['pickings'] for i in p['move_lines' if source else 'move_ids']]
        data['moves']=read('stock.move',mids)
        data['move_lines']=read('stock.move.line',[i for m in data['moves'] for i in m['move_line_ids']])
        checkpoint('root_stock_read')
        # Entire connected chains (internal steps/backorders/returns) are discovered separately from roots.
        seen=set(mids); frontier=list(mids)
        while frontier:
            print(json.dumps({'version':version,'chain_frontier':len(frontier)}),flush=True)
            rows=r.read('stock.move',frontier,['move_orig_ids','move_dest_ids','origin_returned_move_id','returned_move_ids','company_id'])
            extra=set(i for x in rows for k in ['move_orig_ids','move_dest_ids','returned_move_ids'] for i in x[k])
            extra.update(x['origin_returned_move_id'][0] for x in rows if x['origin_returned_move_id'])
            frontier=sorted(extra-seen); seen.update(frontier)
        extras=read('stock.move',sorted(seen-set(mids)))
        require(all(x['company_id'][0]==1 for x in data['moves']+extras),'Cross-company chain')
        data['chain_moves']=extras
        ep=set(x['picking_id'][0] for x in extras if x['picking_id'])-picks
        data['chain_pickings']=read('stock.picking',sorted(ep))
        data['chain_move_lines']=read('stock.move.line',[i for x in extras for i in x['move_line_ids']])
        checkpoint('chain_stock_read')
        data['repack']=read('repacking.order',domain=[['company_id','=',1],'|','&',['date_confirm','>=','2026-06-30 16:00:00'],['date_confirm','<','2026-07-31 16:00:00'],'&',['date_complete','>=','2026-06-30 16:00:00'],['date_complete','<','2026-07-31 16:00:00']])
        data['repack_lines']=read('repacking.order.line',[i for x in data['repack'] for i in x['repacking_line_ids']])
        checkpoint('repack_read')
        data['locations']=read('stock.location',domain=['|',['company_id','=',1],['company_id','=',False]])
        data['picking_types']=read('stock.picking.type',domain=[['company_id','=',1]])
        routem='stock.location.route' if source else 'stock.route'
        data['routes']=read(routem,domain=['|',['company_id','=',1],['company_id','=',False]])
        lotm='stock.production.lot' if source else 'stock.lot'
        lotids=set(x['lot_id'][0] for x in data['move_lines']+data['chain_move_lines'] if x['lot_id'])
        lotids.update(x['lot_consume_id'][0] for x in data['repack'] if x['lot_consume_id'])
        lotids.update(x['lot_produce_id'][0] for x in data['repack_lines'] if x['lot_produce_id'])
        data['lots']=read(lotm,sorted(lotids))
        data['external_ids']=r.search_read('ir.model.data',[['module','=','pysb_v14']],['name','model','res_id']) if not source else []
        save(out/f'{version}-snapshot.json',data)
        summary[version]={'company':data['company'],'pickings':dict(Counter(x['state'] for x in data['pickings'])), 'chain_pickings':len(data['chain_pickings']), 'moves':len(data['moves']), 'move_lines':len(data['move_lines']), 'repack':dict(Counter(x['state'] for x in data['repack'])), 'lots':len(data['lots'])}
        print(json.dumps({version:summary[version]},ensure_ascii=False),flush=True)
    save(out/'inspection-summary.json',summary)
if __name__=='__main__': main()
