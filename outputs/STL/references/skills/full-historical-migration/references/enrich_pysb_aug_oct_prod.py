"""Read-only full stock documents and source/target master evidence for new run."""
import json
import runpy
import socket
from pathlib import Path

BASE = Path(__file__).resolve().parent
I = runpy.run_path(str(BASE / 'inspect_pysb_aug_oct_prod.py'))
ROOT, OUT, ReadOnly = I['ROOT'], I['OUT'], I['ReadOnly']
save = I['save']
def rid(v): return v[0] if isinstance(v, list) and v else v or False

def main():
    socket.setdefaulttimeout(120)
    moves = json.loads((OUT / 'source-moves.json').read_text(encoding='utf8'))
    lines = json.loads((OUT / 'source-move-lines.json').read_text(encoding='utf8'))
    a = ReadOnly('v14-prod', ('http://175.145.85.151', 'paoyeang_live'))
    b = ReadOnly('v19-prod', ('https://py19.odoo.com', 'py19-main-33843450'))
    picks = a.read('stock.picking', [rid(x['picking_id']) for x in moves if x.get('picking_id')], 'name state company_id picking_type_id location_id location_dest_id origin scheduled_date date_done move_lines backorder_id partner_id'.split())
    save('source-pickings.json', picks)
    mos = a.read('mrp.production', [rid(x.get('production_id') or x.get('raw_material_production_id')) for x in moves if x.get('production_id') or x.get('raw_material_production_id')], 'name state company_id product_id product_qty qty_produced product_uom_id date_start date_planned_start date_finished move_raw_ids move_finished_ids origin lot_producing_id bom_id'.split())
    save('source-mos.json', mos)
    all_moves = {i for p in picks for i in p['move_lines']}
    all_moves.update(i for mo in mos for key in ['move_raw_ids', 'move_finished_ids'] for i in mo[key])
    extras = all_moves - {x['id'] for x in moves}
    extra_moves = a.read('stock.move', extras, list(moves[0]))
    save('source-document-extra-moves.json', extra_moves)
    save('source-document-extra-lines.json', a.read('stock.move.line', [i for x in extra_moves for i in x['move_line_ids']], list(lines[0])))
    print('documents', len(picks), 'pickings', len(mos), 'MO; outside-scope document moves', len(extras), flush=True)
    for label, reader in [('source', a), ('target', b)]:
        for model, fields, domain in [
            ('stock.location', 'name complete_name usage company_id location_id active', ['|', ['company_id', '=', 1], ['company_id', '=', False]]),
            ('stock.picking.type', 'name code company_id warehouse_id default_location_src_id default_location_dest_id', [['company_id', '=', 1]]),
            ('uom.uom', 'name rounding factor factor_inv relative_factor relative_uom_id category_id uom_type', []),
            ('stock.warehouse', 'name code company_id', [['company_id', '=', 1]]),
            ('account.journal', 'name code type company_id currency_id', [['company_id', '=', 1]]),
            ('res.currency', 'name rounding active', []),
        ]:
            save(label + '-' + model + '.json', reader.scan(model, domain, fields.split()))
        lot_model = 'stock.production.lot' if label == 'source' else 'stock.lot'
        if label == 'source':
            lots = reader.read(lot_model, [rid(x['lot_id']) for x in lines if x.get('lot_id')], ['name', 'product_id', 'company_id'])
            products = reader.read('product.product', [rid(x['product_id']) for x in moves], 'name default_code barcode company_id uom_id type tracking active'.split())
            save('source-products.json', products)
        else:
            lots = reader.scan(lot_model, [['company_id', '=', 1]], ['name', 'product_id', 'company_id'])
        save(label + '-lots.json', lots)
        models = ['product.product', 'product.template', 'uom.uom', 'stock.location', 'stock.picking.type', 'stock.warehouse', 'res.partner', 'account.account', 'account.tax', 'account.journal', 'res.currency', 'account.payment.term', 'res.users']
        save(label + '-master-external-ids.json', reader.scan('ir.model.data', [['model', 'in', models]], ['model', 'module', 'name', 'res_id']))
        print(label, 'master evidence saved', flush=True)

if __name__ == '__main__': main()
