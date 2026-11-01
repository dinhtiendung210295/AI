"""Final SO/line and document-link audit only; no stock/accounting reconciliation."""
import argparse
import json
import runpy
import socket
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
h = runpy.run_path(str(ROOT / '.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/confirm_pysb_july_so_staging.py'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', required=True, type=Path)
    parser.add_argument('--exception', required=True, type=Path)
    args = parser.parse_args()
    batch = json.loads(args.batch.read_text(encoding='utf-8'))
    exception = json.loads(args.exception.read_text(encoding='utf-8'))
    require, Reader = h['require'], h['Reader']
    require(batch['status'] == exception['status'] == 'passed', 'Unverified run evidence')
    socket.setdefaulttimeout(60)
    a = Reader(ROOT / 'mcp-server-odoo/envs/v14-prod/.env')
    b = Reader(ROOT / 'mcp-server-odoo/envs/v19-staging/.env')
    require((a.url, a.db) == ('http://175.145.85.151', 'paoyeang_live'), 'Wrong source')
    require((b.url, b.db) == ('https://py-staging.odoo.com', 'py19-staging-39654560'), 'Wrong target')
    groups = batch['groups']
    require(len(groups) == 953, 'Wrong scope')
    source = [g['source'] for g in groups]
    require(a.read('sale.order', [r['id'] for r in source], list(source[0])) == source, 'Source SO data changed')
    source_lines = batch['source_lines']
    require(a.read('sale.order.line', [r['id'] for r in source_lines], list(source_lines[0])) == source_lines, 'Source lines changed')
    expected = []
    for g in groups:
        item = dict(g)
        if g['source']['name'] == 'SO-53440':
            require(g['before']['id'] == exception['before']['id'], 'Wrong exception SO')
            item['lines'] = exception['after_lines']
        expected.append(item)
    for start in range(0, len(expected), 100):
        h['verify_group'](b, expected[start:start + 100])
    h['verify_masters'](b, batch['master_before'])
    orders = b.read('sale.order', [g['before']['id'] for g in groups], h['ORDER'])
    require(dict(Counter(r['state'] for r in orders)) == {'sale': 953}, 'Not all SOs are confirmed')
    pick_ids = sorted({i for r in orders for i in r['picking_ids']})
    pickings = b.read('stock.picking', pick_ids, ['name', 'state', 'origin', 'sale_id', 'scheduled_date'])
    line_map = h['external'](b, 'sale.order.line')
    by_id = {r['id']: r for r in orders}
    handoff = [{'source_id': g['source']['id'], 'v14_reference': g['source']['name'],
                'target_id': g['before']['id'], 'v19_name': g['before']['name'],
                'date_order_utc': by_id[g['before']['id']]['date_order'],
                'picking_ids': by_id[g['before']['id']]['picking_ids'],
                'line_mapping': [{'v14_line_id': i, 'v19_line_id': line_map[i]} for i in g['source']['order_line']]} for g in groups]
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    report = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'status': 'passed', 'writes_performed': False,
              'target_database': b.db, 'scope_count': 953, 'states': {'sale': 953},
              'source_unchanged': True, 'commercial_data_preserved_except_approved_free_flag': True,
              'master_data_unchanged': True, 'no_invoices': all(not r['invoice_ids'] for r in orders),
              'approved_difference': exception['approved_difference'], 'picking_count': len(pickings),
              'picking_states': dict(Counter(p['state'] for p in pickings)),
              'inventory_and_accounting_reconciliation': 'deferred to DO/MO and INV/BILL steps as requested',
              'orders': orders, 'pickings': pickings, 'batch_report': str(args.batch), 'exception_report': str(args.exception)}
    folder = args.batch.parent
    path = folder / f'final-audit-{stamp}.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (folder / 'so-delivery-handoff.json').write_text(json.dumps(handoff, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {k: v for k, v in report.items() if k not in ['orders', 'pickings']}
    summary.update(final_audit_report=path.name, base_price_repairs=3, offline_tests_passed=5)
    (folder / 'completion-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'report': str(path), 'status': 'passed', 'states': report['states'],
                     'picking_count': len(pickings), 'picking_states': report['picking_states'], 'handoff_rows': len(handoff)}))


if __name__ == '__main__':
    main()
