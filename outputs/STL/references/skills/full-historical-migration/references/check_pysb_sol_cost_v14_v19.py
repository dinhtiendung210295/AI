"""Read-only July PYSB sale-line historical Cost comparison."""
import json
import runpy
import socket
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
H = runpy.run_path(str(ROOT / '.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/confirm_pysb_july_po_staging.py'))


def main():
    socket.setdefaulttimeout(60)
    a = H['Reader'](ROOT / 'mcp-server-odoo/envs/v14-prod/.env')
    b = H['Reader'](ROOT / 'mcp-server-odoo/envs/v19-staging/.env')
    require = H['require']
    require((a.url, a.db) == ('http://175.145.85.151', 'paoyeang_live'), 'Wrong source')
    require((b.url, b.db) == ('https://py-staging.odoo.com', 'py19-staging-39654560'), 'Wrong target')
    sources = a.search_read('sale.order', [['company_id', '=', 1], ['date_order', '>=', '2026-07-01'],
              ['date_order', '<', '2026-08-01'], ['state', 'in', ['sale', 'done']],
              ['is_quotation_template', '=', False]], ['name', 'order_line', 'currency_id'])
    om, lm = H['external'](b, 'sale.order'), H['external'](b, 'sale.order.line')
    targets = {r['id']: r for r in b.read('sale.order', [om[r['id']] for r in sources if r['id'] in om],
               ['name', 'company_id', 'currency_id', 'order_line', 'x_studio_v14_reference_studio'])}
    fields = ['order_id', 'product_id', 'display_type', 'name', 'product_uom_qty', 'purchase_price']
    sl = a.read('sale.order.line', [i for r in sources for i in r['order_line']], fields + ['product_uom'])
    tl = {r['id']: r for r in b.read('sale.order.line', [lm[r['id']] for r in sl if r['id'] in lm], fields + ['product_uom_id'])}
    order_source = {r['id']: r for r in sources}
    rows = []
    for s in sl:
        so = order_source[s['order_id'][0]]
        to = targets.get(om.get(so['id']))
        t = tl.get(lm.get(s['id']))
        row = {'reference': so['name'], 'source_line_id': s['id'], 'target_line_id': lm.get(s['id']),
               'source_product': s['product_id'], 'source_cost': s['purchase_price'],
               'target_cost': t['purchase_price'] if t else None, 'quantity': s['product_uom_qty'],
               'source_currency': so['currency_id'], 'source_uom': s['product_uom'], 'display_type': s['display_type']}
        if not to or not t:
            row['status'] = 'missing_mapping'
        elif to['company_id'][0] != 1 or to['x_studio_v14_reference_studio'] != so['name'] or t['order_id'][0] != to['id'] or t['id'] not in to['order_line']:
            row['status'] = 'wrong_mapping'
        else:
            row.update(target_order_id=to['id'], target_order_name=to['name'], target_product=t['product_id'],
                       target_currency=to['currency_id'], target_uom=t['product_uom_id'])
            currency = {'CNH': 'CNY'}.get(so['currency_id'][1], so['currency_id'][1])
            uom = {'UNIT': 'Units'}.get(s['product_uom'][1], s['product_uom'][1]) if s['product_uom'] else False
            tuom = t['product_uom_id'][1] if t['product_uom_id'] else False
            if currency != to['currency_id'][1] or uom != tuom:
                row['status'] = 'currency_or_uom_mismatch'
            else:
                row['difference'] = t['purchase_price'] - s['purchase_price']
                row['status'] = 'matched' if abs(row['difference']) <= 0.000001 else 'cost_mismatch'
                row['quantity_weighted_difference'] = row['difference'] * s['product_uom_qty']
        rows.append(row)
    summary = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'writes_performed': False,
               'source_database': a.db, 'target_database': b.db, 'field': 'sale.order.line.purchase_price',
               'order_count': len(sources), 'line_count': len(rows), 'status_counts': dict(Counter(r['status'] for r in rows)),
               'orders_with_differences': len({r['reference'] for r in rows if r['status'] != 'matched'}),
               'comparison_tolerance': 0.000001,
               'non_display_status_counts': dict(Counter(r['status'] for r in rows if not r['display_type']))}
    folder = ROOT / 'outputs/pysb-so-confirm-20261012-staging'
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    path = folder / f'sol-cost-comparison-{stamp}.json'
    H['save'](path, {'summary': summary, 'rows': rows})
    print(json.dumps(summary | {'report': str(path), 'examples': [r for r in rows if r['status'] != 'matched'][:8]}))


if __name__ == '__main__':
    main()
