"""Confirm only eight repaired drafts explicitly delegated by Bruce."""
import argparse
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import runpy
import subprocess
import sys
import uuid

BASE=Path(__file__).parent
P=runpy.run_path(str(BASE/'confirm_pysb_prod_orders.py'))
C=runpy.run_path(str(BASE/'run_pysb_phased_migration.py'))
S=runpy.run_path(str(BASE/'confirm_pysb_approved_supplier_pos.py'))

def main(directory,mode):
    out=Path(directory).resolve();phase=out/'phases';lock=runpy.run_path(str(BASE/'production_write_lock.py'))['acquire'](out);old=None;active=False
    try:
        identity,readiness=C['validate_context'](out);authorization=P['load'](phase/'authorized-po-gaps-approval.json')
        if not authorization['approved'] or authorization['identity']!=identity or len(authorization['draft_source_ids'])!=8:raise RuntimeError('Eight draft repair authorization missing')
        code=P['digest']({n:hashlib.sha256((BASE/n).read_bytes()).hexdigest() for n in ('confirm_pysb_repaired_draft_pos.py','confirm_pysb_prod_orders.py','confirm_pysb_approved_supplier_pos.py')})
        if mode=='batch':
            sample=P['load'](phase/'repaired-draft-po-sample.json')
            if not sample['passed'] or sample['code_hash']!=code:raise RuntimeError('Repaired draft sample required')
        tests=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(BASE/'tests'),'-q'],capture_output=True,text=True)
        P['save'](phase/'repaired-draft-po-tests.json',dict(returncode=tests.returncode,output=tests.stdout+tests.stderr))
        if tests.returncode:raise RuntimeError('Offline tests failed')
        base=P['ConfirmPO'](out,identity,readiness)
        selected=[];approved_rows=[]
        for sid in authorization['draft_source_ids']:
            row=next(r for r in readiness['models']['purchase.order']['rows'] if r['source_id']==sid)
            previous=base.j['orders'].get('purchase.order:'+str(sid))
            if previous and previous['status']=='verified_confirmed':continue
            if previous:raise RuntimeError('Existing draft intent requires readback')
            if not row['commercially_matched'] or row['target_state'] not in ('draft','sent'):raise RuntimeError('Repaired draft commercial comparison not passed')
            pre=base.preflight(row)
            other=[x for x in pre['issues'] if not x.startswith('confirmation_may_create_supplier_master:')]
            if other:raise RuntimeError('Repaired draft has unresolved workflow '+str(other))
            parent=base.b.read('res.partner',[P['rid'](pre['target']['partner_id'])],['parent_id'])[0]
            approved_rows.append(dict(source_id=sid,target_id=row['target_id'],target_product_ids=sorted({P['rid'](l['product_id']) for l in pre['target_lines'] if l.get('product_id')}),target_line_ids=[l['id'] for l in pre['target_lines']],vendor_ids=sorted({P['rid'](pre['target']['partner_id']),P['rid'](parent['parent_id'])}-{False})))
            selected.append(row)
            if mode=='sample':break
        approval=dict(approved=True,approved_by='Bruce',scope_identity=identity,authority='Explicit user delegation to repair and complete eight draft PO; supplier additions limited to native confirmation of these exact lines',orders=approved_rows)
        P['save'](phase/('repaired-draft-supplier-scope-'+mode+'.json'),approval)
        runner=S['ApprovedPO'](out,identity,readiness,approval)
        token=uuid.uuid4().hex;runner.session_token=token
        old=P['load'](phase/'phased-control-enabled.json')
        P['save'](phase/'phased-control-enabled.json',dict(identity=identity,supported_phases=['confirm-po'],code_hash=code))
        P['save'](phase/'active-phase.json',dict(identity=identity,phase='confirm-po',pid=os.getpid(),token=token));active=True
        results=[]
        for row in selected:
            pre=runner.preflight(row);result=runner.confirm(row,pre);results.append(result)
            print(__import__('json').dumps(dict(source_id=row['source_id'],target_id=row['target_id'],confirmed=True,new_supplier_ids=result['approved_supplier_changes']['created_supplier_ids'],new_invoices=0,warehouse_done_by_this_phase=0)),flush=True)
        P['save'](phase/('repaired-draft-po-'+mode+'.json'),dict(passed=bool(results),code_hash=code,completed=results,completed_utc=datetime.now(timezone.utc).isoformat()))
    finally:
        if active:P['save'](phase/'active-phase.json',dict(identity=identity,phase=None,pid=None,token=None,stopped_utc=datetime.now(timezone.utc).isoformat()))
        if old is not None:P['save'](phase/'phased-control-enabled.json',old)
        lock.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--evidence-dir',required=True);p.add_argument('--mode',choices=['sample','batch'],required=True);args=p.parse_args();main(args.evidence_dir,args.mode)
