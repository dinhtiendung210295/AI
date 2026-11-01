"""Restore July historical SOL costs on staging only; journal every write."""
import json
import runpy
import socket
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
H = runpy.run_path(str(ROOT / '.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/confirm_pysb_july_so_staging.py'))
Reader, require, save, external = [H[k] for k in ['Reader', 'require', 'save', 'external']]


def main():
    policy_path = ROOT / 'outputs/pysb-stock-migration-20261012/execution-journal.json'
    if policy_path.exists() and json.loads(policy_path.read_text(encoding='utf8')).get('sol_cost_policy', {}).get('status') == 'paused_by_operator':
        print('SOL cost checks and updates skipped per Bruce instruction.', flush=True)
        return
    socket.setdefaulttimeout(60)
    a = Reader(ROOT / 'mcp-server-odoo/envs/v14-prod/.env')
    b = Reader(ROOT / 'mcp-server-odoo/envs/v19-staging/.env')
    require((a.url, a.db) == ('http://175.145.85.151', 'paoyeang_live'), 'Wrong source')
    require((b.url, b.db) == ('https://py-staging.odoo.com', 'py19-staging-39654560'), 'Wrong target')
    sources = a.search_read('sale.order', [['company_id', '=', 1], ['date_order', '>=', '2026-07-01'],
        ['date_order', '<', '2026-08-01'], ['state', 'in', ['sale', 'done']],
        ['is_quotation_template', '=', False]], ['name', 'order_line', 'currency_id'])
    require(len(sources) == 953, 'Scope changed')
    om, lm = external(b, 'sale.order'), external(b, 'sale.order.line')
    require(all(s['id'] in om for s in sources), 'Missing order mapping')
    orders = b.read('sale.order', [om[s['id']] for s in sources], H['ORDER'])
    od = {r['id']: r for r in orders}
    sl = a.read('sale.order.line', [i for s in sources for i in s['order_line']],
                ['order_id', 'product_id', 'purchase_price', 'product_uom', 'display_type', 'product_uom_qty'])
    require(len(sl) == 2683 and all(s['id'] in lm for s in sl), 'Line scope/mapping changed')
    fields = H['LINE'] + ['purchase_price']
    lines = b.read('sale.order.line', [lm[s['id']] for s in sl], fields)
    baseline = {r['id']: r for r in lines}
    sd = {r['id']: r for r in sources}
    # Native sale_stock added this zero-order-quantity line when validating
    # mapped v14 move 504751 (which had no sale_line_id). Preserve it and
    # document it separately; restore cost only on the 2683 mapped lines.
    extras = []
    for so in sources:
        to = od[om[so['id']]]
        expected = {lm[i] for i in so['order_line']}
        require(expected <= set(to['order_line']), 'Missing mapped lines')
        added = set(to['order_line']) - expected
        if added:
            require(so['name'] == 'SO-53388' and added == {11740}, 'Unexpected extra lines')
            extra = b.read('sale.order.line', [11740], fields + ['price_subtotal', 'qty_invoiced', 'move_ids'])[0]
            require(extra['order_id'][0] == to['id'] and extra['product_uom_qty'] == 0
                    and extra['price_subtotal'] == 0 and extra['qty_invoiced'] == 0
                    and extra['move_ids'] == [10362], 'Native extra line changed')
            extras.append(extra)
    desired, pending = {}, []
    for s in sl:
        so, t = sd[s['order_id'][0]], baseline[lm[s['id']]]
        to = od[om[so['id']]]
        require(to['company_id'][0] == 1 and to['state'] == 'sale' and
                to['x_studio_v14_reference_studio'] == so['name'], 'Order identity/state changed')
        require(t['order_id'][0] == to['id'] and t['id'] in to['order_line'], 'Wrong line parent')
        require({lm[i] for i in so['order_line']} <= set(to['order_line']), 'Missing mapped lines')
        require({'CNH': 'CNY'}.get(so['currency_id'][1], so['currency_id'][1]) == to['currency_id'][1], 'Currency mismatch')
        su = {'UNIT': 'Units'}.get(s['product_uom'][1], s['product_uom'][1]) if s['product_uom'] else False
        require(su == (t['product_uom_id'][1] if t['product_uom_id'] else False), 'UOM mismatch')
        require(s['product_uom_qty'] == t['product_uom_qty'] and s['display_type'] == t['display_type'], 'Line changed')
        desired[t['id']] = s['purchase_price']
        if abs(t['purchase_price'] - s['purchase_price']) > 1e-6:
            require(not s['display_type'], 'Unexpected display-line cost')
            pending.append({'source_id': s['id'], 'target_id': t['id'], 'reference': so['name'],
                            'before': t['purchase_price'], 'after': s['purchase_price']})
    require(len(desired) == len(sl), 'Nonunique mapping')
    masters = H['masters'](b, orders, lines)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    path = ROOT / 'outputs/pysb-so-confirm-20261012-staging' / f'sol-cost-update-{stamp}.json'
    log = {'target_database': b.db, 'source_orders': sources, 'source_lines': sl,
           'before_orders': orders, 'before_lines': lines, 'masters': masters,
           'pending': pending, 'operations': [], 'status': 'preflight_passed', 'native_extra_lines_preserved': extras}
    save(path, log)
    print(json.dumps({'phase': 'preflight', 'pending': len(pending), 'report': str(path)}), flush=True)

    def verify(rows, expected):
        require(len(rows) == len(expected), 'Missing readback')
        for r in rows:
            base = baseline[r['id']]
            require(all(r[k] == base[k] for k in H['LINE']), 'Commercial line data changed: ' + str(r['id']))
            require(abs(r['purchase_price'] - expected[r['id']]) <= 1e-6, 'Cost verification failed: ' + str(r['id']))

    def order_equal(actual, expected):
        def normalized(rows):
            return [{**r, 'picking_ids': sorted(r['picking_ids'])} for r in rows]
        return normalized(actual) == normalized(expected)

    try:
        # Trial one line, then groups of 50; writes are one field on one line.
        groups = ([pending[:1]] + [pending[i:i+50] for i in range(1, len(pending), 50)]) if pending else []
        for n, group in enumerate(groups):
            ids = [r['target_id'] for r in group]
            current = b.read('sale.order.line', ids, fields)
            verify(current, {i: baseline[i]['purchase_price'] for i in ids})
            for item in group:
                operation = dict(item, status='intent')
                log['operations'].append(operation)
                save(path, log)
                require(b.call('sale.order.line', 'write', [[item['target_id']], {'purchase_price': item['after']}], {}), 'Write failed')
                operation['status'] = 'written'
            after = b.read('sale.order.line', ids, fields)
            verify(after, {i: desired[i] for i in ids})
            for op in log['operations'][-len(group):]:
                op['status'] = 'verified'
            save(path, log)
            print(json.dumps({'group': n, 'verified': len(log['operations']), 'total': len(pending)}), flush=True)
            if n == 0:
                require(order_equal(b.read('sale.order', list(od), H['ORDER']), orders), 'Order data changed in trial')
                H['verify_masters'](b, masters)
        final = b.read('sale.order.line', list(baseline), fields)
        verify(final, desired)
        require(order_equal(b.read('sale.order', list(od), H['ORDER']), orders), 'Order data changed')
        H['verify_masters'](b, masters)
        if extras:
            require(b.read('sale.order.line', [11740], fields + ['price_subtotal', 'qty_invoiced', 'move_ids']) == extras, 'Native extra line changed during cost restore')
        fresh = a.read('sale.order.line', [s['id'] for s in sl], ['purchase_price'])
        require(all(abs(r['purchase_price'] - desired[lm[r['id']]]) <= 1e-6 for r in fresh), 'Source cost changed during run')
        log.update(status='completed', after_lines=final,
                   summary={'orders': len(orders), 'lines': len(lines), 'updated': len(pending),
                            'all_costs_match': True, 'commercial_data_unchanged': True, 'masters_unchanged': True})
        save(path, log)
        print(json.dumps(log['summary'] | {'report': str(path)}), flush=True)
    except Exception as exc:
        log.update(status='stopped', error=str(exc))
        save(path, log)
        raise


if __name__ == '__main__':
    main()
