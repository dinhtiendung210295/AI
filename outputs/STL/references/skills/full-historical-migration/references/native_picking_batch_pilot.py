"""Two independent first-stage pickings, one native button_validate call; no retry."""
import runpy,time
from collections import defaultdict
from datetime import datetime,timedelta
from pathlib import Path
BASE=Path(__file__).parent
def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False

def local_day(value):
    return (datetime.strptime(value,'%Y-%m-%d %H:%M:%S')+timedelta(hours=8)).date().isoformat()

def select_day(rows,pickings):
    days=defaultdict(list)
    for row in rows:
        dates={local_day(pickings[pid]['date_done']) for pid in row['pickings']}
        if len(dates)!=1:raise RuntimeError('Cross-day chain requires separate event review')
        days[next(iter(dates))].append(row)
    if not days:return None,[]
    day=min(days)
    return day,days[day]

def select_month(rows,pickings):
    months=defaultdict(list)
    for row in rows:
        dates={local_day(pickings[pid]['date_done'])[:7] for pid in row['pickings']}
        if len(dates)!=1:raise RuntimeError('Cross-month chain requires separate event review')
        months[next(iter(dates))].append(row)
    if not months:return None,[]
    month=min(months)
    return month,months[month]
def select(rows,moves,pickings):
    for i,a in enumerate(rows):
        roots={rid(moves[mid]['picking_id']) for mid in a['roots']}
        if len(roots)!=1:continue
        ap=next(iter(roots));day=local_day(pickings[ap]['date_done'])
        for b in rows[i+1:]:
            broots={rid(moves[mid]['picking_id']) for mid in b['roots']}
            if len(broots)!=1:continue
            bp=next(iter(broots))
            if local_day(pickings[bp]['date_done'])!=day or rid(pickings[bp]['picking_type_id'])!=rid(pickings[ap]['picking_type_id']):continue
            allids=set(a['moves'])|set(b['moves'])
            if set(a['moves'])&set(b['moves']):continue
            if any(set(moves[mid]['move_orig_ids'])&set(b['moves']) or set(moves[mid]['move_dest_ids'])&set(b['moves']) for mid in a['moves']):continue
            return [a,b]
    raise RuntimeError('No two independent same-day same-type first-stage pickings eligible for native pilot')

def select_ten(rows,moves,pickings):
    for start,a in enumerate(rows):
        chosen=[a]
        for b in rows[start+1:]:
            if all(can_pair(x,b,moves,pickings) for x in chosen):chosen.append(b)
            if len(chosen)==10:return chosen
    raise RuntimeError('No complete set of ten same-day same-type independent first stages')

def can_pair(a,b,moves,pickings):
    try:return len(select([a,b],moves,pickings))==2
    except RuntimeError:return False

