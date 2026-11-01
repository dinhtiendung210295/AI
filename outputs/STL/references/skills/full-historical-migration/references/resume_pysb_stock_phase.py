"""Scoped stock phase: canonical writers, one lock, sample per flow, no retries."""
import argparse
import hashlib
import json
import os
import runpy
import uuid
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
I = runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'))
OUT = I['OUT']

def load(name):
    return json.loads((OUT/name).read_text(encoding='utf8'))

def now():
    return datetime.now(timezone.utc).isoformat()

def refresh_target():
    """Keep frozen source; archive previous target evidence before recapture."""
    b = I['ReadOnly']('v19-prod', ('https://py19.odoo.com','py19-main-33843450'))
    maps = load('after-run-stock-mapping.json')['maps']
    headerfields = list(load('target-delivery-orders.json')[0])
    linefields = list(load('target-delivery-order-lines.json')[0])
    ids = [maps.get('sale.order',{}).get(str(x['id'])) for x in load('source-delivery-orders.json')]
    headers = b.read('sale.order',ids,headerfields)
    lines = b.read('sale.order.line',[i for x in headers for i in x['order_line']],linefields)
    rid=lambda x:x[0] if isinstance(x,(list,tuple)) and x else x or False
    products=b.read('product.product',{rid(x['product_id']) for x in lines if x['product_id']},list(load('target-delivery-products.json')[0]))
    categories=b.read('product.category',{rid(x['categ_id']) for x in products},list(load('target-delivery-categories.json')[0]))
    routes=b.read('stock.route',{i for x in products+categories for i in x['route_ids']},list(load('target-delivery-routes.json')[0]))
    rules=b.read('stock.rule',{i for x in routes for i in x['rule_ids']},list(load('target-delivery-rules.json')[0]))
    existing_products=load('target-products.json')
    stock_products=b.read('product.product',{x['id'] for x in existing_products}|{x['id'] for x in products},list(existing_products[0]))
    history = OUT/'stock-phase-target-history'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    history.mkdir(parents=True)
    for name, rows in [('target-delivery-orders.json',headers),('target-delivery-order-lines.json',lines),('target-delivery-products.json',products),('target-delivery-categories.json',categories),('target-delivery-routes.json',routes),('target-delivery-rules.json',rules),('target-products.json',stock_products)]:
        (history/name).write_bytes((OUT/name).read_bytes())
        I['save'](name,rows)
    I['save']('stock-phase-target-refresh.json',dict(captured_utc=now(),headers=len(headers),lines=len(lines),source_snapshot_preserved=True,previous_evidence=str(history.relative_to(OUT))))
    print(json.dumps(dict(target_headers=len(headers),target_lines=len(lines))),flush=True)

