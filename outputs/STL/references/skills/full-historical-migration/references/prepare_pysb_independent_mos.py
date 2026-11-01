"""Offline conservative historical supply plan. No Odoo writes.

All source consumption reduces supply, including transactions not migrated yet.
Only verified supply and proposed earlier eligible MOs add usable supply.
Eligibility is a proposal; execution must recheck stock and native MO behavior.
"""
import json
import runpy
from collections import Counter,defaultdict
from decimal import Decimal,ROUND_HALF_UP
from pathlib import Path
I=runpy.run_path(str(Path(__file__).with_name('inspect_pysb_aug_oct_prod.py')))
OUT=I['OUT'];save=I['save']
def load(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def rid(x):return x[0] if isinstance(x,(tuple,list)) and x else x or False

def main():
    manifest=load('discovery-manifest.json');maps=manifest['maps']
    maps=runpy.run_path(str(Path(__file__).with_name('stock_confirmation_handoff.py')))['apply'](maps,OUT)
    for model,pairs in load('independent-receipts-journal.json')['maps'].items():maps.setdefault(model,{}).update(pairs)
    runtime_holds=set()
    for name in ['independent-mo-journal.json','independent-delivery-journal.json','independent-inventory-journal.json']:
        if not (OUT/name).exists():continue
        journal=load(name)
        for model,pairs in journal['maps'].items():
            target=maps.setdefault(model,{})
            for sid,tid in pairs.items():
                if sid in target and target[sid]!=tid:raise RuntimeError('MO planning journal mapping conflict')
                target[sid]=tid
        if name=='independent-mo-journal.json':runtime_holds.update(int(sid) for sid,row in journal['mos'].items() if row.get('execution_hold'))
    maps.setdefault('stock.lot',{}).update(load('opening-lot-resolution.json')['maps']['stock.lot'])
    moves={x['id']:x for x in load('source-moves.json')};mos={x['id']:x for x in load('source-mo-execution-details.json')}
    lines=defaultdict(list)
    for x in load('source-move-lines.json'):lines[rid(x['move_id'])].append(x)
    units={x['id']:x for x in load('source-uom.uom.json')};products={x['id']:x for x in load('source-products.json')};target_units={x['id']:x for x in load('target-uom.uom.json')}
    locations={x['id']:x for x in load('source-stock.location.json')}
    coverage=load('after-run-stock-coverage.json')['results'];verified={x['source_move_id'] for x in coverage if x['status']=='verified'}
    verified_targets={x['target_move_id'] for x in coverage if x['status']=='verified'}
    unproven_products={rid(x['product_id']) for x in load('target-stock-moves-in-period.json') if x['id'] not in verified_targets}
    held_products={x['source_id'] for x in load('native-opening-comparison.json')['rows'] if not x['exact_quantity_match']}
    held_products.update(x['source_id'] for x in load('resolved-master-evidence.json')['issues'] if x['model']=='product.product')
    held_lots=set(load('source-mo-lot-metadata.json')['changed_since_snapshot']) if (OUT/'source-mo-lot-metadata.json').exists() else set()
    precision_hold=set(load('mo-extra-precision-review.json')['affected_mos']) if (OUT/'mo-extra-precision-review.json').exists() else set()
    if (OUT/'operator-mo-demand-rounding-approval.json').exists():precision_hold.difference_update(load('operator-mo-demand-rounding-approval.json')['approved_source_mos'])
    opening=load('detailed-opening-comparison.json');validkeys={tuple(x['target_key']) for x in opening['rows'] if x['exact_match']}
    pool=defaultdict(float)
    for x in load('source-detailed-opening-reconstruction.json')['rows']:
        targetkey=[]
        for model,sid in zip(['product.product','stock.location','stock.lot','stock.package','res.partner'],x['key']):targetkey.append(maps.get(model,{}).get(str(sid)) if sid else False)
        if tuple(targetkey) in validkeys:pool[tuple(x['key'])]=x['quantity']
    def quantity(x,consumption=False):
        pid=rid(x['product_id']);base=rid(products[pid]['uom_id']);unit=rid(x['product_uom_id'])
        target_unit=maps.get('uom.uom',{}).get(str(unit));q=x['qty_done']
        if target_unit:
            precision=Decimal(str(target_units[target_unit]['rounding']))
            target_q=float((Decimal(str(q))/precision).quantize(Decimal('1'),rounding=ROUND_HALF_UP)*precision)
            q=max(q,target_q) if consumption else target_q
        return q*units[base]['factor']/units[unit]['factor']
    def key(x,origin=True):return (rid(x['product_id']),rid(x['location_id'] if origin else x['location_dest_id']),rid(x['lot_id']),rid(x['package_id'] if origin else x['result_package_id']),rid(x['owner_id']))
    def apply(mid,add_supply):
        for x in lines[mid]:
            if locations[rid(x['location_id'])]['usage']=='internal':pool[key(x)]-=quantity(x,True)
            if add_supply and locations[rid(x['location_dest_id'])]['usage']=='internal':pool[key(x,False)]+=quantity(x)
    grouped={};events=[];first_ids={}
    for mo in mos.values():
        mids=[i for i in mo['move_raw_ids']+mo['move_finished_ids'] if i in moves]
        for mid in mids:grouped[mid]=mo['id']
        first_ids[mo['id']]=min(mids)
        events.append((min(moves[i]['date'] for i in mids),min(mids),'mo',mo['id']))
    events.extend((m['date'],mid,'move',mid) for mid,m in moves.items())
    def event_order(event):
        date,mid,kind,sid=event;owner=sid if kind=='mo' else grouped.get(mid)
        rank=0 if kind=='mo' else (1 if not owner or mid in mos[owner]['move_raw_ids'] else 2)
        return date,first_ids[owner] if owner else mid,rank,mid
    results=[];by_mo={}
    for date,_,kind,sid in sorted(events,key=event_order):
        if kind=='move':
            owner=grouped.get(sid);record=by_mo.get(owner)
            if record and record['eligible'] and sid in mos[owner]['move_raw_ids']:
                stage=defaultdict(float)
                for x in lines[sid]:stage[key(x)]+=quantity(x,True)
                shortages=[{'source_key':list(k),'available_historical':pool[k],'required':q,'shortage':q-pool[k]} for k,q in stage.items() if pool[k]+1e-6<q]
                if shortages:
                    record['eligible']=False;record['errors'].append('historical_stage_supply_shortage');record['shortages'].extend(shortages)
            apply(sid,sid in verified or bool(record and record['eligible']));continue
        mo=mos[sid];mids=[i for i in mo['move_raw_ids']+mo['move_finished_ids'] if i in moves];errors=[];shortages=[]
        if sid in runtime_holds:errors.append('runtime_execution_hold')
        if sid in precision_hold:errors.append('mo_demand_precision_extension_not_approved')
        raw_dates=[moves[i]['date'] for i in mo['move_raw_ids'] if i in moves]
        finished_dates=[moves[i]['date'] for i in mo['move_finished_ids'] if i in moves]
        if not raw_dates or not finished_dates or min(finished_dates)<max(raw_dates):errors.append('output_before_last_material_requires_staged_review')
        for mid in mids:
            m=moves[mid];pid=rid(m['product_id']);tpid=maps['product.product'].get(str(pid))
            if not tpid or pid in held_products:errors.append('product_mapping_or_opening_hold')
            if tpid in unproven_products:errors.append('unproven_target_period_movements')
            if mid in verified or maps.get('stock.move',{}).get(str(mid)):errors.append('existing_move_requires_audit')
            for x in lines[mid]:
                if rid(x['lot_id']) in held_lots:errors.append('lot_metadata_changed_since_snapshot')
                if x['package_id'] or x['result_package_id'] or x['owner_id']:errors.append('package_owner_requires_execution_support')
                for model,field in [('uom.uom','product_uom_id'),('stock.location','location_id'),('stock.location','location_dest_id')]:
                    if not maps.get(model,{}).get(str(rid(x[field]))):errors.append('missing_'+model)
        demand=defaultdict(float)
        for mid in mo['move_raw_ids']:
            for x in lines[mid]:demand[key(x)]+=quantity(x,True)
        for k,qty in demand.items():
            if pool[k]+1e-6<qty:shortages.append({'source_key':list(k),'available_historical':pool[k],'required':qty,'shortage':qty-pool[k]})
        if shortages:errors.append('historical_supply_shortage')
        eligible=not errors
        record={'source_mo':sid,'name':mo['name'],'event_utc':date,'eligible':eligible,'errors':sorted(set(errors)),'shortages':shortages,'depends_on_prior_eligible_mos':True}
        results.append(record);by_mo[sid]=record
    result={'scope':load('scope.json'),'write_ready':False,'method':'matched detailed opening + verified supply; subtract every source consumption; proposed eligible MO supply only after its source event','rows':results,'summary':{'mos':len(results),'proposed_eligible':sum(x['eligible'] for x in results),'held':sum(not x['eligible'] for x in results),'hold_reasons':dict(Counter(e for x in results for e in x['errors']))}}
    save('independent-mo-supply-plan.json',result);print(json.dumps(result['summary']),flush=True)

if __name__=='__main__':main()
