"""Read-only investigation of PO identity gaps; never repairs business data."""
import argparse
import json
from pathlib import Path
import runpy
from types import SimpleNamespace
from datetime import datetime, timezone

BASE = Path(__file__).parent
C = runpy.run_path(str(BASE / 'run_pysb_phased_migration.py'))
A = runpy.run_path(str(BASE / 'confirm_pysb_prod_orders.py'))
rid = A['rid']


def main(directory, concurrent_read=False):
    directory = Path(directory).resolve()
    lock = None if concurrent_read else runpy.run_path(str(BASE / 'production_write_lock.py'))['acquire'](directory)
    try:
        identity, readiness = C['validate_context'](directory)
        # This investigation performs no workflow calls and does not persist
        # shared journals or master-map evidence used by another phase.
        runner = SimpleNamespace(a=A['I']['ReadOnly']('v14-prod', ('http://175.145.85.151', 'paoyeang_live')), b=A['I']['ReadOnly']('v19-prod', ('https://py19.odoo.com', 'py19-main-33843450')))
        report = C['load'](directory / 'phases/confirm-po-verification.json')
        selected = [r for r in report['rows'] if r['status'] == 'held' and not any(i['reason'].startswith('confirmation_may_create_supplier') for i in r['reasons'])]
        sh = {x['id']: x for x in runner.a.read('purchase.order', [r['source_id'] for r in selected], ['name', 'date_order', 'date_approve', 'partner_id', 'picking_type_id', 'company_id', 'order_line', 'amount_total', 'currency_id', 'write_date'])}
        target_fields = ['name', 'state', 'date_order', 'create_date', 'write_date', 'partner_id', 'picking_type_id', 'company_id', 'order_line', 'amount_total', 'currency_id', 'x_studio_v14_reference_studio', 'origin', 'partner_ref']
        th = {x['id']: x for x in runner.b.read('purchase.order', [r['target_id'] for r in selected if r['target_id']], target_fields)}
        missing = [r for r in selected if not r['target_id']]
        candidates = runner.b.scan('purchase.order', [['x_studio_v14_reference_studio', 'in', [r['source_name'] for r in missing]]], target_fields)
        # Also search native reference/partner reference/origin, across archived
        # records and all accessible companies, before declaring an order absent.
        names = [r['source_name'] for r in missing]
        loose = runner.b.scan('purchase.order', ['|', '|', ['name', 'in', names], ['partner_ref', 'in', names], ['origin', 'in', names]], target_fields)
        models = {'purchase.order': {r['source_id'] for r in selected}, 'res.partner': {rid(h['partner_id']) for h in sh.values()}, 'stock.picking.type': {rid(h['picking_type_id']) for h in sh.values()}, 'product.product': set()}
        for row in selected:
            for line in row['line_results']:
                for issue in line.get('issues', []):
                    if issue['reason'] == 'line_product_identity_mismatch':
                        models['product.product'].add(issue['source'])
        xml_names = [model.replace('.', '_') + '_' + str(sid) for model, ids in models.items() for sid in ids]
        xmlids = runner.b.scan('ir.model.data', [['name', 'in', xml_names]], ['module', 'name', 'model', 'res_id'])
        details = {}
        identity_xmlids = []
        for model, fields in [('res.partner', ['name', 'display_name', 'active', 'vat', 'company_registry', 'parent_id', 'company_type', 'company_id']), ('product.product', ['name', 'display_name', 'default_code', 'barcode', 'active', 'product_tmpl_id', 'uom_id']), ('stock.picking.type', ['name', 'code', 'warehouse_id', 'company_id', 'default_location_src_id', 'default_location_dest_id'])]:
            source_ids = models[model] - {False}
            target_ids = {x['res_id'] for x in xmlids if x['model'] == model}
            if model == 'res.partner':
                target_ids.update(rid(h['partner_id']) for h in th.values())
            elif model == 'stock.picking.type':
                target_ids.update(rid(h['picking_type_id']) for h in th.values())
            else:
                for row in selected:
                    for line in row['line_results']:
                        for issue in line.get('issues', []):
                            if issue['reason'] == 'line_product_identity_mismatch':
                                target_ids.update([issue['target'], issue.get('expected_target')])
            details[model] = dict(source=runner.a.read(model, source_ids, fields), target=runner.b.read(model, target_ids - {None, False}, fields))
            identity_xmlids.extend(runner.b.scan('ir.model.data', [['model', '=', model], ['res_id', 'in', sorted(target_ids - {None, False})]], ['module', 'name', 'model', 'res_id']))
        template_ids = {rid(x['product_tmpl_id']) for x in details['product.product']['target']}
        template_xmlids = runner.b.scan('ir.model.data', [['model', '=', 'product.template'], ['res_id', 'in', sorted(template_ids)]], ['module', 'name', 'model', 'res_id'])
        for reader, expected in ((runner.a, sh), (runner.b, th)):
            latest = reader.read('purchase.order', list(expected), ['write_date'])
            if any(x['write_date'] != expected[x['id']]['write_date'] for x in latest):
                raise RuntimeError('Investigated PO changed during capture; no stable conclusion')
        result = dict(identity=identity, captured_utc=datetime.now(timezone.utc).isoformat(), concurrent_read=concurrent_read, erp_mutations=0, source_orders=list(sh.values()), target_orders=list(th.values()), missing_order_reference_candidates=candidates, missing_order_loose_candidates=loose, target_xmlids=xmlids, identity_xmlids=identity_xmlids, template_xmlids=template_xmlids, identities=details, original_issues=selected)
        A['save'](directory / 'phases/po-exception-investigation.json', result)
        print(json.dumps(dict(orders_investigated=len(selected), missing_orders=len(missing), reference_candidates=len(candidates), other_candidates=len(loose), identity_xmlids=xmlids), ensure_ascii=True), flush=True)
    finally:
        if lock is not None:
            lock.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence-dir', required=True)
    parser.add_argument('--concurrent-read', action='store_true')
    args = parser.parse_args()
    main(args.evidence_dir, args.concurrent_read)
