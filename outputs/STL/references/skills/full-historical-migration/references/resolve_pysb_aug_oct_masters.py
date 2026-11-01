"""Read-only identity checks using mapped templates and native unit factors."""
import json
import runpy
import socket
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
I = runpy.run_path(str(BASE / 'inspect_pysb_aug_oct_prod.py'))
ROOT, OUT, save, ReadOnly = I['ROOT'], I['OUT'], I['save'], I['ReadOnly']
def rid(v): return v[0] if isinstance(v, list) and v else v or False
def load(n): return json.loads((OUT / n).read_text(encoding='utf8'))

def main():
    socket.setdefaulttimeout(120)
    d = load('discovery-manifest.json')
    maps = {m: {int(s): t for s,t in v.items()} for m,v in d['maps'].items()}
    a = ReadOnly('v14-prod', ('http://175.145.85.151', 'paoyeang_live'))
    b = ReadOnly('v19-prod', ('https://py19.odoo.com', 'py19-main-33843450'))
    products = a.read('product.product', [x['id'] for x in load('source-products.json')], ['name','product_tmpl_id','uom_id','tracking','active'])
    templates = a.read('product.template', [rid(x['product_tmpl_id']) for x in products], ['product_variant_ids'])
    single = {x['id']: x['product_variant_ids'][0] for x in templates if len(x['product_variant_ids']) == 1}
    target_templates = b.read('product.template', [maps['product.template'][i] for i in single if i in maps['product.template']], ['product_variant_ids'])
    target_single = {x['id']: x['product_variant_ids'][0] for x in target_templates if len(x['product_variant_ids']) == 1}
    prior_evidence = load('resolved-master-evidence.json') if (OUT/'resolved-master-evidence.json').exists() else {}
    resolutions = [x for x in prior_evidence.get('resolutions',[]) if 'rejected_target_id' in x]
    issues = []
    if (OUT / 'missing-product-barcode-candidates.json').exists():
        source_byid = {x['id']:x for x in load('source-products.json')}
        candidates = load('missing-product-barcode-candidates.json')
        source_barcode = a.scan('product.product', [['barcode','in',[x['barcode'] for x in candidates]]], ['barcode','company_id'])
        for sid, p in source_byid.items():
            hits = [x for x in candidates if x['barcode'] == p.get('barcode') and x['name'] == p['name'] and rid(x['company_id']) == 1 and x['tracking'] == p['tracking']]
            source_hits = [x for x in source_barcode if x['barcode'] == p.get('barcode')]
            if len(hits) == 1 and len(source_hits) == 1:
                maps['product.product'][sid] = hits[0]['id']
                resolutions.append({'model':'product.product','source_id':sid,'target_id':hits[0]['id'],'evidence':'unique_barcode_both_databases_exact_name_company_tracking'})
    for p in products:
        st = rid(p['product_tmpl_id']); tt = maps['product.template'].get(st)
        if st in single and tt in target_single:
            tid = target_single[tt]
            prior = maps['product.product'].get(p['id'])
            if prior and prior != tid:
                issues.append({'model':'product.product','source_id':p['id'],'reason':'template_variant_conflict','existing':prior,'candidate':tid})
            else:
                maps['product.product'][p['id']] = tid
                resolutions.append({'model':'product.product','source_id':p['id'],'target_id':tid,'evidence':'mapped_template_single_variant_on_both_sides','source_template':st,'target_template':tt})
    requested_ids = {maps['product.product'][p['id']] for p in products if p['id'] in maps['product.product']}
    target_products = b.scan('product.product', [['id', 'in', sorted(requested_ids)]], ['name','product_tmpl_id','uom_id','tracking','active','company_id','type','is_storable'])
    for tid in sorted(requested_ids - {p['id'] for p in target_products}):
        issues.append({'model':'product.product','target_id':tid,'reason':'target_not_readable_in_company_scope'})
    save('target-products.json', target_products)
    save('source-products-with-template.json', products)
    source_units = {x['id']:x for x in load('source-uom.uom.json')}
    target_units = {x['id']:x for x in load('target-uom.uom.json')}
    target_byid = {x['id']:x for x in target_products}
    candidates = defaultdict(set)
    for p in products:
        tid = maps['product.product'].get(p['id'])
        if tid in target_byid:
            candidates[rid(p['uom_id'])].add(rid(target_byid[tid]['uom_id']))
    for sid, tids in candidates.items():
        if len(tids) != 1:
            s = source_units[sid]
            exact = [t for t in target_units.values() if t['name'] == s['name'] and abs((1/s['factor'])-t['factor']) < 1e-8]
            if len(exact) == 1:
                tids = {exact[0]['id']}
            else:
                issues.append({'model':'uom.uom','source_id':sid,'targets':sorted(tids),'reason':'inconsistent_product_uom_mapping'}); continue
        tid = next(iter(tids)); s = source_units[sid]; t = target_units[tid]
        name_match = t['name'] == {'UNIT':'Units','GRAM':'g','MM':'mm'}.get(s['name'],s['name'])
        factor_match = abs((1/s['factor'])-t['factor']) < 1e-8
        if name_match and factor_match:
            prior = maps['uom.uom'].get(sid)
            if prior and prior != tid:
                resolutions.append({'model':'uom.uom','source_id':sid,'rejected_target_id':prior,'target_id':tid,'evidence':'standard_xmlid_rejected_due_to_changed_unit_semantics; mapped_product_base_unit_name_and_factor_verified'})
            maps['uom.uom'][sid] = tid
            resolutions.append({'model':'uom.uom','source_id':sid,'target_id':tid,'evidence':'mapped_product_base_unit_name_and_inverse_factor','source_rounding':s['rounding'],'target_rounding':t['rounding']})
        else:
            issues.append({'model':'uom.uom','source_id':sid,'target_id':tid,'reason':'base_unit_conversion_requires_review','source':s,'target':t})
    for p in products:
        tid = maps['product.product'].get(p['id'])
        t = target_byid.get(tid)
        if t and p['tracking'] != t['tracking']:
            approval=load('operator-pp-primer-untracked-approval.json') if (OUT/'operator-pp-primer-untracked-approval.json').exists() else {}
            if p['id']==54465 and tid==116045 and p['tracking']=='lot' and t['tracking']=='none' and approval.get('approved') and approval.get('source_product')==54465 and approval.get('target_product')==116045:
                resolutions.append({'model':'product.product','source_id':54465,'target_id':116045,'source_tracking':'lot','target_tracking':'none','evidence':'Operator explicitly approved preserving native untracked configuration; exact stock-detail checks remain mandatory; no implicit lot or quantity waiver'})
                continue
            issues.append({'model':'product.product','source_id':p['id'],'target_id':tid,'reason':'tracking_difference','source':p['tracking'],'target':t['tracking']})
    save('resolved-master-evidence.json', {'maps':maps,'resolutions':resolutions,'issues':issues})
    print(json.dumps({'products_in_scope':len(products),'mapped_products_in_scope':sum(x['id'] in maps['product.product'] for x in products),'resolutions':len(resolutions),'issues':len(issues)}),flush=True)

if __name__ == '__main__': main()
