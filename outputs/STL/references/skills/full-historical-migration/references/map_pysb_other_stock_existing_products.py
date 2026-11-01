"""Map extra stock products to existing cleaned masters, never create products."""
from execute_pysb_stock_migration import Migration,load,save,OUT,rid,ROOT,require
import runpy,json
def main():
 m=Migration();d=load('supporting-stock-discovery.json');ids=d['missing'].get('product.product',[]);helper=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/so-po-migration/scripts/test_prepare_july_2026_so_po_migration.py'));mapper=helper['TargetMapper'](m.b)
 source=m.a.read('product.product',ids,['name','display_name','default_code','barcode','company_id','active']);mapping=mapper.products(source);m.maps['product.product'].update(mapping)
 target=m.b.read('product.product',sorted(set(m.maps['product.product'].values())),['name','default_code','barcode','tracking','uom_id','packing_ratio','active','is_storable']);base={x['id'] for x in m.j['baseline_products']}
 for x in target:
  if x['id'] not in base:m.j['baseline_products'].append({k:v for k,v in x.items() if k!='is_storable'})
 m.p['maps']['product.product']=m.maps['product.product'];m.p['target_products']=target;save(OUT/'execution-manifest.json',m.p);m.persist()
 issues=list(mapper.exceptions);blockedp=set();blockedgroups=set();moves={s['id']:s for s in d['moves']}
 products={x['id']:x for x in target}
 for x in d['lines']:
  if x['qty_done']<=0:continue
  s=moves[rid(x['move_id'])];sid=rid(x['product_id']);pid=m.maps['product.product'].get(sid);bad=[]
  if not pid:bad.append('missing product mapping')
  elif products[pid]['tracking']!='none' and not x['lot_id']:bad.append('missing source lot for tracked target')
  elif products[pid]['tracking']=='serial' and abs(x['qty_done']-1)>1e-6:bad.append('source serial quantity is not one')
  if x['package_id'] or x['result_package_id'] or x['owner_id']:bad.append('package or owner needs mapping')
  if bad:
   issues.append({'source_move':s['id'],'source_product':sid,'product':x['product_id'][1],'target_product':pid,'source_picking':rid(s['picking_id']),'source_inventory':rid(s.get('inventory_id')),'reason':bad})
   if s['picking_id']:blockedp.add(rid(s['picking_id']))
   else:blockedgroups.add((rid(s.get('inventory_id')),sid))
 eligible=[s for s in d['moves'] if rid(s['picking_id']) not in blockedp and (rid(s.get('inventory_id')),rid(s['product_id'])) not in blockedgroups and rid(s['product_id']) in m.maps['product.product']];eligibleids={s['id'] for s in eligible};lines=[x for x in d['lines'] if rid(x['move_id']) in eligibleids]
 dd={**d,'moves':eligible,'pickings':[p for p in d['pickings'] if p['id'] not in blockedp],'lines':lines,'missing':{k:v for k,v in d['missing'].items() if k!='product.product'}}
 dd['missing']['stock.lot']=sorted({rid(x['lot_id']) for x in lines if x['lot_id'] and rid(x['lot_id']) not in m.maps['stock.lot']})
 save(OUT/'supporting-stock-discovery-before-product-review.json',d);save(OUT/'supporting-stock-discovery.json',dd);save(OUT/'other-stock-master-mapping-exceptions.json',issues)
 print(json.dumps({'existing_products_matched':len(mapping),'products_in_manifest':len(target),'eligible_moves':len(eligible),'eligible_pickings':len(dd['pickings']),'blocked_pickings':sorted(blockedp),'exceptions':issues}))
if __name__=='__main__':main()