def execute(kind, limit, mode, source_so=None, bulk_pilot=False, bulk_pairs=False, bulk_ten=False, daily=False, resume_unvalidated=False, monthly=False, month=None):
    handoff=OUT/'phases/stock-offset-handoff.json'
    if handoff.exists() and load('phases/stock-offset-handoff.json').get('requested'):raise RuntimeError('Opening-offset handoff: finish current group, stop before next group')
    priority=OUT/'phases/stock-receipts-priority.json'
    if kind!='receipt' and priority.exists() and load('phases/stock-receipts-priority.json').get('handoff_requested'):raise RuntimeError('Receipt-priority handoff: stop before next stock group')
    C = runpy.run_path(str(BASE/'run_pysb_phased_migration.py'))
    lock = runpy.run_path(str(BASE/'production_write_lock.py'))['acquire'](OUT)
    activated = False
    previous_token = os.environ.get('PYSB_PHASE_TOKEN')
    try:
        if (OUT/'phases/operator-month-first-stock-order.json').exists():
            if month!='2026-08':raise RuntimeError('Month-first gate: only explicit August scope may resume until August is reconciled')
        identity, _ = C['validate_context'](OUT)
        C['require_previous_gate'](OUT,'stock',identity)
        if runpy.run_path(str(BASE/'production_operation_log.py'))['OperationLog'](OUT/'phases',identity).unresolved():raise RuntimeError('Unresolved phase operation')
        approval = load('phases/operator-stock-resume-approval.json')
        if approval.get('identity') != identity or not approval.get('stock_authorized') or approval.get('accounting_authorized'):
            raise RuntimeError('Scoped stock authorization missing')
        # validate_context also rejects all prior uncertain stock operations.
        token = uuid.uuid4().hex
        I['save']('phases/phased-control-enabled.json',dict(identity=identity,supported_phases=['stock'],status='Stock group active; accounting disabled'))
        I['save']('phases/active-phase.json',dict(identity=identity,phase='stock',token=token,pid=os.getpid(),started_utc=now()))
        os.environ['PYSB_PHASE_TOKEN']=token
        activated=True
        filenames={'receipt':'migrate_pysb_independent_receipts.py','inventory':'migrate_pysb_inventory_adjustments.py','mo':'migrate_pysb_independent_mos.py','delivery':'migrate_pysb_independent_deliveries.py'}
        writer_sha256=hashlib.sha256((BASE/filenames[kind]).read_bytes()).hexdigest()
        batch_adapter_sha256=hashlib.sha256((BASE/'native_picking_batch_pilot.py').read_bytes()).hexdigest()
        M=runpy.run_path(str(BASE/filenames[kind]));r=M['Run']()
        if resume_unvalidated:
            if kind!='delivery' or r.uncertain:raise RuntimeError('Only known unvalidated delivery preparation can resume')
            r.resume_unvalidated=True
        rpc_counts=Counter();measured_start=time.perf_counter()
        if bulk_ten or monthly:
            for label,reader in [('source',r.a),('target',r.b)]:
                original=reader.call
                def measured_call(model,method,args,kwargs=None,_original=original,_label=label):
                    rpc_counts[_label+'.'+model+'.'+method]+=1
                    return _original(model,method,args,kwargs)
                reader.call=measured_call
            original_mutate=r.mutate
            def measured_mutate(model,method,args,**kwargs):
                rpc_counts['write.'+model+'.'+method]+=1
                return original_mutate(model,method,args,**kwargs)
            r.mutate=measured_mutate
        if kind=='receipt':
            approval=load('phases/operator-receipt-resume-approval.json')
            if not approval.get('approved') or approval.get('identity')!=identity:raise RuntimeError('Receipt-specific approval missing')
            rows=[x for x in r.plan() if not x['issues'] and x['target']['state']=='purchase' and not r.j['groups'].get(str(x['source']['id']),{}).get('execution_hold') and r.j['groups'].get(str(x['source']['id']),{}).get('phase')!='completed']
            samplepath=OUT/'phases/stock-receipt-samples.json'
            samples=load('phases/stock-receipt-samples.json') if samplepath.exists() else {'flows':[]}
            proven={json.dumps(x) for x in samples['flows']}
            flow=lambda x:json.dumps((len(x['pickings']),tuple(sorted({r.tp[r.maps['product.product'][M['rid'](r.sm[mid]['product_id'])]]['tracking'] for mid in x['moves']}))))
            completed=lambda x:r.j['groups'].get(str(x['source']['id']),{}).get('phase')=='completed'
        elif kind=='inventory':
            rows=[x for x in r.plan['groups'] if x['eligible'] and x['group_key'] not in r.j['groups']]
            proven={json.dumps(x['flow']) for x in r.j['groups'].values() if x['status']=='verified_done'}
            flow=lambda x:json.dumps(r.flow(x))
            completed=lambda x:r.j['groups'].get(x['group_key'],{}).get('status')=='verified_done'
        elif kind=='mo':
            rows=sorted([x for x in r.plan['rows'] if x['eligible'] and not r.j['mos'].get(str(x['source_mo']),{}).get('execution_hold') and r.j['mos'].get(str(x['source_mo']),{}).get('status')!='verified_done'],key=lambda x:(x['event_utc'],x['source_mo']))
            proven={r.flow({'source_mo':int(sid)}) for sid,state in r.j['mos'].items() if state['status']=='verified_done'}
            flow=r.flow
            completed=lambda x:r.j['mos'].get(str(x['source_mo']),{}).get('status')=='verified_done'
        else:
            if r.uncertain:raise RuntimeError('Uncertain delivery operation')
            if source_so and r.j['groups'].get(str(source_so),{}).get('phase')=='confirmation_held':
                row=next(x for x in r.planrows if x['source_so']==source_so and x['eligible'])
                runpy.run_path(str(BASE/'reopen_confirmed_delivery_hold.py'))['reopen'](r,r.group(row),load('phases/so-confirmation-journal.json')['orders'])
            rows=[x for x in r.planrows if x['eligible'] and not r.j['groups'].get(str(x['source_so']),{}).get('execution_hold') and r.j['groups'].get(str(x['source_so']),{}).get('phase')!='completed']
            proven={r.flow(x) for x in r.planrows if r.j['groups'].get(str(x['source_so']),{}).get('phase')=='completed'}
            flow=r.flow
            completed=lambda x:r.j['groups'].get(str(x['source_so']),{}).get('phase')=='completed'
            if source_so:rows=[x for x in rows if x['source_so']==source_so]
        if month:
            local_day=runpy.run_path(str(BASE/'native_picking_batch_pilot.py'))['local_day']
            if kind in ['receipt','delivery','inventory']:rows=[x for x in rows if x.get('moves') and all(local_day(r.sm[mid]['date'])[:7]==month for mid in x['moves'])]
            else:raise RuntimeError('MO month filter requires full raw/finished event adapter; use reviewed August-only plan')
        selected=rows[:1 if mode=='sample' else limit]
        processing_day=None;day_candidates=0
        if daily:
            if not load('phases/operator-daily-stock-approval.json').get('approved') or load('phases/native-bulk-ten-pilot.json')['status']!='all_full_chains_verified':raise RuntimeError('Daily approval and verified ten-picking sample required')
            processing_day,selected=runpy.run_path(str(BASE/'native_picking_batch_pilot.py'))['select_day'](rows,r.sp)
            day_candidates=len(selected)
        processing_month=None
        if monthly:
            if not load('phases/operator-monthly-stock-approval.json').get('approved') or load('phases/native-bulk-ten-pilot.json')['status']!='all_full_chains_verified':raise RuntimeError('Monthly approval and verified native sample required')
            processing_month,selected=runpy.run_path(str(BASE/'native_picking_batch_pilot.py'))['select_month'](rows,r.sp)
            day_candidates=len(selected)
        if bulk_ten:bulk_pilot=True
        if bulk_pilot:
            if kind!='delivery' or mode!='sample':raise RuntimeError('Bulk pilot is delivery sample only')
            if not load('phases/operator-native-bulk-validate-approval.json').get('approved'):raise RuntimeError('Native bulk pilot approval missing')
            action=load('phases/native-bulk-validate-live-action.json')['actions']
            if len(action)!=1 or action[0]['state']!='code' or 'records.button_validate()' not in action[0]['code']:raise RuntimeError('Native list Validate action not verified')
            if bulk_ten:
                if not load('phases/operator-native-bulk-ten-approval.json')['approved'] or load('phases/native-bulk-validate-pilot.json')['status']!='both_full_chains_verified':raise RuntimeError('Ten-picking pilot approval or two-picking sample missing')
            selected=runpy.run_path(str(BASE/'native_picking_batch_pilot.py'))['select_ten' if bulk_ten else 'select']([x for x in rows if str(x['source_so']) not in r.j['groups']],r.sm,r.sp)
        if selected and not bulk_pilot:
            if flow(selected[0]) not in proven:selected=selected[:1]
            else:selected=selected[:next((i for i,x in enumerate(selected) if flow(x) not in proven),len(selected))]
        if monthly and selected and not runpy.run_path(str(BASE/'native_picking_batch_pilot.py'))['stage_batch_proven'](r):
            selected=[x for x in selected if flow(x)==flow(selected[0])][:2]
        print(json.dumps(dict(kind=kind,pending=len(rows),selected=len(selected),mode=mode,malaysia_day=processing_day,malaysia_month=processing_month,eligible_period_candidates=day_candidates)),flush=True)
        if kind=='receipt':
            for g in selected:r.process(g,prepare_only=True)
            for date,pid,g in sorted((r.sp[pid]['date_done'],pid,g) for g in selected for pid in g['pickings']):r.finish(g,only_picking=pid)
            for g in selected:
                if completed(g) and json.loads(flow(g)) not in samples['flows']:samples['flows'].append(json.loads(flow(g)))
            I['save']('phases/stock-receipt-samples.json',samples)
        elif kind=='delivery':
            preparation_started=time.perf_counter()
            groups=[r.group(x) for x in selected]
            if monthly and resume_unvalidated:
                runpy.run_path(str(BASE/'native_picking_batch_pilot.py'))['restore_recorded_batches'](r,groups)
            for g in groups:
                if r.j['groups'].get(str(g['source']['id']),{}).get('phase')=='chain_prepared':
                    r.round_prepared_quantity=M['R']['rounded']
                    runpy.run_path(str(BASE/'prepared_delivery_readback.py'))['verify'](r,g)
                r.prepare(g)
            groups=[g for g in groups if not r.j['groups'].get(str(g['source']['id']),{}).get('execution_hold')]
            preparation_seconds=time.perf_counter()-preparation_started
            if monthly:print(json.dumps(dict(malaysia_month=processing_month,prepared_chains=len(groups),preparation_seconds=preparation_seconds)),flush=True)
            if bulk_pilot:
                if len(groups)!=(10 if bulk_ten else 2):raise RuntimeError('All pilot chains must pass preparation')
                pilot=runpy.run_path(str(BASE/'native_picking_batch_pilot.py'))['validate'](r,groups,grouped=bulk_ten)
            if monthly:
                started=time.perf_counter()
                calls=runpy.run_path(str(BASE/'native_picking_batch_pilot.py'))['finish_monthly'](r,groups,processing_month)
                print(json.dumps(dict(malaysia_month=processing_month,native_monthly_validate_calls=calls,finish_seconds=time.perf_counter()-started)),flush=True)
            elif daily:
                calls=runpy.run_path(str(BASE/'native_picking_batch_pilot.py'))['finish_daily'](r,groups,processing_day)
                print(json.dumps(dict(malaysia_day=processing_day,native_daily_validate_calls=calls)),flush=True)
            elif bulk_pairs:
                if load('phases/native-bulk-validate-pilot.json')['status']!='both_full_chains_verified' or not load('phases/operator-native-bulk-pairs-approval.json')['approved']:raise RuntimeError('Verified pair sample and continuation approval required')
                paired_calls=runpy.run_path(str(BASE/'native_picking_batch_pilot.py'))['finish_events_in_pairs'](r,groups)
                print(json.dumps(dict(native_two_picking_validate_calls=paired_calls)),flush=True)
            else:
                for date,pid,g in sorted((r.sp[pid]['date_done'],pid,g) for g in groups for pid in g['pickings']):r.finish(g,only_picking=pid)
            if bulk_pilot:
                pilot['status']='all_full_chains_verified' if bulk_ten else 'both_full_chains_verified'
                if bulk_ten:pilot.update(measured_seconds_after_reader_initialization=time.perf_counter()-measured_start,rpc_method_counts=dict(rpc_counts))
                r.persist();I['save']('phases/native-bulk-ten-pilot.json' if bulk_ten else 'phases/native-bulk-validate-pilot.json',pilot)
        else:
            for row in selected:r.process(row)
        result=dict(kind=kind,selected=len(selected),verified=sum(completed(x) for x in selected),malaysia_day=processing_day,malaysia_month=processing_month,eligible_period_candidates=day_candidates,completed_utc=now(),code_sha256=writer_sha256,batch_adapter_sha256=batch_adapter_sha256)
        if monthly:result.update(preparation_seconds=preparation_seconds,measured_seconds_after_reader_initialization=time.perf_counter()-measured_start,rpc_method_counts=dict(rpc_counts))
        if monthly:I['save']('phases/monthly-stock-run-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json',result)
        I['save']('phases/stock-last-group.json',result)
        print(json.dumps(result),flush=True)
        if result['verified']!=len(selected):raise RuntimeError('Stock group incomplete or held; inspect readback before continuation')
    except Exception as error:
        I['save']('phases/stock-last-error.json',dict(kind=kind,source_so=source_so,error_type=type(error).__name__,error=str(error),stopped_utc=now(),automatic_retry=False))
        raise
    finally:
        if activated:
            I['save']('phases/active-phase.json',dict(phase=None,pid=None,token=None,stopped_utc=now()))
            I['save']('phases/phased-control-enabled.json',dict(identity=identity,supported_phases=[],status='Stock group finished; writer disabled',completed_utc=now()))
        if previous_token is None:os.environ.pop('PYSB_PHASE_TOKEN',None)
        else:os.environ['PYSB_PHASE_TOKEN']=previous_token
        lock.close()
        if activated:
            try:runpy.run_path(str(BASE/'report_pysb_stock_resume.py'))['main']()
            except Exception as report_error:I['save']('phases/stock-report-error.json',dict(error=str(report_error),captured_utc=now(),erp_mutations=0))