def prepare_root_details_together(r,selected,R):
    source_ids=[lid for g,spid,tp in selected for mid in g['moves'] if rid(r.sm[mid]['picking_id'])==spid for lid in r.sm[mid]['move_line_ids']]
    if len(source_ids)!=len(set(source_ids)) or any(lid in r.maps.get('stock.move.line',{}) for lid in source_ids):raise RuntimeError('Grouped preparation requires new unmapped details')
    source_moves=[mid for g,spid,tp in selected for mid in g['moves'] if rid(r.sm[mid]['picking_id'])==spid]
    frozen={lid:r.sl[lid] for lid in source_ids}
    fresh=r.a.read('stock.move.line',source_ids,list(next(iter(frozen.values()))))
    if {x['id'] for x in fresh}!=set(source_ids) or any(x!=frozen[x['id']] for x in fresh):raise RuntimeError('Grouped frozen source detail changed')
    fields=['state','date','quantity_done','product_id','product_uom','location_id','location_dest_id','move_line_ids','write_date']
    fresh_moves=r.a.read('stock.move',source_moves,fields)
    if any(any(x[f]!=r.sm[x['id']][f] for f in fields) for x in fresh_moves):raise RuntimeError('Grouped source moves changed')
    pairs={int(s):t for g,_,_ in selected for s,t in r.j['groups'][str(g['source']['id'])]['move_pairs'].items()}
    target_moves=[pairs[mid] for mid in source_moves];targets=[tp for _,_,tp in selected]
    current=r.b.scan('stock.move.line',[['move_id','in',target_moves]],['state','picked'])
    if any(x['picked'] or x['state']=='done' for x in current):raise RuntimeError('Grouped preparation already picked/done')
    r.mutate('stock.picking','do_unreserve',[targets],jsonrpc=True)
    zero=r.b.read('stock.move',target_moves,['quantity','move_line_ids'])
    if any(abs(x['quantity'])>1e-8 or x['move_line_ids'] for x in zero):raise RuntimeError('Grouped unreserve postcondition failed')
    values=[]
    for lid in source_ids:
        x=r.sl[lid];unit=r.maps['uom.uom'][rid(x['product_uom_id'])];qty=R['rounded'](x['qty_done'],r.tu[unit]['rounding'])
        if abs(qty-x['qty_done'])>1e-8:r.j['rounding_differences'].append(dict(source_line=lid,source_move=rid(x['move_id']),source_qty=x['qty_done'],target_qty=qty,target_unit=unit,delta=qty-x['qty_done']))
        values.append(dict(company_id=1,move_id=pairs[rid(x['move_id'])],product_id=r.maps['product.product'][rid(x['product_id'])],product_uom_id=unit,location_id=r.maps['stock.location'][rid(x['location_id'])],location_dest_id=r.maps['stock.location'][rid(x['location_dest_id'])],lot_id=r.maps.get('stock.lot',{}).get(rid(x['lot_id']),False),quantity=qty,picked=True,date=x['date']))
    r.persist();created=r.mutate('stock.move.line','create',[values])
    if len(created)!=len(source_ids) or len(set(created))!=len(created):raise RuntimeError('Grouped detail creation incomplete')
    actual={x['id']:x for x in r.b.read('stock.move.line',created,list(values[0]))}
    for lid,want in zip(created,values):
        if any((rid(actual[lid][f]) if f.endswith('_id') else actual[lid][f])!=v for f,v in want.items()):raise RuntimeError('Grouped detail readback mismatch')
    r.attach_many('stock.move.line',list(zip(source_ids,created)))

