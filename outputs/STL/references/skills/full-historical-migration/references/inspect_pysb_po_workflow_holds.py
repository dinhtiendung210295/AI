"""Read current supplier metadata for held PO lines, including native cap."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import runpy

BASE = Path(__file__).parent
C = runpy.run_path(str(BASE / 'run_pysb_phased_migration.py'))
A = runpy.run_path(str(BASE / 'confirm_pysb_prod_orders.py'))
rid = A['rid']


def main(directory):
    directory = Path(directory).resolve()
    lock = runpy.run_path(str(BASE / 'production_write_lock.py'))['acquire'](directory)
    try:
        identity, readiness = C['validate_context'](directory)
        runner = A['ConfirmPO'](directory, identity, readiness)
        held = [x for x in runner.j['orders'].values() if x['status'] == 'held_workflow']
        tids = [x['target_id'] for x in held]
        orders = {x['id']: x for x in runner.b.read('purchase.order', tids, ['partner_id', 'order_line', 'state'])}
        lines = {x['id']: x for x in runner.b.read('purchase.order.line', [i for o in orders.values() for i in o['order_line']], ['product_id', 'display_type'])}
        products = {x['id']: x for x in runner.b.read('product.product', [rid(x['product_id']) for x in lines.values() if x.get('product_id')], ['seller_ids'])}
        partners = {x['id']: x for x in runner.b.read('res.partner', [rid(x['partner_id']) for x in orders.values()], ['parent_id'])}
        sellers = {x['id']: x for x in runner.b.read('product.supplierinfo', [i for p in products.values() for i in p['seller_ids']], ['partner_id'])}
        rows = []
        safe = []
        for item in held:
            order = orders[item['target_id']]
            vendor = {rid(order['partner_id']), rid(partners[rid(order['partner_id'])]['parent_id'])} - {False}
            details = []
            for lid in order['order_line']:
                line = lines[lid]
                if line.get('display_type') or not line.get('product_id'):
                    continue
                product = products[rid(line['product_id'])]
                already = bool(vendor.intersection(rid(sellers[i]['partner_id']) for i in product['seller_ids']))
                details.append(dict(target_line_id=lid, target_product_id=rid(line['product_id']), seller_ids=product['seller_ids'], seller_partner_ids=[rid(sellers[i]['partner_id']) for i in product['seller_ids']], vendor_ids=sorted(vendor), already_registered=already, native_would_add_supplier=not already and len(product['seller_ids']) <= 10))
            safe_by_cap = bool(details) and not any(x['native_would_add_supplier'] for x in details)
            if safe_by_cap:
                safe.append(item['source_id'])
            rows.append(dict(source_id=item['source_id'], target_id=item['target_id'], lines=details, supplier_hold_still_valid=not safe_by_cap))
        evidence = dict(identity=identity, read_only_erp=True, captured_utc=datetime.now(timezone.utc).isoformat(), rows=rows, safe_to_recheck_source_ids=safe)
        A['save'](directory / 'phases/po-held-supplier-evidence.json', evidence)
        print(__import__('json').dumps(dict(held=len(rows), safe_to_recheck_source_ids=safe)), flush=True)
    finally:
        lock.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence-dir', required=True)
    main(parser.parse_args().evidence_dir)
