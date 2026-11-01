"""Read-only dependencies for the 16 explicitly authorized missing SOs."""
import runpy
from pathlib import Path
BASE=Path(__file__).parent;M=runpy.run_path(str(BASE/'inspect_pysb_so_remediation.py'));D=M['DEST'];OUT=M['OUT'];rid=M['rid'];load=M['load'];save=M['save']
def main():
    a=M['M']['I']['ReadOnly']('v14-prod',('http://175.145.85.151','paoyeang_live'));b=M['M']['I']['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    maps=load(OUT/'resolved-master-evidence.json')['maps'];products=load(D/'source-supplement-products.json')
    targetids={maps['product.template'].get(str(rid(x['product_tmpl_id']))) for x in products}-{None,False}
    candidates=b.scan('product.product',['|',['product_tmpl_id','in',list(targetids)],['barcode','in',[x['barcode'] for x in products if x['barcode']]]],['name','product_tmpl_id','barcode','default_code','active','company_id','uom_id','tracking'])
    save(D/'missing-so-product-candidates.json',candidates)
    save(D/'missing-so-source-product-xids.json',a.scan('ir.model.data',['|','&',['model','=','product.product'],['res_id','in',[x['id'] for x in products]],'&',['model','=','product.template'],['res_id','in',[rid(x['product_tmpl_id']) for x in products]]],['module','name','model','res_id']))
    save(D/'missing-so-target-product-xids.json',b.scan('ir.model.data',['|','&',['model','=','product.product'],['res_id','in',[x['id'] for x in candidates]],'&',['model','=','product.template'],['res_id','in',[rid(x['product_tmpl_id']) for x in candidates]]],['module','name','model','res_id']))
    for label,r in [('source',a),('target',b)]:
        terms=load(D/(label+'-all-payment-terms.json'))
        save(D/(label+'-payment-term-lines.json'),r.read('account.payment.term.line',[i for x in terms for i in x['line_ids']],['value','value_amount','days','nb_days','delay_type','days_next_month','end_month','months','sequence']))
    save(D/'missing-so-extra-units.json',b.read('uom.uom',[rid(x['uom_id']) for x in candidates],['name','factor','rounding','relative_uom_id','relative_factor']))
    print('Missing SO master evidence complete; no writer lock acquired',flush=True)
if __name__=='__main__':main()