def validate(r,groups,grouped=False,day_mode=False,month=None,stage_by_so=None):
    R=runpy.run_path(str(BASE/'migrate_pysb_independent_receipts.py'))
    selected=[];needed=defaultdict(float);all_mids=set();evidence=[]
    for g in groups:
        state=r.j['groups'][str(g['source']['id'])]
        if state['phase']!='chain_prepared' or (state.get('completed_pickings') and stage_by_so is None):raise RuntimeError('Pilot requires untouched prepared chains')
        mids=set(g['moves']);all_mids.update(state['move_pairs'].values())
        roots={rid(r.sm[mid]['picking_id']) for mid in mids if not set(r.sm[mid]['move_orig_ids'])&mids}
        if len(roots)!=1:raise RuntimeError('Ambiguous first stage')
        spid=stage_by_so[g['source']['id']] if stage_by_so is not None else next(iter(roots))
        if spid not in g['pickings'] or spid in state.get('completed_pickings',[]):raise RuntimeError('Stage already completed or outside chain')
        tp=state['picking_pairs'].get(spid,state['picking_pairs'].get(str(spid)))
        if any(x['model']=='stock.picking' and x['method']=='button_validate' and tp in x['args'][0] for x in r.j['operations']):raise RuntimeError('Prior validation attempt cannot be retried by pilot')
        if not grouped:r.prepare_picking_lines(g,spid)
        for mid in mids:
            if rid(r.sm[mid]['picking_id'])!=spid:continue
            if r.sm[mid]['move_orig_ids']:
                if stage_by_so is None:raise RuntimeError('Pilot first stage has predecessor')
                for pred in r.sm[mid]['move_orig_ids']:
                    if pred not in mids or rid(r.sm[pred]['picking_id']) not in state.get('completed_pickings',[]):raise RuntimeError('Stage predecessor not completed in journal')
            for line in r.by_move[mid]:
                if line['owner_id'] or line['package_id'] or line['result_package_id']:raise RuntimeError('Package/owner outside pilot')
                product=r.maps['product.product'][rid(line['product_id'])];unit=r.maps['uom.uom'][rid(line['product_uom_id'])]
                if r.locations[rid(line['location_id'])]['usage']!='internal':raise RuntimeError('Pilot requires internal source')
                if r.tp[product].get('is_storable'):
                    key=(product,r.maps['stock.location'][rid(line['location_id'])],r.maps.get('stock.lot',{}).get(rid(line['lot_id']),False))
                    needed[key]+=R['rounded'](line['qty_done'],r.tu[unit]['rounding'])*r.tu[unit]['factor']/r.tu[rid(r.tp[product]['uom_id'])]['factor']
        selected.append((g,spid,tp));evidence.append(dict(source_so=g['source']['id'],source_picking=spid,target_picking=tp,date=r.sp[spid]['date_done']))
    count_ok=len(selected)>=2 if (day_mode or month) and grouped else len(selected)==(10 if grouped else 2)
    period_ok=all(local_day(x['date'])[:7]==month for x in evidence) if month else len({local_day(x['date']) for x in evidence})==1
    if not count_ok or not period_ok:raise RuntimeError('Wrong native pilot count/period')
    if grouped:prepare_root_details_together(r,selected,R)
    targets=[x[2] for x in selected]
    checks=r.b.read('stock.picking',targets,['state','company_id','carrier_id','picking_type_id'])
    if any(x['state'] in ['draft','done','cancel'] or rid(x['company_id'])!=1 or x['carrier_id'] for x in checks) or len({rid(x['picking_type_id']) for x in checks})!=1:raise RuntimeError('Live pilot state/company/type/carrier gate failed')
    native=r.b.read('stock.move',[mid for check in r.b.read('stock.picking',targets,['move_ids']) for mid in check['move_ids']],['state','company_id','picking_id','move_orig_ids','move_dest_ids'])
    native_ids={x['id'] for x in native}
    if any(x['state'] in ['done','cancel'] or rid(x['company_id'])!=1 or (x['move_orig_ids'] and stage_by_so is None) or (set(x['move_orig_ids'])|set(x['move_dest_ids']))&native_ids for x in native):raise RuntimeError('Live pilot pickings have invalid state or interdependency')
    if stage_by_so is not None:
        expected={}
        for g,spid,tp in selected:
            pairs={int(s):t for s,t in r.j['groups'][str(g['source']['id'])]['move_pairs'].items()}
            for mid in g['moves']:
                if rid(r.sm[mid]['picking_id'])==spid:expected[pairs[mid]]={pairs[p] for p in r.sm[mid]['move_orig_ids']}
        if set(expected)!=native_ids or any(set(x['move_orig_ids'])!=expected[x['id']] for x in native):raise RuntimeError('Live stage predecessor mapping differs')
        predecessor_ids=set().union(*expected.values())
        predecessors=r.b.read('stock.move',sorted(predecessor_ids),['state','company_id']) if predecessor_ids else []
        if {x['id'] for x in predecessors}!=predecessor_ids or any(x['state']!='done' or rid(x['company_id'])!=1 for x in predecessors):raise RuntimeError('Live stage predecessor is not done')
    if needed:
        r.release_scoped_reservations(needed,all_mids)
        quants=r.b.scan('stock.quant',[['company_id','=',1],['product_id','in',sorted({k[0] for k in needed})],['location_id','in',sorted({k[1] for k in needed})],['lot_id','in',sorted({k[2] for k in needed})],['package_id','=',False],['owner_id','=',False]],['product_id','location_id','lot_id','quantity','reserved_quantity'])
        R['assert_exact_stock'](needed,quants)
    pilot=dict(status='preflight_verified',pickings=evidence,native_method='stock.picking.button_validate',expected_validate_rpc_calls=1,malaysia_month=month,stage_batch=stage_by_so is not None,dependent_stage=any(r.sm[mid]['move_orig_ids'] for g,spid,tp in selected for mid in g['moves'] if rid(r.sm[mid]['picking_id'])==spid))
    r.j.setdefault('native_batch_pilots',[]).append(pilot);r.persist()
    started=time.perf_counter()
    result=r.mutate('stock.picking','button_validate',[targets],context={'skip_backorder':True,'picking_ids_not_to_backorder':targets,'skip_redirection':True})
    after=r.b.read('stock.picking',targets,['state','company_id','move_ids','date_done'])
    pilot.update(result=result,after=after,elapsed_validate_and_header_read_seconds=time.perf_counter()-started);r.persist()
    if {x['id'] for x in after}!=set(targets) or any(x['state']!='done' or rid(x['company_id'])!=1 for x in after):raise RuntimeError('Native multi-validate incomplete; readback required, never retry')
    r.native_batch_validated=set(targets)
    for g,spid,tp in selected:r.finish(g,only_picking=spid)
    pilot['status']='all_validated_and_historical_dates_restored' if day_mode or month else 'both_validated_and_historical_dates_restored';r.persist()
    return pilot

