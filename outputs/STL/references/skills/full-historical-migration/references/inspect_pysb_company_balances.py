"""Read-only full-company internal balances at four historical cutoffs.

All quant and done-line products are included, including unmapped products.
Missing dimensions and non-equivalent base units remain explicit blockers.
"""
import json
import argparse
import runpy
import socket
from datetime import datetime, timezone
from collections import defaultdict, Counter
from pathlib import Path

BASE = Path(__file__).parent
I = runpy.run_path(str(BASE / 'inspect_pysb_aug_oct_prod.py'))
OUT = I['OUT']
D = runpy.run_path(str(BASE / 'inspect_pysb_detailed_opening.py'))
rid = D['rid']
SOURCE_ROUND=runpy.run_path(str(I['ROOT']/'odoo14_PY/odoo/tools/float_utils.py'))['float_round']


def load(name):
    return json.loads((OUT / name).read_text(encoding='utf8'))


def balances(quants, lines, products, units, locations, cutoffs, source):
    results = {}
    quantity = 'qty_done' if source else 'quantity'
    for cutoff in cutoffs:
        pool = defaultdict(float)
        for q in quants:
            pool[tuple(rid(q[f]) for f in ['product_id','location_id','lot_id','package_id','owner_id'])] += q['quantity']
        for line in lines:
            if line.get('move_date',line['date']) < cutoff:
                continue
            pid = rid(line['product_id']);product=products[pid]
            if source and 'type' in product and product['type']!='product':continue
            if not source and 'is_storable' in product and not product['is_storable']:continue
            base = rid(product['uom_id'])
            unit = rid(line['product_uom_id'])
            if not source and line.get('quantity_product_uom') is not None:
                amount=line['quantity_product_uom']
            else:
                amount=(line[quantity]/units[unit]['factor']*units[base]['factor']) if source else (line[quantity]*units[unit]['factor']/units[base]['factor'])
                if units[base].get('rounding'):amount=SOURCE_ROUND(amount,precision_rounding=units[base]['rounding'],rounding_method='HALF-UP')
            common = (pid, rid(line['lot_id']), rid(line['owner_id']))
            pool[(pid,rid(line['location_id']),common[1],rid(line['package_id']),common[2])] += amount
            pool[(pid,rid(line['location_dest_id']),common[1],rid(line['result_package_id']),common[2])] -= amount
        results[cutoff] = [{'key':list(k),'quantity':v} for k,v in sorted(pool.items())
                           if locations[k[1]]['usage']=='internal' and abs(v)>1e-8]
    return results


def collect(label, identity, cutoffs, source, extra_product_ids=()):
    r = I['ReadOnly'](label, identity)
    domain = [['company_id','=',1]]
    qfields = 'product_id location_id lot_id package_id owner_id quantity'.split()
    before = r.scan('stock.quant',domain,qfields)
    fields = ('move_id product_id product_uom_id location_id location_dest_id lot_id package_id result_package_id owner_id date '+('qty_done' if source else 'quantity quantity_product_uom')).split()
    line_domain=domain+[['move_id.state','=','done'],['move_id.date','>=',min(cutoffs)]]
    lines = r.scan('stock.move.line',line_domain,fields)
    parent_ids=sorted({rid(x['move_id']) for x in lines})
    parent_rows=r.read('stock.move',parent_ids,['date','state','company_id','write_date'])
    parents={x['id']:x for x in parent_rows}
    if any(x['state']!='done' or rid(x['company_id'])!=1 for x in parent_rows):raise RuntimeError('Company balance parent move drift')
    for line in lines:line['move_date']=parents[rid(line['move_id'])]['date']
    after = r.scan('stock.quant',domain,qfields)
    if D['fingerprint'](before)!=D['fingerprint'](after):
        raise RuntimeError('Company quants changed during capture: '+label)
    if D['fingerprint'](parent_rows)!=D['fingerprint'](r.read('stock.move',parent_ids,['date','state','company_id','write_date'])) or r.call('stock.move.line','search_count',[line_domain])!=len(lines):raise RuntimeError('Company balance movement dates changed during capture: '+label)
    stock_pids={rid(x['product_id']) for x in after+lines}
    products={x['id']:x for x in r.read('product.product',sorted(stock_pids),['uom_id','type','is_storable','company_id'])}
    extra=set(extra_product_ids)-stock_pids
    if extra:
        accessible=r.scan('product.product',[['id','in',sorted(extra)],['company_id','in',[False,1]]],['uom_id','type','is_storable','company_id'])
        products.update({x['id']:x for x in accessible})
    unavailable_extra=sorted(extra-set(products))
    uids = sorted({rid(x['product_uom_id']) for x in lines}|{rid(x['uom_id']) for x in products.values()})
    if not source:uids=sorted(set(uids)|set(load('discovery-manifest.json')['maps']['uom.uom'].values()))
    units = {x['id']:x for x in r.read('uom.uom',uids,['factor','rounding','relative_factor','relative_uom_id'])}
    if not source:
        while True:
            missing=sorted({rid(x.get('relative_uom_id')) for x in units.values() if x.get('relative_uom_id')}-set(units))
            if not missing:break
            units.update({x['id']:x for x in r.read('uom.uom',missing,['factor','rounding','relative_factor','relative_uom_id'])})
    lids = sorted({rid(x['location_id']) for x in after+lines}|{rid(x['location_dest_id']) for x in lines})
    locations = {x['id']:x for x in r.read('stock.location',lids,['usage'])}
    verified_semantics=(all(x.get('type') in ['product','consu','service'] for x in products.values()) if source else all(isinstance(x.get('is_storable'),bool) for x in products.values()) and all('quantity_product_uom' in x for x in lines))
    result = {'company_id':1,'unavailable_extra_product_metadata_ids':unavailable_extra,'quant_semantics_verified':verified_semantics,'quantity_basis':'v14 product-only with native product-base HALF-UP; v19 is_storable with captured quantity_product_uom','date_basis':'stock.move.date','captured_utc':datetime.now(timezone.utc).isoformat(),'stable_quant_reads':True,'all_company_products':len(products),
              'quants':after,'done_lines':lines,'products':list(products.values()),'units':list(units.values()),
              'balances':balances(after,lines,products,units,locations,cutoffs,source)}
    I['save'](('source' if source else 'target')+'-full-company-balance-snapshot.json',result)
    print(json.dumps({'environment':label,'products':len(products),'quants':len(after),'done_lines':len(lines)}),flush=True)
    return result


