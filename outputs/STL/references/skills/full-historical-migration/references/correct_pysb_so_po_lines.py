"""Correct known July line differences on staging, without workflow changes."""
import argparse
import json
import runpy
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
Reader = runpy.run_path(str(ROOT / '.agents/skills/FC+TC/6-Data migration/so-po-migration/scripts/test_prepare_july_2026_so_po_migration.py'))['OdooReader']
SPECS = {
    'sale.order.line': {195606: ['product_uom_qty', 'price_unit', 'discount'],
                       **{i: ['product_uom_qty'] for i in [196108, 196109, 196110, 196111, 196112, 196113]},
                       196924: ['price_unit'], 197067: ['price_unit']},
    'purchase.order.line': {**{i: ['price_unit'] for i in [19470, 19471, 19556, 19557, 19558, 19559, 19560]},
                           19713: ['name'], **{i: ['product_qty', 'price_unit'] for i in [19715, 19716, 19717, 19718]}}
}
REFS = {'SO-53435', 'SO-53787', 'SO-53814', 'PO-04439', 'PO-04456', 'PO-04486', 'PO-04487'}


def require(ok, msg):
    if not ok:
        raise RuntimeError(msg)


def equal(a, b):
    if isinstance(a, (int, float)) and not isinstance(a, bool) and isinstance(b, (int, float)) and not isinstance(b, bool):
        return abs(a - b) < 0.000001
    return a == b


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--sample', action='store_true', help='Only SO-53787, one price correction')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    a = Reader(ROOT / 'mcp-server-odoo/envs/v14-prod/.env')
    b = Reader(ROOT / 'mcp-server-odoo/envs/v19-staging/.env')
    require(a.db == 'paoyeang_live' and a.url == 'http://175.145.85.151', 'Source guard failed')
    require(b.db == 'py19-staging-39654560' and b.url == 'https://py-staging.odoo.com', 'Staging guard failed')
    groups = []
    for model, spec in SPECS.items():
        om = model.removesuffix('.line')
        quantity = 'product_uom_qty' if om == 'sale.order' else 'product_qty'
        taxes = 'tax_id' if om == 'sale.order' else 'taxes_id'
        target_taxes = 'tax_ids'
        source_fields = ['id', 'order_id', 'name', 'product_id', quantity, 'price_unit', 'price_subtotal', 'product_uom', taxes]
        if om == 'sale.order':
            source_fields += ['discount']
        target_fields = ['id', 'order_id', 'name', 'product_id', quantity, 'price_unit', 'price_subtotal', 'product_uom_id', target_taxes, 'discount', 'write_date']
        sr = {r['id']: r for r in a.read(model, list(spec), source_fields)}
        xml = b.search_read('ir.model.data', [['module', '=', 'pysb_v14'], ['model', '=', model], ['name', 'in', [model.replace('.', '_') + '_' + str(i) for i in spec]]], ['name', 'res_id'])
        require(len(xml) == len(spec), 'Missing/duplicate line External IDs')
        maps = {int(x['name'].rsplit('_', 1)[1]): x['res_id'] for x in xml}
        require(set(maps) == set(spec) and len(set(maps.values())) == len(spec), 'Invalid line map')
        tr = {r['id']: r for r in b.read(model, list(maps.values()), target_fields)}
        ofields = ['id', 'name', 'company_id', 'partner_id', 'state', 'currency_id', 'date_order', 'order_line', 'picking_ids', 'invoice_ids', 'amount_untaxed', 'amount_tax', 'amount_total', 'x_studio_v14_reference_studio']
        tos = {r['id']: r for r in b.read(om, [r['order_id'][0] for r in tr.values()], ofields)}
        sos = {r['id']: r for r in a.read(om, [r['order_id'][0] for r in sr.values()], ['id', 'name', 'company_id', 'date_order', 'currency_id', 'amount_untaxed', 'amount_tax', 'amount_total'])}
        for order in tos.values():
            ref = order['x_studio_v14_reference_studio']
            require(ref in REFS and order['company_id'][0] == 1, 'Wrong target order/company')
            require(order['state'] in ['draft', 'sent'] and not order['picking_ids'] and not order['invoice_ids'], 'Order has workflow effects; stop')
            lines = b.read(model, order['order_line'], target_fields)
            updates = []
            source_order = None
            for sid, fields in spec.items():
                target = tr[maps[sid]]
                if target['order_id'][0] != order['id']:
                    continue
                source = sr[sid]
                so = sos[source['order_id'][0]]
                require(so['name'] == ref and so['company_id'][0] == 1 and '2026-07-01' <= so['date_order'] < '2026-08-01', 'Source order mismatch')
                require(so['currency_id'][1] == order['currency_id'][1], 'Currency mismatch')
                source_order = so
                values = {f: source[f] for f in fields if not equal(source[f], target[f])}
                # Quantity changes trigger supplier/pricelist recomputation in Odoo.
                # Explicitly pin historical commercial values in the same write.
                if quantity in values:
                    values['price_unit'] = source['price_unit']
                    values['discount'] = source.get('discount', target['discount'])
                if values:
                    updates.append({'source_id': sid, 'target_id': target['id'], 'values': values, 'source': source, 'before': target})
            require(source_order is not None, 'Missing source order')
            groups.append({'model': model, 'order_model': om, 'order_fields': ofields, 'line_fields': target_fields, 'reference': ref, 'before_order': order, 'before_lines': lines, 'source_order': source_order, 'updates': updates})
    master_fields = ['id', 'name', 'write_date']
    product_ids = sorted({r['product_id'][0] for g in groups for r in g['before_lines'] if r['product_id']})
    partner_ids = sorted({g['before_order']['partner_id'][0] for g in groups})
    products = b.read('product.product', product_ids, master_fields)
    partners = b.read('res.partner', partner_ids, master_fields)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    path = args.output_dir / f'correction-{stamp}.json'
    report = {'target_database': b.db, 'apply': args.apply, 'sample': args.sample, 'before_products': products, 'before_partners': partners, 'groups': groups, 'actions': []}
    save(path, report)
    if args.apply:
        for g in groups:
            if args.sample and g['reference'] != 'SO-53787':
                continue
            order = g['before_order']
            require(b.read(g['order_model'], [order['id']], g['order_fields'])[0] == order, 'Order changed since preflight')
            require(b.read(g['model'], order['order_line'], g['line_fields']) == g['before_lines'], 'Lines changed since preflight')
            if g['updates']:
                # One ORM transaction per order; no workflow methods or new records.
                commands = [[1, e['target_id'], e['values']] for e in g['updates']]
                require(b.call(g['order_model'], 'write', [[order['id']], {'order_line': commands}], {'context': {'tracking_disable': True}}), 'Write failed')
            actual = b.read(g['model'], order['order_line'], g['line_fields'])
            modifications = {e['target_id']: e for e in g['updates']}
            for old, new in zip(g['before_lines'], actual):
                require(old['id'] == new['id'], 'Line identity changed')
                change = modifications.get(old['id'])
                for k in old:
                    if change and k in change['values']:
                        require(equal(new[k], change['values'][k]), 'Corrected field mismatch')
                    elif change and k in ['write_date', 'price_subtotal']:
                        continue
                    else:
                        require(equal(old[k], new[k]), 'Unrequested line field changed: ' + k)
                if change:
                    require(equal(new['price_subtotal'], change['source']['price_subtotal']), 'Line subtotal mismatch')
            after = b.read(g['order_model'], [order['id']], g['order_fields'])[0]
            for k in order:
                if k not in ['amount_untaxed', 'amount_tax', 'amount_total']:
                    require(order[k] == after[k], 'Unrequested order field changed: ' + k)
            for k in ['amount_untaxed', 'amount_tax', 'amount_total']:
                require(abs(after[k] - g['source_order'][k]) < 0.01, 'Order amount does not match source: ' + k)
            g['after_order'] = after
            g['after_lines'] = actual
            report['actions'].append({'reference': g['reference'], 'corrected_lines': len(g['updates']), 'verification': 'passed'})
            save(path, report)
        require(b.read('product.product', product_ids, master_fields) == products, 'Products changed')
        require(b.read('res.partner', partner_ids, master_fields) == partners, 'Partners changed')
        report['verification'] = 'passed'
        save(path, report)
    print(json.dumps({'report': str(path), 'lines_needing_correction': sum(len(g['updates']) for g in groups), 'actions': report['actions'], 'verification': report.get('verification', 'read_only_preflight')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