def month_ready_events(r,groups,month):
    ready=[]
    for g in groups:
        state=r.j['groups'][str(g['source']['id'])];done=set(state.get('completed_pickings',[]))
        if state['phase']=='completed':continue
        for pid in g['pickings']:
            if local_day(r.sp[pid]['date_done'])[:7]!=month:raise RuntimeError('Monthly scope mismatch')
            if pid in done:continue
            preds={rid(r.sm[p]['picking_id']) for mid in g['moves'] if rid(r.sm[mid]['picking_id'])==pid for p in r.sm[mid]['move_orig_ids']}
            if preds<=done:ready.append((r.sp[pid]['date_done'],pid,g))
    return sorted(ready,key=lambda e:(e[0],e[1]))

def restore_recorded_batches(r,groups):
    """Resume dates only for a batch with returned Validate and recorded all-Done readback."""
    if r.uncertain:raise RuntimeError('Uncertain write requires separate recovery')
    by_so={g['source']['id']:g for g in groups};pending=[]
    for batch in r.j.get('native_batch_pilots',[]):
        entries=[p for p in batch['pickings'] if p['source_so'] in by_so and p['source_picking'] not in r.j['groups'][str(p['source_so'])].get('completed_pickings',[])]
        if not entries:continue
        after={x['id']:x for x in batch.get('after',[])};targets={p['target_picking'] for p in batch['pickings']}
        attempts=[op for op in r.j['operations'] if op['model']=='stock.picking' and op['method']=='button_validate' and set(op['args'][0])==targets]
        if len(attempts)!=1 or attempts[0]['status']!='returned' or set(after)!=targets or any(x['state']!='done' or rid(x['company_id'])!=1 for x in after.values()):raise RuntimeError('Batch lacks unambiguous returned Validate and Done proof')
        pending.extend(entries)
    if not pending:return
    mids={mid for p in pending for mid in by_so[p['source_so']]['moves']}
    fields=['state','date','quantity_done','product_id','product_uom','location_id','location_dest_id','move_line_ids','write_date','move_orig_ids','move_dest_ids']
    source=r.a.read('stock.move',sorted(mids),fields)
    if {x['id'] for x in source}!=mids or any(any((set(x[f])!=set(r.sm[x['id']][f])) if f.endswith('_ids') else x[f]!=r.sm[x['id']][f] for f in fields) for x in source):raise RuntimeError('Source changed before batch date recovery')
    targets={p['target_picking'] for p in pending};live=r.b.read('stock.picking',sorted(targets),['state','company_id','move_ids'])
    if {x['id'] for x in live}!=targets or any(x['state']!='done' or rid(x['company_id'])!=1 for x in live):raise RuntimeError('Recorded batch is no longer Done')
    for p in pending:
        state=r.j['groups'][str(p['source_so'])];g=by_so[p['source_so']];pairs={int(s):t for s,t in state['move_pairs'].items()}
        want={pairs[mid] for mid in g['moves'] if rid(r.sm[mid]['picking_id'])==p['source_picking']}
        if set(next(x for x in live if x['id']==p['target_picking'])['move_ids'])!=want:raise RuntimeError('Batch picking mapping changed')
    r.j.setdefault('batch_date_recoveries',[]).append(dict(pickings=live,source_moves=source,validation_repeated=False));r.persist()
    r.native_batch_validated=targets
    for p in pending:r.finish(by_so[p['source_so']],only_picking=p['source_picking'])
    for batch in r.j['native_batch_pilots']:
        if all(p['source_picking'] in r.j['groups'][str(p['source_so'])].get('completed_pickings',[]) for p in batch['pickings']):batch['status']='all_validated_and_historical_dates_restored'
    r.persist()

def stage_batch_proven(r):
    return any(x.get('stage_batch') and x.get('dependent_stage') and x.get('status')=='all_validated_and_historical_dates_restored' and all(r.j['groups'][str(p['source_so'])]['phase']=='completed' for p in x['pickings']) for x in r.j.get('native_batch_pilots',[]))

