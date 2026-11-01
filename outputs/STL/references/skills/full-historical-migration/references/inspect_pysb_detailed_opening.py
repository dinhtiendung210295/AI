"""Read-only detailed opening reconstruction from stable quants and done lines.

Mapped scope only. This evidence cannot by itself certify full-company balances.
No write methods, no temporary stock, no borrowing from later receipts.
"""
import argparse
import json
import runpy
from collections import defaultdict
from pathlib import Path

I=runpy.run_path(str(Path(__file__).with_name('inspect_pysb_aug_oct_prod.py')))
OUT=I['OUT'];save=I['save'];ReadOnly=I['ReadOnly']
def load(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False
def fingerprint(rows):return sorted(json.dumps(x,sort_keys=True) for x in rows)

def collect(env,identity,ids,cutoff,source):
    r=ReadOnly(env,identity)
    qfields='product_id location_id lot_id package_id owner_id quantity'.split()
    domain=[['company_id','=',1],['product_id','in',ids]]
    before=r.scan('stock.quant',domain,qfields)
    quantity='qty_done' if source else 'quantity'
    fields=('product_id product_uom_id location_id location_dest_id lot_id package_id result_package_id owner_id date '+quantity).split()
    # Match native qty_available and the migration scope: completion date of
    # the parent move, even when a legacy detailed-operation date differs.
    lines=r.scan('stock.move.line',domain+[['move_id.state','=','done'],['move_id.date','>=',cutoff]],fields)
    after=r.scan('stock.quant',domain,qfields)
    if fingerprint(before)!=fingerprint(after):raise RuntimeError(env+': quants changed during read; snapshot rejected')
    products={x['id']:x for x in r.read('product.product',ids,['uom_id'])}
    unit_ids=sorted({rid(x['product_uom_id']) for x in lines}|{rid(x['uom_id']) for x in products.values()})
    units={x['id']:x for x in r.read('uom.uom',unit_ids,['factor'])}
    balance=defaultdict(float)
    for q in after:balance[(rid(q['product_id']),rid(q['location_id']),rid(q['lot_id']),rid(q['package_id']),rid(q['owner_id']))]+=q['quantity']
    for line in lines:
        pid=rid(line['product_id']);u=rid(line['product_uom_id']);base=rid(products[pid]['uom_id'])
        ratio=units[base]['factor']/units[u]['factor'] if source else units[u]['factor']/units[base]['factor']
        qty=line[quantity]*ratio
        common=(pid,rid(line['lot_id']),rid(line['owner_id']))
        balance[(common[0],rid(line['location_id']),common[1],rid(line['package_id']),common[2])]+=qty
        balance[(common[0],rid(line['location_dest_id']),common[1],rid(line['result_package_id']),common[2])]-=qty
    locations={x['id']:x for x in r.read('stock.location',sorted({k[1] for k in balance}),['usage'])}
    rows=[{'key':list(k),'quantity':q} for k,q in sorted(balance.items()) if locations[k[1]]['usage']=='internal' and abs(q)>1e-8]
    save(('source' if source else 'target')+'-detailed-opening-reconstruction.json',{'cutoff_utc_exclusive':cutoff,'date_basis':'stock.move.date','products':len(ids),'stable_quant_reads':True,'quant_count':len(after),'reversed_done_lines':len(lines),'rows':rows})
    print(json.dumps({'database':r.r.db,'products':len(ids),'quants':len(after),'reversed_done_lines':len(lines),'opening_keys':len(rows)}),flush=True)
    return rows

def main():
    p=argparse.ArgumentParser();p.add_argument('--reuse-snapshots',action='store_true');args=p.parse_args()
    scope=load('scope.json');m=load('discovery-manifest.json')['maps']
    m=runpy.run_path(str(Path(__file__).with_name('stock_confirmation_handoff.py')))['apply'](m,OUT)
    journal=load('independent-receipts-journal.json')
    for model,pairs in journal['maps'].items():
        dest=m.setdefault(model,{})
        for sid,tid in pairs.items():
            if sid in dest and dest[sid]!=tid:raise RuntimeError('Mapping conflict')
            dest[sid]=tid
    if (OUT/'opening-lot-resolution.json').exists():
        for sid,tid in load('opening-lot-resolution.json')['maps']['stock.lot'].items():
            old=m.setdefault('stock.lot',{}).get(sid)
            if old and old!=tid:raise RuntimeError('Opening lot mapping conflict')
            m['stock.lot'][sid]=tid
    scoped_ids={x['id'] for x in load('source-products.json')}
    pm={sid:tid for sid,tid in m['product.product'].items() if int(sid) in scoped_ids}
    source_ids=sorted(int(x) for x in pm)
    if args.reuse_snapshots:
        snapshots=[load(label+'-detailed-opening-reconstruction.json') for label in ['source','target']]
        if any(not x['stable_quant_reads'] or x['cutoff_utc_exclusive']!=scope['start_utc'] or x.get('date_basis')!='stock.move.date' for x in snapshots):raise RuntimeError('Invalid/stale detailed snapshot; recapture with stock.move.date basis')
        a,b=[x['rows'] for x in snapshots]
    else:
        a=collect('v14-prod',('http://175.145.85.151','paoyeang_live'),source_ids,scope['start_utc'],True)
        b=collect('v19-prod',('https://py19.odoo.com','py19-main-33843450'),sorted(set(pm.values())),scope['start_utc'],False)
    target={tuple(x['key']):x['quantity'] for x in b};mapped=defaultdict(float);rows=[];missing=[]
    for row in a:
        keys=[];errors=[]
        for model,sid in zip(['product.product','stock.location','stock.lot','stock.package','res.partner'],row['key']):
            tid=m.get(model,{}).get(str(sid)) if sid else False
            if sid and not tid:errors.append({'model':model,'source_id':sid})
            keys.append(tid)
        if errors:missing.append({**row,'missing':errors});continue
        mapped[tuple(keys)]+=row['quantity']
    for key in sorted(set(mapped)|set(target)):
        s=mapped.get(key,0);t=target.get(key,0)
        rows.append({'target_key':list(key),'source_quantity':s,'target_quantity':t,'delta':t-s,'exact_match':abs(t-s)<=1e-6})
    result={'full_company_acceptance':False,'scope':'mapped products; exact detailed keys; missing mappings retained','cutoff_utc_exclusive':scope['start_utc'],'rows':rows,'missing_source_keys':missing,'summary':{'keys':len(rows),'exact_matches':sum(x['exact_match'] for x in rows),'differences':sum(not x['exact_match'] for x in rows),'missing_source_keys':len(missing)}}
    save('detailed-opening-comparison.json',result);print(json.dumps(result['summary']),flush=True)

if __name__=='__main__':main()
