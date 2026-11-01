"""Correct three known historical SO base prices; never changes selling prices."""
import json
import runpy
import socket
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
helper = runpy.run_path(str(ROOT / '.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/confirm_pysb_july_so_staging.py'))
Reader, require, save = [helper[k] for k in ['Reader', 'require', 'save']]
socket.setdefaulttimeout(30)
a = Reader(ROOT / 'mcp-server-odoo/envs/v14-prod/.env')
b = Reader(ROOT / 'mcp-server-odoo/envs/v19-staging/.env')
require((a.url, a.db) == ('http://175.145.85.151', 'paoyeang_live'), 'Wrong source')
require((b.url, b.db) == ('https://py-staging.odoo.com', 'py19-staging-39654560'), 'Wrong target')
line_map = helper['external'](b, 'sale.order.line')
plan = [(sid, line_map[sid], ref) for sid, ref in
        [(195606, 'SO-53435'), (196924, 'SO-53787'), (197067, 'SO-53814')]]
orders = helper['ORDER']; fields = helper['LINE']
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
path = ROOT / 'outputs/pysb-so-confirm-20261012-staging' / f'base-price-repair-{stamp}.json'
report = {'database': b.db, 'actions': []}
for sid, tid, ref in plan:
    source = a.read('sale.order.line', [sid], ['order_id', 'base_price', 'price_unit', 'discount', 'is_free'])[0]
    before = b.read('sale.order.line', [tid], fields)[0]
    order = b.read('sale.order', [before['order_id'][0]], orders)[0]
    require(order['state'] == 'draft' and order['company_id'][0] == 1 and order['x_studio_v14_reference_studio'] == ref, 'Wrong draft SO')
    require(source['order_id'][1] == ref and all(before[k] == source[k] for k in ['price_unit', 'discount', 'is_free']), 'Source values changed')
    entry = {'source_id': sid, 'target_id': tid, 'reference': ref, 'before': before, 'source': source, 'status': 'write_requested'}
    report['actions'].append(entry)
    save(path, report)
    if before['base_price'] != source['base_price']:
        b.call('sale.order.line', 'write', [[tid], {'base_price': source['base_price']}], {'context': {'tracking_disable': True}})
    after = b.read('sale.order.line', [tid], fields)[0]
    require(after['base_price'] == source['base_price'], 'Base price correction failed')
    require(all(before[k] == after[k] for k in fields if k != 'base_price'), 'Another line field changed')
    require(b.read('sale.order', [order['id']], orders)[0] == order, 'Order commercial values changed')
    entry.update(after=after, status='passed')
    save(path, report)
report['status'] = 'passed'
save(path, report)
print(json.dumps({'report': str(path), 'status': 'passed', 'repaired_lines': len(plan)}))
