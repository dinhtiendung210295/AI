"""Offline proposal for real source inventory deltas, complete source groups only."""
import json
import runpy
from pathlib import Path
from collections import defaultdict,Counter
from decimal import Decimal,ROUND_HALF_UP
BASE=Path(__file__).parent
I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'));OUT=I['OUT']
C=runpy.run_path(str(BASE/'inventory_count_checks.py'))
rid=C['rid']
def load(name):return json.loads((OUT/name).read_text(encoding='utf8'))


def main():
    scope=load('scope.json');maps=load('after-run-stock-mapping.json')['maps'];coverage=load('after-run-stock-coverage.json')['results']
    verified={x['source_move_id'] for x in coverage if x['status'] in ['verified','approved_exception']}
    target_verified={x['target_move_id'] for x in coverage if x['status'] in ['verified','approved_exception']}
    inventory_ids={x['source_move_id'] for x in coverage if x['category']=='inventory_adjustment'}
    moves={x['id']:x for x in load('source-moves.json')};details=defaultdict(list)
    for x in load('source-move-lines.json'):details[rid(x['move_id'])].append(x)
    headers={x['id']:x for x in load('source-inventory-adjustment-headers.json')};counts=load('source-inventory-adjustment-count-lines.json')
    extras={x['id']:x for x in load('source-inventory-adjustment-extra-moves.json')}
    source_products={x['id']:x for x in load('source-products.json')};products={x['id']:x for x in load('target-inventory-adjustment-products.json')}
    source_units={x['id']:x for x in load('source-uom.uom.json')};target_units={x['id']:x for x in load('target-uom.uom.json')}
    locations={x['id']:x for x in load('source-stock.location.json')}
    lots={x['id']:x for x in load('source-inventory-adjustment-lots.json')};target_lots=load('target-inventory-adjustment-lots.json')
    held={x['source_id'] for x in load('native-opening-comparison.json')['rows'] if not x['exact_quantity_match']}
    issues=load('resolved-master-evidence.json')['issues'];held.update(x['source_id'] for x in issues if x['model']=='product.product')
    held_units={x['source_id'] for x in issues if x['model']=='uom.uom'}
    unknown_products={rid(x['product_id']) for x in load('target-stock-moves-in-period.json') if x['id'] not in target_verified}
    original_opening={tuple(x['key']):x['quantity'] for x in load('source-detailed-opening-reconstruction.json')['rows']}
    opening={tuple(x['target_key']):x for x in load('detailed-opening-comparison.json')['rows']}
    def mapid(model,sid):return maps.get(model,{}).get(str(sid)) if sid else False
    def source_key(line,destination=False):return (rid(line['product_id']),rid(line['location_dest_id'] if destination else line['location_id']),rid(line['lot_id']),rid(line['result_package_id'] if destination else line['package_id']),rid(line['owner_id']))
    def amount(line,consume=False):
        unit=rid(line['product_uom_id']);base=rid(source_products[rid(line['product_id'])]['uom_id']);quantity=line['qty_done'];tu=mapid('uom.uom',unit)
        if tu:
            step=Decimal(str(target_units[tu]['rounding']));rounded=float((Decimal(str(quantity))/step).quantize(Decimal('1'),rounding=ROUND_HALF_UP)*step)
            quantity=max(quantity,rounded) if consume else rounded
        return quantity*source_units[base]['factor']/source_units[unit]['factor']
    groups={};owner={};rows=[];lot_resolutions={}
    for mid in sorted(inventory_ids):
        move=moves[mid];header=headers.get(rid(move['inventory_id']));gid='inventory:'+str(header['id']) if header else 'move:'+str(mid)
        group=groups.setdefault(gid,{'group_key':gid,'source_inventory':header['id'] if header else False,'name':header['name'] if header else move['name']+' [v14:'+str(mid)+']','moves':[],'pending_moves':[],'errors':[]})
        group['moves'].append(mid);owner[mid]=gid
        row={'source_move':mid,'group_key':gid,'already_verified':mid in verified,'errors':[]};rows.append(row)
        if mid in verified:continue
        group['pending_moves'].append(mid);errors=row['errors'];pid=rid(move['product_id']);tpid=mapid('product.product',pid);product=products.get(tpid)
        if mapid('stock.move',mid):errors.append('existing_mapping_requires_audit')
        if pid in held or not product:errors.append('product_mapping_opening_or_tracking_hold')
        if tpid in unknown_products:errors.append('unproven_target_period_movements')
        if len(details[mid])!=1:errors.append('multiple_inventory_details_require_review');continue
        detail=details[mid][0];su=rid(move['product_uom']);tu=mapid('uom.uom',su)
        if not tu or su in held_units:errors.append('unit_mapping_requires_review')
        if product and (not product['is_storable']):errors.append('native_product_not_storable')
        alias=None
        if product and tu!=rid(product['uom_id']):
            policy=load('inventory-unit-alias-validation.json') if (OUT/'inventory-unit-alias-validation.json').exists() else {}
            try:
                if not policy.get('enabled') or policy.get('scope')!=scope or str(mid) not in policy['moves'] or su!=rid(source_products[pid]['uom_id']):raise ValueError('Inventory unit alias not validated for this frozen source move')
                proof=runpy.run_path(str(BASE/'same_factor_unit_alias.py'))['prove'](tu,rid(product['uom_id']),target_units)
                if proof!=policy['moves'][str(mid)]['proof']:raise ValueError('Inventory alias proof changed')
                alias=proof;tu=rid(product['uom_id'])
            except ValueError:errors.append('native_base_unit_alias_requires_verification')
        if any(detail[field] for field in ['owner_id','package_id','result_package_id']):errors.append('inventory_owner_package_requires_review')
        src=rid(move['location_id']);dst=rid(move['location_dest_id'])
        if locations[src]['usage']=='inventory' and locations[dst]['usage']=='internal':sign=1;internal=dst;virtual=src
        elif locations[src]['usage']=='internal' and locations[dst]['usage']=='inventory':sign=-1;internal=src;virtual=dst
        else:errors.append('inventory_direction_requires_review');continue
        tloc=mapid('stock.location',internal);tvirtual=mapid('stock.location',virtual)
        if not tloc or not tvirtual:errors.append('location_mapping_missing')
        if product and rid(product['property_stock_inventory'])!=tvirtual:errors.append('native_inventory_location_differs')
        count=None
        if header:
            try:count=C['match_count'](move,detail,header,counts,sign,internal)
            except RuntimeError as error:errors.append(str(error))
            if header['name']!=move['inventory_id'][1] or header['write_date']>=scope['end_utc_exclusive']:errors.append('source_inventory_header_changed_since_snapshot')
            if any(extras[x]['state']=='done' for x in header['move_ids'] if x in extras):errors.append('done_inventory_move_outside_scope')
        elif abs(detail['qty_done']-move['quantity_done'])>1e-8 or rid(detail['product_uom_id'])!=su:errors.append('direct_adjustment_detail_differs')
        lotid=rid(detail['lot_id']);tlot=mapid('stock.lot',lotid)
        if lotid:
            lot=lots[lotid];matches=[x for x in target_lots if rid(x['product_id'])==tpid and x['name']==lot['name']]
            if tlot:
                if not any(x['id']==tlot for x in matches):errors.append('mapped_lot_identity_differs')
            elif len(matches)>1:errors.append('ambiguous_native_lot')
            elif matches:tlot=matches[0]['id'];lot_resolutions[str(lotid)]=tlot
        elif product and product['tracking']!='none':errors.append('required_historical_lot_missing')
        skey=(pid,internal,lotid,False,False);tkey=(tpid,tloc,tlot,False,False)
        existing=opening.get(tkey)
        if (original_opening.get(skey,0) and (not existing or not existing['exact_match'])) or (existing and not existing['exact_match']):errors.append('detailed_opening_not_proven')
        row.update(source_line=detail['id'],source_count=count,sign=sign,internal_source_location=internal,target_product=tpid,target_location=tloc,target_inventory_location=tvirtual,target_unit=tu,target_lot=tlot,source_lot=lotid,target_unit_alias_proof=alias)
    row_index={x['source_move']:x for x in rows}
    for group in groups.values():
        group['event_utc']=min(moves[mid]['date'] for mid in group['moves'])
        if len({moves[mid]['date'] for mid in group['moves']})!=1:group['errors'].append('inventory_group_multiple_dates_requires_review')
        group['errors'].extend(error for mid in group['pending_moves'] for error in row_index[mid]['errors'])
        keys=[(row_index[mid].get('target_product'),row_index[mid].get('target_location'),row_index[mid].get('source_lot')) for mid in group['pending_moves']]
        if len(keys)!=len(set(keys)):group['errors'].append('duplicate_inventory_quant_key')
        group['errors']=sorted(set(group['errors']))
    pool=defaultdict(float)
    for key,quantity in original_opening.items():
        target=tuple(mapid(model,sid) for model,sid in zip(['product.product','stock.location','stock.lot','stock.package','res.partner'],key))
        if target in opening and opening[target]['exact_match']:pool[key]=quantity
    first={min(group['moves']):group for group in groups.values()}
    for mid,move in sorted(moves.items(),key=lambda item:(item[1]['date'],item[0])):
        if mid in first:
            group=first[mid];needed=defaultdict(float)
            for source_mid in group['pending_moves']:
                row=row_index[source_mid]
                if row.get('sign')==-1:
                    for line in details[source_mid]:needed[source_key(line)]+=amount(line,True)
            shortage=[{'source_key':list(key),'available_historical':pool[key],'required':quantity} for key,quantity in needed.items() if pool[key]+1e-6<quantity]
            if shortage:group['errors'].append('historical_supply_shortage')
            group.update(shortages=shortage,eligible=bool(group['pending_moves']) and not group['errors'])
        group=groups.get(owner.get(mid));add=mid in verified or bool(group and group.get('eligible'))
        for line in details[mid]:
            if locations[rid(line['location_id'])]['usage']=='internal':pool[source_key(line)]-=amount(line,True)
            if add and locations[rid(line['location_dest_id'])]['usage']=='internal':pool[source_key(line,True)]+=amount(line)
    result={'scope':scope,'write_ready':False,'method':'Actual frozen done inventory deltas; complete source groups; no temporary stock or absolute historical counts','rows':rows,'groups':sorted(groups.values(),key=lambda x:(x['event_utc'],x['group_key'])),'lot_resolutions':lot_resolutions,
            'summary':{'source_moves':len(rows),'already_verified_moves':sum(x['already_verified'] for x in rows),'eligible_groups':sum(x['eligible'] for x in groups.values()),'eligible_moves':sum(len(x['pending_moves']) for x in groups.values() if x['eligible']),'hold_reasons':dict(Counter(error for x in groups.values() for error in set(x['errors'])))}}
    I['save']('independent-inventory-adjustment-plan.json',result);print(json.dumps(result['summary']),flush=True)


if __name__=='__main__':main()
