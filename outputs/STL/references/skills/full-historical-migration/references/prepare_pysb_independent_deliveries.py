"""Read-only/local preflight for simple complete SO delivery chains.

No SO is confirmed here. Every source consumption reduces historical supply;
only verified movements or proposed earlier eligible delivery transfers add it.
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
    maps=load('after-run-stock-mapping.json')['maps'];scope=load('scope.json')
    confirmations=load('phases/so-confirmation-journal.json')['orders'] if (OUT/'phases/so-confirmation-journal.json').exists() else {}
    source={x['id']:x for x in load('source-delivery-orders.json')};target={x['id']:x for x in load('target-delivery-orders.json')}
    sl=defaultdict(list);tl={x['id']:x for x in load('target-delivery-order-lines.json')}
    for x in load('source-delivery-order-lines.json'):sl[rid(x['order_id'])].append(x)
    picks={x['id']:x for x in load('source-pickings.json')};moves={x['id']:x for x in load('source-moves.json')};by_pick=defaultdict(list);lines=defaultdict(list)
    for m in moves.values():by_pick[rid(m['picking_id'])].append(m['id'])
    for x in load('source-move-lines.json'):lines[rid(x['move_id'])].append(x)
    a=I['ReadOnly']('v14-prod',('http://175.145.85.151','paoyeang_live'))
    outside=a.read('stock.picking',sorted({i for x in source.values() for i in x['picking_ids'] if i not in picks}),['state','date_done','company_id'])
    save('source-delivery-extra-pickings.json',outside);extra={x['id']:x for x in outside}
    products={x['id']:x for x in load('target-delivery-products.json')};categories={x['id']:x for x in load('target-delivery-categories.json')}
    rules=load('target-delivery-rules.json');risk_routes={rid(x['route_id']) for x in rules if x['procure_method']!='make_to_stock'}
    route_proof=load('hq-mts-delivery-route-proof.json') if (OUT/'hq-mts-delivery-route-proof.json').exists() else {}
    opening=load('detailed-opening-comparison.json');exact={tuple(x['target_key']) for x in opening['rows'] if x['exact_match']}
    held={x['source_id'] for x in load('native-opening-comparison.json')['rows'] if not x['exact_quantity_match']}
    held.update(x['source_id'] for x in load('resolved-master-evidence.json')['issues'] if x['model']=='product.product')
    cov=load('after-run-stock-coverage.json')['results'];verified={x['source_move_id'] for x in cov if x['status']=='verified'};vt={x['target_move_id'] for x in cov if x['status']=='verified'}
    unknown={rid(x['product_id']) for x in load('target-stock-moves-in-period.json') if x['id'] not in vt}
    units={x['id']:x for x in load('source-uom.uom.json')};tu={x['id']:x for x in load('target-uom.uom.json')};sp={x['id']:x for x in load('source-products.json')};loc={x['id']:x for x in load('source-stock.location.json')}
    def mapid(model,sid):return maps.get(model,{}).get(str(sid),False)
    def amount(x,consume=False):
        q=x['qty_done'];u=rid(x['product_uom_id']);targetunit=mapid('uom.uom',u)
        if targetunit:
            precision=Decimal(str(tu[targetunit]['rounding']));rq=float((Decimal(str(q))/precision).quantize(Decimal('1'),rounding=ROUND_HALF_UP)*precision);q=max(q,rq) if consume else rq
        return q*units[rid(sp[rid(x['product_id'])]['uom_id'])]['factor']/units[u]['factor']
    def key(x,destination=False):return (rid(x['product_id']),rid(x['location_dest_id'] if destination else x['location_id']),rid(x['lot_id']),rid(x['result_package_id'] if destination else x['package_id']),rid(x['owner_id']))
    pool=defaultdict(float)
    for x in load('source-detailed-opening-reconstruction.json')['rows']:
        k=x['key'];targetkey=tuple(mapid(model,sid) if sid else False for model,sid in zip(['product.product','stock.location','stock.lot','stock.package','res.partner'],k))
        if targetkey in exact:pool[tuple(k)]=x['quantity']
    groups={};owners={}
    for sid,s in source.items():
        errors=[];route_sample=False;t=target.get(mapid('sale.order',sid));mids=sorted({mid for pid in s['picking_ids'] for mid in by_pick[pid]});pids=sorted({rid(moves[mid]['picking_id']) for mid in mids})
        if not mids:continue
        if not t:errors.append('missing_target_order')
        elif t['state'] not in ['draft','sent']:
            confirmed=confirmations.get(str(sid),{})
            if t['state'] not in ['sale','done'] or confirmed.get('status')!='verified_confirmed' or confirmed.get('target_id')!=t['id']:errors.append('existing_confirmed_order_requires_audit')
        if s['state'] not in ['sale','done']:errors.append('source_not_confirmed')
        if s['write_date']>=scope['end_utc_exclusive']:errors.append('source_header_changed_since_snapshot')
        if any(extra[i]['state']=='done' for i in s['picking_ids'] if i in extra):errors.append('done_picking_outside_scope')
        if t:
            for f,model in [('partner_id','res.partner'),('partner_invoice_id','res.partner'),('partner_shipping_id','res.partner'),('warehouse_id','stock.warehouse')]:
                if rid(t[f])!=mapid(model,rid(s[f])):errors.append('header_identity_'+f)
            # Currency identity must be proven, not guessed from a numeric ID.
            if rid(t['currency_id'])!=mapid('res.currency',rid(s['currency_id'])):errors.append('header_currency')
            for f in ['amount_untaxed','amount_tax','amount_total']:
                if abs(t[f]-s[f])>0.00501:errors.append('commercial_total_'+f)
        target_line_ids=set()
        for line in sl[sid]:
            dst=tl.get(mapid('sale.order.line',line['id']))
            if not dst:errors.append('missing_order_line');continue
            target_line_ids.add(dst['id'])
            if dst['display_type']!=line['display_type']:errors.append('line_display_type')
            if line['display_type']:continue
            pid=rid(line['product_id']);tpid=mapid('product.product',pid)
            if not tpid or rid(dst['product_id'])!=tpid or pid in held:errors.append('product_mapping_or_opening_hold');continue
            if rid(dst['product_uom_id'])!=mapid('uom.uom',rid(line['product_uom'])):errors.append('line_unit')
            for f in ['product_uom_qty','price_unit','discount','price_subtotal','price_total']:
                if abs(line[f]-dst[f])>1e-6:errors.append('commercial_line_'+f)
            if line['tax_id'] or dst['tax_ids']:errors.append('tax_requires_mapping_review')
            p=products[tpid]
            if p.get('service_tracking','no')!='no':errors.append('service_project_automation')
            if p['type']=='service' and abs(line['qty_delivered']-dst['qty_delivered'])>1e-6:errors.append('service_manual_delivery_requires_review')
            category=categories.get(rid(p['categ_id']))
            if category is None:errors.append('missing_product_category')
            routes=set(p['route_ids'])|set((category or {}).get('route_ids',[]))
            if routes&risk_routes:
                if route_proof.get('ready') and t and rid(t['warehouse_id'])==1 and routes<={4,5} and routes&risk_routes=={5}:
                    route_sample=True
                else:errors.append('procurement_route_needs_sample')
            if line['route_id']:errors.append('procurement_route_needs_sample')
            if p['type']!='service' and abs(line['qty_delivered']-line['product_uom_qty'])>1e-6:errors.append('partial_delivery_requires_split_support')
            if tpid in unknown:errors.append('unproven_target_movements')
        if t and target_line_ids!=set(t['order_line']):errors.append('extra_target_lines')
        if len({rid(picks[i]['picking_type_id']) for i in pids})!=len(pids):errors.append('split_backorder_chain_requires_mapping')
        roots=[mid for mid in mids if not (set(moves[mid]['move_orig_ids'])&set(mids))]
        if len({rid(moves[i]['picking_id']) for i in roots})!=1:errors.append('multiple_root_pickings')
        for mid in mids:
            m=moves[mid]
            if mid in verified or mapid('stock.move',mid):errors.append('existing_move_requires_audit')
            if m['origin_returned_move_id']:errors.append('return_requires_linked_flow')
            if any(i not in mids for i in m['move_orig_ids']):errors.append('external_predecessor')
            if any(i in moves and moves[i]['date']>m['date'] for i in m['move_orig_ids']):errors.append('predecessor_dated_after_consumption')
            for x in lines[mid]:
                if x['owner_id'] or x['package_id'] or x['result_package_id']:errors.append('package_owner')
                for f,model in [('product_id','product.product'),('product_uom_id','uom.uom'),('location_id','stock.location'),('location_dest_id','stock.location')]:
                    if not mapid(model,rid(x[f])):errors.append('missing_'+model)
        provenance=runpy.run_path(str(Path(__file__).with_name('delivery_line_provenance.py')))['issues'](mids,moves)
        errors.extend(x['reason'] for x in provenance)
        groups[sid]={'source_so':sid,'name':s['name'],'target_so':t['id'] if t else False,'moves':mids,'pickings':pids,'roots':roots,'requires_mts_route_sample':route_sample,'errors':sorted(set(errors)),'first_event_utc':min(moves[i]['date'] for i in mids)}
        for mid in mids:
            if mid in owners:groups[sid]['errors'].append('source_move_shared_between_orders')
            owners[mid]=sid
    for mid,m in sorted(moves.items(),key=lambda kv:(kv[1]['date'],kv[0])):
        g=groups.get(owners.get(mid));add=mid in verified
        if g:
            if 'eligible' not in g:
                demand=defaultdict(float)
                for root in g['roots']:
                    for x in lines[root]:
                        if loc[rid(x['location_id'])]['usage']=='internal':demand[key(x)]+=amount(x,True)
                        else:g['errors'].append('root_not_internal')
                shortage=[{'source_key':list(k),'available_historical':pool[k],'required':q} for k,q in demand.items() if pool[k]+1e-6<q]
                if shortage:g['errors'].append('historical_supply_shortage')
                g['shortages']=shortage;g['eligible']=not g['errors']
            add=add or g['eligible']
        for x in lines[mid]:
            if loc[rid(x['location_id'])]['usage']=='internal':pool[key(x)]-=amount(x,True)
            if add and loc[rid(x['location_dest_id'])]['usage']=='internal':pool[key(x,True)]+=amount(x)
    rows=sorted(groups.values(),key=lambda x:(x['first_event_utc'],x['source_so']))
    summary={'orders':len(rows),'proposed_eligible':sum(x['eligible'] for x in rows),'held':sum(not x['eligible'] for x in rows),'hold_reasons':dict(Counter(e for x in rows for e in set(x['errors'])))}
    save('independent-delivery-plan.json',{'write_ready':False,'scope':scope,'rows':rows,'summary':summary,'method':'Conservative historical ledger, full simple chains only; native sample and live gates still required'})
    print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
