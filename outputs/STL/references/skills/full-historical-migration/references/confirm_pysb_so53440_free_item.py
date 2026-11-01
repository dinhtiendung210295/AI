"""Bruce-approved free-item exception for SO-53440, staging only."""
import json
import runpy
import socket
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
h = runpy.run_path(str(ROOT / '.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/confirm_pysb_july_so_staging.py'))
Reader, require, save = [h[k] for k in ['Reader', 'require', 'save']]


def main():
    socket.setdefaulttimeout(60)
    a = Reader(ROOT / 'mcp-server-odoo/envs/v14-prod/.env')
    b = Reader(ROOT / 'mcp-server-odoo/envs/v19-staging/.env')
    require((a.url, a.db) == ('http://175.145.85.151', 'paoyeang_live'), 'Wrong source')
    require((b.url, b.db) == ('https://py-staging.odoo.com', 'py19-staging-39654560'), 'Wrong target')
    source = a.search_read('sale.order', [['company_id', '=', 1], ['name', '=', 'SO-53440']],
                           ['name', 'date_order', 'order_line', 'state'])
    require(len(source) == 1 and source[0]['state'] in ['sale', 'done'] and
            '2026-07-01' <= source[0]['date_order'] < '2026-08-01', 'Wrong source SO')
    source = source[0]
    oid = h['external'](b, 'sale.order')[source['id']]
    lid = h['external'](b, 'sale.order.line')[195704]
    before = b.read('sale.order', [oid], h['ORDER'])[0]
    lines = b.read('sale.order.line', before['order_line'], h['LINE'])
    line = next(r for r in lines if r['id'] == lid)
    require(before['state'] == 'draft' and before['x_studio_v14_reference_studio'] == 'SO-53440' and
            before['company_id'][0] == 1 and not before['picking_ids'] and not before['invoice_ids'], 'SO changed or already confirmed')
    require(line['order_id'][0] == oid and line['price_unit'] == 0 and line['base_price'] == 0 and
            not line['is_free'], 'Free-item exception data changed')
    masters = h['masters'](b, [before], lines)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    path = ROOT / 'outputs/pysb-so-confirm-20261012-staging' / f'so53440-exception-{stamp}.json'
    report = {'target_database': b.db, 'reference': 'SO-53440', 'source': source, 'before': before,
              'before_lines': lines, 'master_before': masters,
              'authorization': 'Bruce explicitly allowed enabling the free-item flag on v19 for SO-53440.',
              'approved_difference': {'source_line_id': 195704, 'target_line_id': lid, 'field': 'is_free', 'source': False, 'target': True},
              'phase': 'free_flag_write_requested'}
    save(path, report)
    try:
        b.call('sale.order.line', 'write', [[lid], {'is_free': True}], {'context': {'tracking_disable': True}})
        expected = [dict(r, is_free=True) if r['id'] == lid else r for r in lines]
        require(b.read('sale.order.line', before['order_line'], h['LINE']) == expected, 'Unapproved line change')
        report['phase'] = 'confirm_requested'
        save(path, report)
        b.call('sale.order', 'action_confirm', [[oid]], {'context': {'tracking_disable': True, 'send_email': False, 'mail_auto_subscribe_no_notify': True}})
        report['phase'] = 'confirmed_pending_date_restore'
        save(path, report)
        b.call('sale.order', 'write', [[oid], {'date_order': source['date_order']}], {'context': {'tracking_disable': True}})
        group = {'source': source, 'before': before, 'lines': expected}
        report['after'] = h['verify_group'](b, [group])[0]
        report['after_lines'] = expected
        h['verify_masters'](b, masters)
        report['status'] = report['phase'] = 'passed'
    except Exception as exc:
        report['status'] = 'stopped'
        report['error'] = str(exc)
        report['recovery_read'] = b.read('sale.order', [oid], h['ORDER'])
    finally:
        save(path, report)
    print(json.dumps({'report': str(path), 'status': report['status'], 'error': report.get('error')}))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
