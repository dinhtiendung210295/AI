"""Read-only supplement without taking the production writer lock."""
import runpy
from pathlib import Path
BASE = Path(__file__).parent
M=runpy.run_path(str(BASE/'inspect_pysb_so_remediation.py'))
OUT=M['OUT'];D=M['DEST'];load=M['load'];save=M['save'];rid=M['rid']

def main():
    a=M['M']['I']['ReadOnly']('v14-prod',('http://175.145.85.151','paoyeang_live'))
    b=M['M']['I']['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    maps=load(OUT/'resolved-master-evidence.json')['maps']
    source=load(D/'source-partners.json');target=load(D/'target-partners.json')
    ids={maps['res.partner'].get(str(x['id'])) for x in source}-{False,None}-{x['id'] for x in target}
    target+=b.read('res.partner',ids,list(target[0]))
    parentids={rid(x.get(f)) for x in target for f in ['parent_id','commercial_partner_id']}-{x['id'] for x in target}-{False}
    target+=b.read('res.partner',parentids,list(target[0]))
    save(D/'target-partners-complete.json',target)
    save(D/'target-partner-xids-complete.json',b.scan('ir.model.data',[['model','=','res.partner'],['res_id','in',[x['id'] for x in target]]],['module','name','model','res_id']))
    missing={r['source_id'] for r in load(D/'classification.json') if r['classification']=='missing_target_order'}
    lines=load(D/'source-line-extra.json');ml=[x for x in lines if rid(x['order_id']) in missing]
    productids={rid(x.get('product_id')) for x in ml}|{46577}
    for label,r,ids in [('source',a,productids),('target',b,{maps['product.product'].get(str(i)) for i in productids}-{False,None})]:
        products=r.read('product.product',ids,'name product_tmpl_id active barcode default_code uom_id tracking company_id type'.split())
        save(D/(label+'-supplement-products.json'),products)
        units=r.read('uom.uom',[rid(x['uom_id']) for x in products],'name factor rounding category_id relative_factor relative_uom_id'.split())
        save(D/(label+'-supplement-units.json'),units)
    save(D/'target-so-reference-schema.json',b.call('sale.order','fields_get',[],{'attributes':['type','relation','readonly','required']}))
    refs=b.fields('sale.order',['x_studio_v14_reference_studio','x_v14_source_id','x_studio_source_id'])
    candidates=[]
    names=[x['name'] for x in load(D/'source-order-extra.json') if x['id'] in missing]
    for field in refs:candidates+=b.scan('sale.order',[[field,'in',names]],['name','state','company_id','order_line',field])
    save(D/'missing-order-reference-candidates.json',candidates)
    for label,r in [('source',a),('target',b)]:
        save(D/(label+'-all-pricelists.json'),r.scan('product.pricelist',[],['name','active','currency_id','company_id']))
        save(D/(label+'-all-payment-terms.json'),r.scan('account.payment.term',[],['name','active','line_ids','company_id']))
        save(D/(label+'-all-users.json'),r.scan('res.users',[],['name','login','active','company_ids']))
    plan=load(D/'repair-plan.json') if (D/'repair-plan.json').exists() else None
    if plan:
        sids={i['source'] for row in plan['holds'] for i in row['unresolved'] if i['field'].startswith('partner')}
        source_index={x['id']:x for x in source}
        parentmap={int(k):v for k,v in plan['maps']['res.partner'].items()}
        parents={parentmap.get(rid(source_index[i].get('parent_id'))) for i in sids}-{None,False}
        aliases=b.scan('res.partner',['|',['parent_id','in',list(parents)],['name','in',[source_index[i]['name'] for i in sids]]],list(target[0]))
        save(D/'target-unresolved-contact-candidates.json',aliases)
        save(D/'target-unresolved-contact-xids.json',b.scan('ir.model.data',[['model','=','res.partner'],['name','in',['partner_'+str(i) for i in sids]]],['module','name','res_id']))
    print('Supplement complete; no production lock used',flush=True)

if __name__=='__main__':main()
