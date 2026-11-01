"""Read-only supplier provenance investigation for the 16 blocked July POs."""
import json
import runpy
import socket
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
Reader = runpy.run_path(str(ROOT / '.agents/skills/FC+TC/6-Data migration/so-po-migration/scripts/test_prepare_july_2026_so_po_migration.py'))['OdooReader']


def main():
    socket.setdefaulttimeout(30)
    folder = ROOT / 'outputs/pysb-po-confirm-20261012-staging'
    baseline = json.loads((folder / 'batch-20261012T080705095043Z.json').read_text(encoding='utf-8'))
    a = Reader(ROOT / 'mcp-server-odoo/envs/v14-prod/.env')
    b = Reader(ROOT / 'mcp-server-odoo/envs/v19-staging/.env')
    assert (a.url, a.db) == ('http://175.145.85.151', 'paoyeang_live')
    assert (b.url, b.db) == ('https://py-staging.odoo.com', 'py19-staging-39654560')
    sl = {r['id']: r for r in baseline['source_lines']}
    xml = b.search_read('ir.model.data', [['module', '=', 'pysb_v14'], ['model', '=', 'purchase.order.line']], ['name', 'res_id'])
    lm = {int(r['name'].rsplit('_', 1)[1]): r['res_id'] for r in xml if r['name'].startswith('purchase_order_line_')}
    groups = [g for g in baseline['groups'] if g['supplier_risk']]
    pairs = {}
    for g in groups:
        tl = {r['id']: r for r in g['lines']}
        for sid in g['source']['order_line']:
            source, target = sl[sid], tl[lm[sid]]
            if not target['product_id'] or target['product_id'][0] not in g['supplier_risk']:
                continue
            key = (source['product_id'][0], target['product_id'][0], g['source']['partner_id'][0], g['before']['partner_id'][0])
            pairs.setdefault(key, []).append(g['source']['name'])
    pf = ['name', 'default_code', 'barcode', 'product_tmpl_id', 'seller_ids', 'create_date', 'write_date']
    sp = {r['id']: r for r in a.read('product.product', [k[0] for k in pairs], pf)}
    tp = {r['id']: r for r in b.read('product.product', [k[1] for k in pairs], pf)}
    vf = ['name', 'parent_id', 'create_date', 'write_date']
    sv = {r['id']: r for r in a.read('res.partner', [k[2] for k in pairs], vf)}
    tv = {r['id']: r for r in b.read('res.partner', [k[3] for k in pairs], vf)}
    sf = ['partner_id', 'product_tmpl_id', 'product_id', 'price', 'min_qty', 'currency_id',
          'date_start', 'date_end', 'create_date', 'write_date', 'create_uid', 'write_uid']
    def suppliers(reader, products):
        meta = reader.call('product.supplierinfo', 'fields_get', [], {'attributes': ['type']})
        fields = [f for f in sf if f in meta]
        vendor_field = 'partner_id' if 'partner_id' in meta else 'name'
        if vendor_field not in fields:
            fields.append(vendor_field)
        records = reader.search_read('product.supplierinfo', [['product_tmpl_id', 'in',
                                     list({r['product_tmpl_id'][0] for r in products.values()})]], fields)
        for row in records:
            row['partner_id'] = row[vendor_field]
        return records
    ss, ts = suppliers(a, sp), suppliers(b, tp)
    rows = []
    for (si, ti, vi, wi), refs in pairs.items():
        source_vendor_ids = {vi} | ({sv[vi]['parent_id'][0]} if sv[vi]['parent_id'] else set())
        target_vendor_ids = {wi} | ({tv[wi]['parent_id'][0]} if tv[wi]['parent_id'] else set())
        all_source = [r for r in ss if r['product_tmpl_id'][0] == sp[si]['product_tmpl_id'][0]]
        all_target = [r for r in ts if r['product_tmpl_id'][0] == tp[ti]['product_tmpl_id'][0]]
        source_matches = [r for r in all_source if r['partner_id'][0] in source_vendor_ids
                          and (not r['product_id'] or r['product_id'][0] == si)]
        target_matches = [r for r in all_target if r['partner_id'][0] in target_vendor_ids
                          and (not r['product_id'] or r['product_id'][0] == ti)]
        if not source_matches:
            classification = 'missing_on_v14_too'
        elif all(r['create_date'] >= '2026-07-06 00:00:00' for r in source_matches):
            classification = 'source_supplier_created_after_july5'
        elif any(r['create_date'] < '2026-07-05 00:00:00' for r in source_matches):
            classification = 'source_supplier_existed_before_july5'
        else:
            classification = 'source_supplier_created_on_july5_time_unknown'
        rows.append({'po_references': sorted(set(refs)), 'source_product': sp[si], 'target_product': tp[ti],
                     'source_vendor': sv[vi], 'target_vendor': tv[wi],
                     'source_matching_suppliers': source_matches, 'target_matching_suppliers': target_matches,
                     'all_source_template_suppliers': all_source, 'all_target_template_suppliers': all_target,
                     'classification': classification})
    from collections import Counter
    report = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'writes_performed': False,
              'source_database': a.db, 'target_database': b.db, 'reference_import_date': 'approximately 2026-07-05',
              'date_classification_basis': 'Raw Odoo UTC; July 5 boundary needs exact import time/timezone for same-day rows.',
              'classification_counts': dict(Counter(r['classification'] for r in rows)), 'pairs': rows}
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    path = folder / f'supplier-gap-investigation-{stamp}.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'report': str(path), 'pair_count': len(rows), 'classification_counts': report['classification_counts'],
                      'details': [{'pos': r['po_references'], 'product': r['target_product']['name'],
                                   'vendor': r['target_vendor']['name'], 'classification': r['classification'],
                                   'source_create_dates': [x['create_date'] for x in r['source_matching_suppliers']],
                                   'source_write_dates': [x['write_date'] for x in r['source_matching_suppliers']],
                                   'target_seller_count': len(r['all_target_template_suppliers'])} for r in rows]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
