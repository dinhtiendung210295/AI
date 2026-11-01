"""Read-only production inventory. Never executes business workflow methods."""
import json
import runpy
import socket
import time
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
HELPER = ROOT / '.agents/skills/FC+TC/6-Data migration/so-po-migration/scripts/test_prepare_july_2026_so_po_migration.py'
Reader = runpy.run_path(str(HELPER))['OdooReader']
OUT = ROOT / 'outputs/pysb-aug-oct-prod-20261024'

def save(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    temp = path.with_suffix('.tmp')
    stock_journals={'independent-delivery-journal.json','independent-receipts-journal.json','independent-mo-journal.json','independent-inventory-journal.json'}
    formatting={'separators':(',',':')} if name in stock_journals else {'indent':2}
    temp.write_text(json.dumps(data, ensure_ascii=False, **formatting), encoding='utf8')
    for attempt in range(20):
        try:
            temp.replace(path)
            break
        except PermissionError:
            if attempt==19:raise
            time.sleep(0.1)

class ReadOnly:
    def __init__(self, env, identity):
        self.r = Reader(ROOT / 'mcp-server-odoo/envs' / env / '.env')
        if (self.r.url, self.r.db) != identity:
            raise RuntimeError('Database identity mismatch')
        self.schema = {}
        company = self.call('res.company', 'read', [[1]], {'fields': ['name']})
        if company[0]['name'] != 'PAO YEANG SDN BHD':
            raise RuntimeError('Company mismatch')

    def call(self, model, method, args, kwargs=None):
        if method not in {'read', 'search_read', 'search_count', 'fields_get'}:
            raise RuntimeError('Read-only gate')
        return self.r.call(model, method, args, kwargs)

    def fields(self, model, fields):
        if model not in self.schema:
            self.schema[model] = self.call(model, 'fields_get', [], {'attributes': ['type', 'store']})
        return [f for f in fields if f in self.schema[model]]

    def scan(self, model, domain, fields):
        count = self.call(model, 'search_count', [domain])
        result, cursor = [], 0
        while True:
            rows = self.call(model, 'search_read', [domain + [['id', '>', cursor]]],
                             {'fields': self.fields(model, fields), 'limit': 500, 'order': 'id asc'})
            if not rows:
                break
            ids = [r['id'] for r in rows]
            if ids != sorted(set(ids)) or ids[0] <= cursor:
                raise RuntimeError('Invalid pagination')
            result.extend(rows)
            cursor = ids[-1]
        if len(result) != count or self.call(model, 'search_count', [domain]) != count:
            raise RuntimeError('Incomplete or changing source: ' + model)
        return result

    def read(self, model, ids, fields):
        ids = sorted({int(i) for i in ids if i})
        rows = []
        for offset in range(0, len(ids), 300):
            rows.extend(self.call(model, 'read', [ids[offset:offset+300]], {'fields': self.fields(model, fields)}))
        if {r['id'] for r in rows} != set(ids):
            raise RuntimeError('Incomplete read: ' + model)
        return rows

def main():
    socket.setdefaulttimeout(120)
    if (OUT / 'scope.json').exists() and json.loads((OUT / 'scope.json').read_text(encoding='utf8')).get('complete'):
        raise RuntimeError('Completed snapshot already exists; use a new evidence directory')
    end = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    scope = {'start_utc': '2026-07-31 16:00:00', 'end_utc_exclusive': end,
             'company_id': 1, 'timezone': 'Asia/Kuala_Lumpur',
             'backup_acknowledged_by_operator': True, 'complete': False}
    save('scope.json', scope)
    a = ReadOnly('v14-prod', ('http://175.145.85.151', 'paoyeang_live'))
    b = ReadOnly('v19-prod', ('https://py19.odoo.com', 'py19-main-33843450'))
    stock_fields = 'name date state company_id product_id product_uom product_uom_qty quantity_done quantity location_id location_dest_id picking_id move_line_ids move_orig_ids move_dest_ids production_id raw_material_production_id unbuild_id consume_unbuild_id scrap_id scrapped inventory_id is_inventory origin_returned_move_id purchase_line_id sale_line_id write_date'.split()
    domain = [['company_id', '=', 1], ['state', '=', 'done'], ['date', '>=', scope['start_utc']], ['date', '<', end]]
    moves = a.scan('stock.move', domain, stock_fields)
    save('source-moves.json', moves)
    print('source stock moves', len(moves), flush=True)
    lines = a.read('stock.move.line', [i for m in moves for i in m['move_line_ids']], 'move_id company_id product_id product_uom_id qty_done location_id location_dest_id lot_id package_id result_package_id owner_id date write_date'.split())
    save('source-move-lines.json', lines)
    local_day = (datetime.strptime(end, '%Y-%m-%d %H:%M:%S') + timedelta(hours=8)).strftime('%Y-%m-%d')
    invoices = a.scan('account.move', [['company_id', '=', 1], ['state', '=', 'posted'], ['move_type', 'in', ['out_invoice', 'out_refund', 'in_invoice', 'in_refund']], ['invoice_date', '>=', '2026-08-01'], ['invoice_date', '<=', local_day]], 'name ref move_type state company_id partner_id commercial_partner_id currency_id invoice_date date invoice_date_due invoice_user_id journal_id invoice_line_ids line_ids amount_untaxed amount_tax amount_total amount_total_signed reversed_entry_id invoice_origin write_date'.split())
    save('source-invoices.json', invoices)
    save('source-invoice-lines.json', a.read('account.move.line', [i for m in invoices for i in m['line_ids']], 'move_id name display_type product_id product_uom_id quantity price_unit discount tax_ids account_id currency_id amount_currency balance debit credit sale_line_ids purchase_line_id price_subtotal price_total partner_id'.split()))
    print('source invoices', dict(Counter(x['move_type'] for x in invoices)), flush=True)
    models = ['sale.order', 'sale.order.line', 'purchase.order', 'purchase.order.line', 'stock.picking', 'stock.move', 'stock.move.line', 'mrp.production', 'product.product', 'uom.uom', 'stock.location', 'stock.lot', 'res.partner', 'account.move', 'account.account', 'account.tax', 'account.journal']
    xids = b.scan('ir.model.data', [['module', '=', 'pysb_v14'], ['model', 'in', models]], ['name', 'model', 'res_id'])
    save('target-external-ids.json', xids)
    for model, fields in [('sale.order', 'name state order_line picking_ids invoice_ids date_order'), ('purchase.order', 'name state order_line picking_ids invoice_ids date_order date_approve')]:
        ids = [x['res_id'] for x in xids if x['model'] == model]
        rows = b.read(model, ids, fields.split())
        save('target-' + model + '.json', rows)
        print(model, dict(Counter(r['state'] for r in rows)), flush=True)
    save('target-stock-moves-in-period.json', b.scan('stock.move', domain, stock_fields))
    save('source-schema.json', a.schema)
    save('target-schema.json', b.schema)
    scope['complete'] = True
    scope['counts'] = {'moves': len(moves), 'move_lines': len(lines), 'invoices': len(invoices)}
    save('scope.json', scope)
    print(json.dumps(scope), flush=True)

if __name__ == '__main__':
    main()
