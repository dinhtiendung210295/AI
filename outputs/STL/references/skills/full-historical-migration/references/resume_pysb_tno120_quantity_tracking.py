"""Operator-approved quantity tracking; restore six omitted source pickings."""
from execute_pysb_stock_migration import Migration,require,save,OUT,rid
from resume_pysb_excluded_consignment_routes import main as prepare_routes
def main():
 m=Migration();p=m.b.read('product.product',[118378],['tracking','product_tmpl_id'])[0]
 require(m.b.read('product.template',[rid(p['product_tmpl_id'])],['product_variant_ids'])[0]['product_variant_ids']==[118378],'Tracking change affects other variants')
 if p['tracking']!='none':m.mutate('product.product','write',[[118378],{'tracking':'none'}])
 require(m.b.read('product.product',[118378],['tracking'])[0]['tracking']=='none','Tracking change failed')
 for row in m.p['target_products']:
  if row['id']==118378:row['tracking']='none'
 for row in m.j['baseline_products']:
  if row['id']==118378:row['tracking']='none'
 approved=m.j.setdefault('approved_operator_master_changes',[])
 if not any(x.get('target_product')==118378 and x.get('value')=='none' for x in approved):approved.append({'source_product':42837,'target_product':118378,'field':'tracking','before':p['tracking'],'value':'none','reason':'Bruce explicitly approved quantity tracking to replay six source pickings without lots'})
 save(OUT/'execution-manifest.json',m.p);m.persist()
 prepare_routes(fixed_sources={185449,185450,185451,185805,185806,185807},old_targets=[1552,1657],journal_key='TNO120_quantity_route_resume')
if __name__=='__main__':main()