def finish_monthly(r,groups,month):
    # Prove independence before any monthly Validate call.
    owners={}
    for g in groups:
        for mid in g['moves']:
            if mid in owners:raise RuntimeError('Monthly source move shared across chains')
            owners[mid]=g['source']['id']
    for mid,owner in owners.items():
        if any(p in owners and owners[p]!=owner for p in r.sm[mid]['move_orig_ids']+r.sm[mid]['move_dest_ids']):raise RuntimeError('Cross-chain monthly dependency')
    calls=0
    while any(r.j['groups'][str(g['source']['id'])]['phase']!='completed' for g in groups):
        ready=month_ready_events(r,groups,month)
        if not ready:raise RuntimeError('No ready monthly stage; inspect dependency state')
        first=ready[0];ptype=rid(r.sp[first[1]]['picking_type_id']);chosen=[];seen=set()
        for event in ready:
            sid=event[2]['source']['id']
            if sid not in seen and rid(r.sp[event[1]]['picking_type_id'])==ptype:chosen.append(event);seen.add(sid)
        # The new dependent-stage path starts with two chains and only scales
        # after their complete chains have passed existing final verification.
        if not stage_batch_proven(r):chosen=chosen[:2]
        if len(chosen)>=2:
            validate(r,[x[2] for x in chosen],grouped=True,month=month,stage_by_so={x[2]['source']['id']:x[1] for x in chosen});calls+=1
            print({'monthly_stage_batch':len(chosen),'malaysia_month':month,'stage_sample_full_chains_verified':stage_batch_proven(r)},flush=True)
        else:r.finish(first[2],only_picking=first[1])
    return calls

def finish_daily(r,groups,day):
    """Batch independent roots by type within one Malaysia day, then dependent legs."""
    by_type=defaultdict(list)
    for i,g in enumerate(groups):
        mids=set(g['moves'])
        if any(local_day(r.sp[pid]['date_done'])!=day for pid in g['pickings']):raise RuntimeError('Daily scope mismatch')
        for other in groups[i+1:]:
            other_ids=set(other['moves'])
            if mids&other_ids or any((set(r.sm[mid]['move_orig_ids'])|set(r.sm[mid]['move_dest_ids']))&other_ids for mid in mids) or any((set(r.sm[mid]['move_orig_ids'])|set(r.sm[mid]['move_dest_ids']))&mids for mid in other_ids):raise RuntimeError('Cross-chain dependency in daily batch')
        roots={rid(r.sm[mid]['picking_id']) for mid in mids if not set(r.sm[mid]['move_orig_ids'])&mids}
        if len(roots)!=1:raise RuntimeError('Ambiguous daily root')
        state=r.j['groups'][str(g['source']['id'])]
        if state.get('completed_pickings'):raise RuntimeError('Daily batch requires untouched chains')
        by_type[rid(r.sp[next(iter(roots))]['picking_type_id'])].append(g)
    calls=0
    for same_type in by_type.values():
        if len(same_type)>=2:
            result=validate(r,same_type,grouped=True,day_mode=True)
            result['malaysia_day']=day;result['production_day_batch']=True;r.persist();calls+=1
    for date,pid,g in sorted((r.sp[pid]['date_done'],pid,g) for g in groups for pid in g['pickings']):
        done=r.j['groups'][str(g['source']['id'])].get('completed_pickings',[])
        if pid not in done and str(pid) not in done:r.finish(g,only_picking=pid)
    return calls

def finish_events_in_pairs(r,groups):
    """Keep chronological order, pair only adjacent independent untouched roots."""
    events=sorted((r.sp[pid]['date_done'],pid,g) for g in groups for pid in g['pickings'])
    i=0;paired=0
    while i<len(events):
        pair=False
        if i+1<len(events):
            a,b=events[i:i+2];ga,gb=a[2],b[2]
            sa=r.j['groups'][str(ga['source']['id'])];sb=r.j['groups'][str(gb['source']['id'])]
            if ga['source']['id']!=gb['source']['id'] and not sa.get('completed_pickings') and not sb.get('completed_pickings'):
                rows=[]
                for g in [ga,gb]:
                    mids=set(g['moves']);roots=[mid for mid in mids if not set(r.sm[mid]['move_orig_ids'])&mids]
                    rows.append(dict(source_so=g['source']['id'],roots=roots,moves=g['moves']))
                try:
                    chosen=select(rows,r.sm,r.sp)
                    pair=all({rid(r.sm[mid]['picking_id']) for mid in row['roots']}=={event[1]} for row,event in zip(chosen,[a,b]))
                except RuntimeError:pair=False
                if pair:
                    result=validate(r,[ga,gb]);result['production_pair']=True;paired+=1;i+=2
        if not pair:
            date,pid,g=events[i];r.finish(g,only_picking=pid);i+=1
    return paired
