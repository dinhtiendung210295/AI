"""Read-only final audit against the durable confirmation batch journal."""
import argparse
import json
import runpy
import socket
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
runner = runpy.run_path(str(ROOT / '.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/confirm_pysb_july_po_staging.py'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', required=True, type=Path)
    args = parser.parse_args()
    socket.setdefaulttimeout(30)
    batch = json.loads(args.batch.read_text(encoding='utf-8'))
    require, Reader = runner['require'], runner['Reader']
    require(batch.get('status') == 'passed' and len(batch['actions']) == 86, 'Batch has not passed all 86 POs')
    a = Reader(ROOT / 'mcp-server-odoo/envs/v14-prod/.env')
    b = Reader(ROOT / 'mcp-server-odoo/envs/v19-staging/.env')
    require((b.url, b.db) == ('https://py-staging.odoo.com', 'py19-staging-39654560'), 'Wrong target')
    require((a.url, a.db) == ('http://175.145.85.151', 'paoyeang_live'), 'Wrong source')
    sources = [g['source'] for g in batch['groups']]
    require(a.read('purchase.order', [r['id'] for r in sources], list(sources[0])) == sources, 'Source PO data changed')
    source_lines = batch['source_lines']
    require(a.read('purchase.order.line', [r['id'] for r in source_lines], list(source_lines[0])) == source_lines,
            'Source line data changed')
    actual = b.read('purchase.order', [g['before']['id'] for g in batch['groups']], runner['ORDER'])
    by_id = {r['id']: r for r in actual}
    states = dict(Counter(r['state'] for r in actual))
    require(states == {'purchase': 86}, 'Not all 86 POs are confirmed')
    for action in batch['actions']:
        require(by_id[action['target_id']] == action['after']['order'], 'PO changed after per-order verification')
    before_lines = [line for g in batch['groups'] for line in g['lines']]
    require(b.read('purchase.order.line', [r['id'] for r in before_lines], runner['LINE']) == before_lines,
            'Commercial lines changed')
    runner['verify_master'](b, batch['master'], batch.get('supplier_additions', []))
    products = sorted(r['id'] for r in batch['master']['product.product']['records'])
    side_effects = runner['verify_side_effects'](b, batch['side_effects_before'], products)
    expected_picks, expected_moves = {}, {}
    for action in batch['actions']:
        workflow = action['after']['workflow']
        for record in workflow['pickings']:
            expected_picks[record['id']] = record
        for record in workflow['moves']:
            expected_moves[record['id']] = record
    picks = b.read('stock.picking', sorted(expected_picks), runner['PICK'])
    moves = b.read('stock.move', sorted(expected_moves), runner['MOVE'])
    require({r['id']: r for r in picks} == expected_picks, 'Receipts changed after verification')
    require({r['id']: r for r in moves} == expected_moves, 'Moves changed after verification')
    linked_moves = b.search_read('stock.move', [['purchase_line_id', 'in', [r['id'] for r in before_lines]]], ['id'])
    require({r['id'] for r in linked_moves} <= set(expected_moves), 'Unreviewed duplicate PO moves')
    report = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'status': 'passed', 'writes_performed': False,
              'target_database': b.db, 'batch_report': str(args.batch), 'scope_count': 86, 'states': states,
              'new_supplier_links_in_batch': len(batch.get('supplier_additions', [])),
              'receipt_count': len(picks), 'move_count': len(moves),
              'receipt_states': dict(Counter(r['state'] for r in picks)),
              'source_unchanged': True, 'commercial_data_unchanged': True,
              'master_data_preserved_except_authorized_supplier_links_and_write_metadata': True,
              'no_new_account_entries': True, 'inventory_quantity_and_cost_unchanged': True,
              'side_effects_after': side_effects, 'pickings': picks, 'moves': moves,
              'supplier_additions': batch.get('supplier_additions', []), 'orders': actual}
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    path = args.batch.parent / f'final-audit-{stamp}.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['status', 'states', 'receipt_count', 'move_count', 'new_supplier_links_in_batch']}
                     | {'report': str(path)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
