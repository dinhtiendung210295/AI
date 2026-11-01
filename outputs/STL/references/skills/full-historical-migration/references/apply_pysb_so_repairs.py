"""Scoped SO header/line repairs with per-record lock and durable intent/result."""
import argparse
import hashlib
import json
import os
import runpy
import uuid
from pathlib import Path
BASE=Path(__file__).parent
M=runpy.run_path(str(BASE/'confirm_pysb_prod_so.py'));OUT=M['I']['OUT'];D=OUT/'so-remediation';load=M['load'];save=M['save'];rid=M['rid']

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');parser.add_argument('--all',action='store_true');args=parser.parse_args()
    plan=load(D/'repair-plan.json');identity,_=M['C']['validate_context'](OUT)
    if not load(OUT/'phases/operator-so-remediation-approval.json').get('repair_order_contacts_and_mappings'):raise RuntimeError('Operator authorization missing')
    if not args.apply:print(json.dumps(plan['counts']));return
    a=M['I']['ReadOnly']('v14-prod',('http://175.145.85.151','paoyeang_live'));b=M['I']['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    jpath=D/'repairs-journal.json';j=load(jpath) if jpath.exists() else dict(identity=identity,actions={})
    log=M['P']['Log'](OUT/'phases',identity)
    codehash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    sample=D/'repairs-sample.json'
    if args.all and (not sample.exists() or load(sample).get('code_hash')!=codehash or not load(sample).get('passed')):raise RuntimeError('Current-code repair sample required')
    targets={x['id']:x for x in load(D/'target-orders.json')};sources={x['id']:x for x in load(D/'source-orders.json')}
    source_lines={x['id']:x for x in load(D/'source-line-extra.json')};target_lines={x['id']:x for x in load(D/'target-line-extra.json')}
    completed=0
    for action in plan['actions']:
        if action['key'] in j['actions']:
            if j['actions'][action['key']]['status']!='verified':raise RuntimeError('Incomplete prior repair; readback required')
            continue
        try:lock=runpy.run_path(str(BASE/'production_write_lock.py'))['acquire'](OUT)
        except RuntimeError:print('Other writer active; repair stopped before next record',flush=True);break
        token=uuid.uuid4().hex
        try:
            log.events=log.replay()
            if log.unresolved():raise RuntimeError('Unresolved shared mutation')
            sid=action['source_id'];model=action['model'];tid=action['target_id'];source=sources[sid]
            if a.read('sale.order',[sid],list(source))[0]!=source:raise RuntimeError('Source SO changed')
            ordertid=tid if model=='sale.order' else rid(target_lines[tid]['order_id'])
            order=b.read('sale.order',[ordertid],list(targets[ordertid]))[0]
            if rid(order['company_id'])!=1 or order['state'] not in ['draft','sent','sale','done']:raise RuntimeError('Wrong company/state')
            if any(order[f]!=targets[ordertid][f] for f in ['amount_untaxed','amount_tax','amount_total','order_line','date_order']):raise RuntimeError('Order commercial data changed')
            if model=='sale.order.line':
                expected=source_lines[action['source_line_id']]
                if a.read(model,[expected['id']],list(expected))[0]!=expected:raise RuntimeError('Source line changed')
                if order['state'] not in ['draft','sent'] and 'product_id' in action['values']:raise RuntimeError('Cannot change product on confirmed order')
                before=b.read(model,[tid],list(target_lines[tid]))[0]
            else:before=order
            if any(before[f]!=value for f,value in action['before'].items()):raise RuntimeError('Repair target value changed; replan')
            save(OUT/'phases/phased-control-enabled.json',dict(identity=identity,supported_phases=['confirm-so']))
            save(OUT/'phases/active-phase.json',dict(identity=identity,phase='confirm-so',token=token,pid=os.getpid()))
            oid=identity['scope_hash']+':so-repair:'+action['key']
            entry=dict(action=action,status='prepared',before=before,order_before=order)
            j['actions'][action['key']]=entry;save(jpath,j)
            log.append_intent(dict(operation_id=oid,phase='confirm-so',source_id=sid,model=model,method='write',args=[[tid],action['values']],before=before))
            try:result=M['W']['call'](b.r,model,'write',[[tid],action['values']],{'context':dict(pysb_phase_token=token,tz='UTC',tracking_disable=True,mail_notrack=True,mail_create_nolog=True,mail_create_nosubscribe=True,mail_auto_subscribe_no_notify=True,send_email=False)})
            except Exception:
                log.mark_uncertain(oid,'SO repair RPC failed; readback required');raise
            log.append_result(oid,dict(returned=True,result=result))
            after=b.read(model,[tid],list(before))[0]
            for f,value in action['values'].items():
                if (rid(after[f]) if f in ['product_id','partner_id','partner_invoice_id','partner_shipping_id','warehouse_id'] else after[f])!=value:raise RuntimeError('Repair readback mismatch')
            for f in ['product_uom_qty','price_unit','discount','tax_ids','purchase_price'] if model=='sale.order.line' else ['amount_untaxed','amount_tax','amount_total','order_line','date_order','state','invoice_ids','picking_ids']:
                if after.get(f)!=before.get(f):raise RuntimeError('Unexpected change during repair: '+f)
            final=b.read('sale.order',[ordertid],['amount_untaxed','amount_tax','amount_total'])[0]
            if any(final[f]!=order[f] for f in ['amount_untaxed','amount_tax','amount_total']):raise RuntimeError('Repair changed order total')
            entry.update(status='verified',after=after,verified_utc=M['now']());save(jpath,j)
            completed+=1
            print(json.dumps(dict(repaired=action['key'],values=action['values'],production_lock_released_after_record=True)),flush=True)
            if not args.all:save(sample,dict(passed=True,code_hash=codehash,action=action['key']))
        finally:
            save(OUT/'phases/active-phase.json',dict(phase=None,pid=None,token=None,stopped_utc=M['now']()))
            save(OUT/'phases/phased-control-enabled.json',dict(identity=identity,supported_phases=[]));lock.close()
        if not args.all:break
    # Publish verified mappings locally; do not overwrite baseline master maps.
    if all(j['actions'].get(x['key'],{}).get('status')=='verified' for x in plan['actions']):
        line_map={int(k):v for k,v in load(OUT/'resolved-master-evidence.json')['maps']['sale.order.line'].items()}
        routes={line_map[x['id']]:rid(x.get('route_id')) for x in source_lines.values() if x['id'] in line_map}
        save(D/'applied-overlay.json',dict(maps=plan['maps'],reviewed_source_header_timestamp_ids=plan['reviewed_source_header_timestamp_ids'],extended_route_proof=True,source_line_route_map=routes,skip_procurement_order_ids=[9481],dropship_dependency_file='dropship-65338-dependency.json',identity_proof_file='repair-plan.json',applied_utc=M['now']()))
    print(json.dumps(dict(verified_actions=len(j['actions']),completed_this_run=completed,overlay_published=(D/'applied-overlay.json').exists())),flush=True)

if __name__=='__main__':main()
