"""Explicit operator-approved one new SKU and PTC013WS quantity tracking."""
from execute_pysb_stock_migration import Migration,load,save,OUT,rid,require
import json
def main():
 m=Migration();s=load('new-6115-28mm-product-preflight.json')['source'];require(s['barcode']=='018/6115-03SW 28x10/ROLL' and s['id']==54710,'Wrong source SKU')
 known=m.maps['product.product'].get(54710)
 hits=m.b.call('product.product','search_read',[[['barcode','=',s['barcode']]]],{'fields':['name','company_id','active'],'context':{'active_test':False,'allowed_company_ids':[1]}})
 if known:require(len(hits)==1 and hits[0]['id']==known,'Existing new SKU mismatch');pid=known
 else:
  require(not hits,'Barcode already exists; do not duplicate')
  require(m.b.read('stock.route',[5],['name'])[0]['name']==m.a.read('stock.location.route',[18],['name'])[0]['name']=='Manufacture','Manufacture route mismatch')
  values={'name':s['name'],'barcode':s['barcode'],'default_code':s['default_code'],'type':'consu','is_storable':True,'company_id':1,'categ_id':141,'uom_id':m.maps['uom.uom'][rid(s['uom_id'])],'tracking':s['tracking'],'active':s['active'],'sale_ok':s['sale_ok'],'purchase_ok':s['purchase_ok'],'list_price':s['list_price'],'standard_price':s['standard_price'],'weight':s['weight'],'volume':s['volume'],'invoice_policy':s['invoice_policy'],'purchase_method':s['purchase_method'],'packing_ratio':1.0,'route_ids':[(6,0,[5])],'taxes_id':[(6,0,[])],'supplier_taxes_id':[(6,0,[])]}
  pid=m.mutate('product.product','create',[values],{'context':{'allowed_company_ids':[1]}});m.maps['product.product'][54710]=pid
  m.j.setdefault('approved_new_products',[]).append({'source_product':54710,'target_product':pid,'values':values,'source_creation':'2026-07-29 03:16:07','approved_by':'Bruce','reason':'Created after both product import dates; explicit permission to add exact 28mm SKU'});m.persist();m.attach('product.product',[(54710,pid)])
 p=m.b.read('product.product',[116236],['tracking','product_tmpl_id'])[0]
 require(m.b.read('product.template',[rid(p['product_tmpl_id'])],['product_variant_ids'])[0]['product_variant_ids']==[116236],'Tracking affects another variant')
 if p['tracking']!='none':m.mutate('product.product','write',[[116236],{'tracking':'none'}])
 rows=m.b.read('product.product',sorted(set(m.maps['product.product'].values())),['name','default_code','barcode','tracking','uom_id','packing_ratio','active','is_storable']);base={x['id']:x for x in m.j['baseline_products']}
 for x in rows:
  if x['id'] not in base:m.j['baseline_products'].append({k:v for k,v in x.items() if k!='is_storable'})
  if x['id']==116236:base[x['id']]['tracking']='none'
 m.j.setdefault('approved_operator_master_changes',[]).append({'target_product':116236,'source_product':49431,'field':'tracking','before':p['tracking'],'value':'none','reason':'Bruce approved quantity tracking for PTC013WS source adjustment without lot'})
 m.p['maps']['product.product']=m.maps['product.product'];m.p['target_products']=rows;save(OUT/'execution-manifest.json',m.p);m.persist()
 # Restore exactly the two excluded source adjustments after their master review.
 current=load('supporting-stock-discovery.json');full=load('supporting-stock-discovery-before-product-review.json');wanted={502727,508597};ids={s['id'] for s in current['moves']}
 current['moves'] += [s for s in full['moves'] if s['id'] in wanted and s['id'] not in ids]
 lineids={x['id'] for x in current['lines']};current['lines'] += [x for x in full['lines'] if rid(x['move_id']) in wanted and x['id'] not in lineids]
 current['missing']['stock.lot']=sorted({rid(x['lot_id']) for x in current['lines'] if x['lot_id'] and rid(x['lot_id']) not in m.maps['stock.lot']})
 save(OUT/'supporting-stock-discovery.json',current);save(OUT/'new-6115-28mm-product-result.json',{'source_product':54710,'target_product':pid,'target':m.b.read('product.product',[pid],['name','barcode','tracking','uom_id','categ_id','company_id','is_storable','route_ids'])})
 print(json.dumps({'new_source_product':54710,'new_target_product':pid,'PTC013WS_tracking':'none','restored_adjustments':sorted(wanted)}))
if __name__=='__main__':main()