def main():
    socket.setdefaulttimeout(120)
    parser=argparse.ArgumentParser();parser.add_argument('--reuse-snapshots',action='store_true');parser.add_argument('--reuse-source-snapshot',action='store_true');args=parser.parse_args()
    if args.reuse_snapshots and args.reuse_source_snapshot:raise RuntimeError('Choose one snapshot reuse mode')
    scope = load('scope.json')
    cutoffs = [scope['start_utc'],'2026-08-31 16:00:00','2026-09-30 16:00:00',scope['end_utc_exclusive']]
    if args.reuse_snapshots:
        a=load('source-full-company-balance-snapshot.json');b=load('target-full-company-balance-snapshot.json')
        if any(not x['stable_quant_reads'] or set(x['balances'])!=set(cutoffs) or x['company_id']!=1 for x in [a,b]):raise RuntimeError('Invalid full-company snapshot')
    else:
        lock = runpy.run_path(str(BASE/'production_write_lock.py'))['acquire'](OUT)
        if args.reuse_source_snapshot:
            a=load('source-full-company-balance-snapshot.json')
            if a.get('company_id')!=1 or not a.get('stable_quant_reads') or a.get('date_basis')!='stock.move.date' or not a.get('quant_semantics_verified') or set(a['balances'])!=set(cutoffs):raise RuntimeError('Source snapshot not suitable for reuse')
        else:a = collect('v14-prod',('http://175.145.85.151','paoyeang_live'),cutoffs,True)
        b = collect('v19-prod',('https://py19.odoo.com','py19-main-33843450'),cutoffs,False,load('discovery-manifest.json')['maps']['product.product'].values())
    maps = load('discovery-manifest.json')['maps']
    for name in ['opening-lot-resolution.json','independent-receipts-journal.json','independent-mo-journal.json','independent-delivery-journal.json','independent-inventory-journal.json']:
        for model,pairs in load(name)['maps'].items():
            dest = maps.setdefault(model,{})
            for sid,tid in pairs.items():
                if sid in dest and dest[sid]!=tid:raise RuntimeError('Company balance mapping conflict')
                dest[sid]=tid
    records={}
    for name in ['independent-receipts-journal.json','independent-mo-journal.json','independent-delivery-journal.json','independent-inventory-journal.json']:
        for record in load(name).get('rounding_differences',[]):
            sid=record.get('source_line',record.get('source_line_id'))
            if sid is None or (sid in records and records[sid]!=record):raise RuntimeError('Company rounding record conflict')
            records[sid]=record
    blocked_units={x['source_id'] for x in load('resolved-master-evidence.json')['issues'] if x['model']=='uom.uom'}
    reports=runpy.run_path(str(BASE/'company_balance_checks.py'))['compare'](a,b,maps,records,blocked_units)
    captured=lambda name,data:data.get('captured_utc') or datetime.fromtimestamp((OUT/(name+'-full-company-balance-snapshot.json')).stat().st_mtime,timezone.utc).isoformat()
    I['save']('full-company-balances.json',{'read_only':True,'scope':scope,'full_company_capture':True,'source_quant_semantics_verified':a.get('quant_semantics_verified',False),'target_quant_semantics_verified':b.get('quant_semantics_verified',False),'source_date_basis':a.get('date_basis','legacy_stock.move.line.date'),'target_date_basis':b.get('date_basis','legacy_stock.move.line.date'),'source_captured_utc':captured('source',a),'target_captured_utc':captured('target',b),
        'target_unavailable_extra_product_metadata_ids':b.get('unavailable_extra_product_metadata_ids',[]),'comparison_note':'Source quantities are mapped totals only. Missing dimension or base-unit mappings remain in missing_source_keys. A target-only difference is not proof of a real stock shortage while source mapping is incomplete.',
        'cutoffs_exclusive':reports,'acceptance_ready':a.get('quant_semantics_verified',False) and b.get('quant_semantics_verified',False) and a.get('date_basis')=='stock.move.date' and b.get('date_basis')=='stock.move.date' and all(not v['missing_source_keys'] and all(x['matched'] or x['approved_exception'] for x in v['rows']) for v in reports.values())})
    print(json.dumps({k:v['summary'] for k,v in reports.items()}),flush=True)


if __name__=='__main__':main()