def main():
    p=argparse.ArgumentParser();p.add_argument('--refresh-target',action='store_true');p.add_argument('--kind',choices=['receipt','inventory','mo','delivery']);p.add_argument('--mode',choices=['sample','batch'],default='sample');p.add_argument('--limit',type=int,default=10);p.add_argument('--source-so',type=int);p.add_argument('--bulk-pilot',action='store_true');p.add_argument('--bulk-pairs',action='store_true');p.add_argument('--bulk-ten',action='store_true');p.add_argument('--daily',action='store_true');p.add_argument('--monthly',action='store_true');p.add_argument('--resume-unvalidated',action='store_true');p.add_argument('--month',choices=['2026-08','2026-09','2026-10']);a=p.parse_args()
    if a.monthly and (a.kind!='delivery' or a.mode!='batch' or a.daily or a.bulk_pilot or a.bulk_pairs or a.bulk_ten or a.source_so):raise RuntimeError('Monthly mode is separate delivery batch mode')
    if a.resume_unvalidated and a.kind!='delivery':raise RuntimeError('Unvalidated continuation is delivery only')
    if a.daily and (a.kind!='delivery' or a.mode!='batch' or a.bulk_pilot or a.bulk_pairs or a.bulk_ten or a.source_so):raise RuntimeError('Daily mode is separate delivery batch mode')
    if a.bulk_ten and (a.bulk_pilot or a.bulk_pairs):raise RuntimeError('Choose one native pilot mode')
    if a.bulk_pairs and (a.kind!='delivery' or a.bulk_pilot):raise RuntimeError('Pair continuation is delivery only and separate from pilot')
    if a.refresh_target:
        if a.kind:raise RuntimeError('Read-only refresh is separate from execution')
        refresh_target();return
    if not a.kind or not 1<=a.limit<=10:raise RuntimeError('Select stock kind and limit 1..10')
    execute(a.kind,a.limit,a.mode,a.source_so,a.bulk_pilot,a.bulk_pairs,a.bulk_ten,a.daily,a.resume_unvalidated,a.monthly,a.month)

if __name__=='__main__':main()
