"""Restore missing package dimension on evidenced existing opening inventory lines."""
import runpy,json
from pathlib import Path
from collections import defaultdict
ROOT=Path(__file__).resolve().parents[6]
H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/execute_pysb_stock_migration.py'))
def totals(rows):
 d=defaultdict(float)
 for x in rows:d[tuple(H['rid'](x[k]) for k in ['product_id','location_id','lot_id','owner_id'])]+=x['quantity']
 return d
def main():
 m=H['Migration']();rid=H['rid'];require=H['require'];e=H['load']('opening-package-plan-evidence.json');before=H['load']('opening-package-target-before.json');pm={int(s):t for s,t in e['product_map'].items()};packages=H['index'](e['source_packages']);moves=H['index'](before['moves']);plan=[]
 cutoff='2026-06-30 15:59:59';pids={pm[x['key'][0]] for x in e['opening_rows']};domain=[['company_id','=',1],['product_id','in',sorted(pids)]];qfields=['product_id','location_id','lot_id','package_id','owner_id','quantity','reserved_quantity']
 currentq=m.b.search_read('stock.quant',domain,qfields);base=totals(currentq)
 for row in e['opening_rows']:
  s,loc,lot,pack,owner=row['key'];require(row['quantity']>0 and not lot and not owner,'Nonpositive or tracked opening requires separate matching')
  target=pm[s];location=m.maps['stock.location'][loc]
  matches=[x for x in before['lines'] if rid(x['product_id'])==target and rid(x['location_dest_id'])==location and not x['lot_id'] and not x['owner_id'] and abs(x['quantity_product_uom']-row['quantity'])<1e-6]
  require(len(matches)==1,'Opening line mapping is not unique')
  line=matches[0];require(line['state']=='done' and rid(line['company_id'])==1 and rid(line['location_id'])==11,'Wrong opening inventory line')
  package_name=packages[pack]['name'];existing=m.b.search_read('stock.package',[['name','=',package_name]],['company_id','location_id'])
  require(len(existing)<=1 and all(rid(x['company_id']) in [False,1] for x in existing),'Package name collision')
  plan.append({'source_product':s,'target_product':target,'source_location':loc,'target_location':location,'source_package':pack,'package_name':package_name,'quantity':row['quantity'],'before_line':line,'before_move':moves[rid(line['move_id'])],'existing_package':existing[0]['id'] if existing else False})
 H['save'](m.path.parent/'opening-package-correction-plan.json',plan)
 m.j.setdefault('opening_package_reclassifications',[])
 for item in plan:
  line=item['before_line'];lid=line['id'];mid=rid(line['move_id']);already=next((x for x in m.j['opening_package_reclassifications'] if x['target_line']==lid),None)
  if already and already['status']=='verified':continue
  fresh=m.b.read('stock.move.line',[lid],list(line.keys()))[0]
  require(fresh==line,'Opening line changed after preflight')
  qty=item['quantity'];pid=item['target_product'];loc=item['target_location']
  physical=m.b.search_read('stock.quant',domain,qfields)
  require(sum(x['quantity'] for x in physical if rid(x['product_id'])==pid and rid(x['location_id'])==loc and not x['lot_id'] and not x['package_id'] and not x['owner_id'])>=qty,'Insufficient unpackaged stock; do not create negative stock')
  package=m.maps.get('stock.package',{}).get(item['source_package']) or item['existing_package']
  if not package:package=m.mutate('stock.package','create',[{'name':item['package_name']}])
  m.attach('stock.package',[(item['source_package'],package)]);m.maps.setdefault('stock.package',{})[item['source_package']]=package
  record={**item,'target_package':package,'target_line':lid,'date_after':cutoff,'status':'intent','deltas':[[[pid,loc,False,False,False],-qty],[[pid,loc,False,package,False],qty]]};m.j['opening_package_reclassifications'].append(record);m.persist()
  m.mutate('stock.move.line','write',[[lid],{'result_package_id':package,'date':cutoff}])
  m.mutate('stock.move','write',[[mid],{'date':cutoff}])
  after=m.b.read('stock.move.line',[lid],list(line.keys()))[0]
  require(rid(after['result_package_id'])==package and after['date']==cutoff and all(after[k]==line[k] for k in line if k not in ['date','result_package_id']),'Unexpected opening line change')
  qafter=m.b.search_read('stock.quant',domain,qfields);tot=totals(qafter);require(set(tot)==set(base) and all(abs(tot[k]-base[k])<1e-6 for k in base),'Product/location/lot/owner totals changed')
  record.update(status='verified',after_line=after);m.persist();print(json.dumps({'line':lid,'package':package,'qty':qty,'status':'verified'}),flush=True)
 afterq=m.b.search_read('stock.quant',domain,qfields)
 masters=m.b.read('product.product',sorted(pids),['name','uom_id','tracking','is_storable']);oldmasters=[x for x in before['products'] if x['id'] in pids];require({x['id']:x for x in masters}=={x['id']:x for x in oldmasters},'Product master changed')
 report={'database':m.b.db,'company_id':1,'source_cutoff':e['cutoff_utc'],'opening_date':cutoff,'summary':{'source_opening_package_rows':len(plan),'corrected_lines':len(m.j['opening_package_reclassifications']),'packages':len({x['target_package'] for x in m.j['opening_package_reclassifications']}),'totals_preserved':True,'products_preserved':True},'operations':m.j['opening_package_reclassifications'],'before_quants':currentq,'after_quants':afterq}
 H['save'](m.path.parent/'opening-package-correction-report.json',report);print(json.dumps(report['summary']),flush=True)
if __name__=='__main__':main()
