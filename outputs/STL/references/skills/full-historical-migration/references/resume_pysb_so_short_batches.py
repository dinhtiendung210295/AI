"""Confirm proven SOs using short, independently locked groups."""
import argparse
import json
import os
import runpy
import uuid
import hashlib
import time
from pathlib import Path
BASE=Path(__file__).parent
M=runpy.run_path(str(BASE/'confirm_pysb_prod_so.py'))
OUT=M['I']['OUT'];save=M['save'];load=M['load']

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--group-size',type=int,default=5);parser.add_argument('--max-orders',type=int,default=5000);args=parser.parse_args()
    if not 1<=args.group_size<=25:raise RuntimeError('Groups must contain 1..25 SO')
    # No OS lock during expensive read-only capture. Every group rechecks all
    # source/target headers and lines under its own short lock before writing.
    r=M['Run'](OUT);r.singleton=True;r.capture()
    rows=[x for x in r.rows if x['eligible'] and str(x['source_id']) not in r.j['orders']][:args.max_orders]
    flowhash=hashlib.sha256((BASE/'production_so_route_proof.py').read_bytes()+(BASE/'confirm_pysb_prod_so.py').read_bytes()).hexdigest()
    samplepath=OUT/'so-remediation/confirmation-flow-samples.json'
    samples=load(samplepath) if samplepath.exists() else dict(code_hash=flowhash,flows={})
    if samples['code_hash']!=flowhash:samples=dict(code_hash=flowhash,flows={})
    def flow(row):
        order=r.target[row['target_id']]
        routes=sorted({route for lid in order['order_line'] for route in r.tl[lid].get('route_ids',[])})
        return str(M['rid'](order['warehouse_id']))+':'+','.join(map(str,routes))
    print(json.dumps(dict(eligible_remaining=len(rows),short_group_size=args.group_size)),flush=True)
    completed=0
    while rows:
        acquire=runpy.run_path(str(BASE/'production_write_lock.py'))['acquire']
        try:lock=acquire(OUT)
        except RuntimeError:
            print(json.dumps(dict(stopped='Another session holds production lock',completed=completed,remaining=len(rows))),flush=True)
            return
        try:
            # Reject external journal changes rather than overwriting them.
            if load(r.jpath)!=r.j:raise RuntimeError('SO journal changed in another session; recapture required')
            r.log.events=r.log.replay()
            if r.log.unresolved():raise RuntimeError('Another session has an unresolved operation')
            rights=r.b.scan('studio.approval.rule',[['model_name','=','sale.order'],['method','=','action_confirm'],['active','=',True]],['can_validate','exclusive_user'])
            if not rights or any(not x['can_validate'] or x['exclusive_user'] for x in rights):raise RuntimeError('Approval rights changed')
            r.token=uuid.uuid4().hex
            save(OUT/'phases/phased-control-enabled.json',dict(identity=r.identity,supported_phases=['confirm-so'],status='Short SO group in progress'))
            save(OUT/'phases/active-phase.json',dict(identity=r.identity,phase='confirm-so',token=r.token,pid=os.getpid(),started_utc=M['now']()))
            newflow=next((x for x in rows if flow(x) not in samples['flows']),None)
            group=[newflow] if newflow else rows[:args.group_size]
            r.confirm(group)
            if newflow:
                if r.j['orders'][str(newflow['source_id'])]['status']!='verified_confirmed':raise RuntimeError('New warehouse/route sample did not pass')
                samples['flows'][flow(newflow)]=dict(source_id=newflow['source_id'],target_id=newflow['target_id'],passed=True,verified_utc=M['now']());save(samplepath,samples)
            selected={x['source_id'] for x in group};rows=[x for x in rows if x['source_id'] not in selected];completed+=len(group)
        finally:
            save(OUT/'phases/active-phase.json',dict(phase=None,pid=None,token=None,stopped_utc=M['now']()))
            save(OUT/'phases/phased-control-enabled.json',dict(identity=r.identity,supported_phases=[],status='Short SO group finished; lock released'))
            lock.close()
        print(json.dumps(dict(confirmed_this_run=completed,remaining=len(rows),production_lock_released=True)),flush=True)
        # Leave a window for another session to acquire the shared writer lock.
        if rows:time.sleep(0.5)
    save(OUT/'phases/confirm-so-short-batch-result.json',dict(identity=r.identity,completed=completed,completed_utc=M['now'](),production_lock_released=True))

if __name__=='__main__':main()
