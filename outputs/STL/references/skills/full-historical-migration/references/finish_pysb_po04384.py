"""Finish only PO-04384 after Bruce approves its two MIMAKI supplier links."""
import os
from pathlib import Path
import runpy
import subprocess
import sys
import uuid
from datetime import datetime, timezone

BASE=Path(__file__).parent
P=runpy.run_path(str(BASE/'confirm_pysb_prod_orders.py'))
C=runpy.run_path(str(BASE/'run_pysb_phased_migration.py'))
S=runpy.run_path(str(BASE/'confirm_pysb_approved_supplier_pos.py'))
OUT=P['I']['OUT']

def main():
    phase=OUT/'phases';lock=runpy.run_path(str(BASE/'production_write_lock.py'))['acquire'](OUT);old=None;active=False
    try:
        identity,readiness=C['validate_context'](OUT)
        tests=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(BASE/'tests'),'-q'],capture_output=True,text=True)
        P['save'](phase/'po04384-offline-tests.json',dict(returncode=tests.returncode,output=tests.stdout+tests.stderr))
        if tests.returncode:raise RuntimeError('Offline tests failed')
        base=P['ConfirmPO'](OUT,identity,readiness)
        row=next(r for r in readiness['models']['purchase.order']['rows'] if r['source_id']==5114)
        if row['target_id']!=1066 or row['source_name']!='PO-04384':raise RuntimeError('PO identity changed')
        previous=base.j['orders']['purchase.order:5114']
        if previous['status']=='verified_confirmed':
            print('PO-04384 already verified; no repeated confirmation');return
        if previous['status']!='held_workflow' or not base.never_attempted(5114):raise RuntimeError('Prior mutation requires readback')
        pre=base.preflight(row)
        required={4053,4054}
        products=set()
        for lid in required:
            line=next(x for x in pre['target_lines'] if x['id']==lid)
            source_line=next(s for s,t in base.maps['purchase.order.line'].items() if t==lid)
            if source_line not in (19147,19148):raise RuntimeError('Approved line mapping changed')
            products.add(P['rid'](line['product_id']))
        expected={'confirmation_may_create_supplier_master:4053','confirmation_may_create_supplier_master:4054'}
        if set(pre['issues'])-expected:raise RuntimeError('Other PO issues require review')
        partner=base.b.read('res.partner',[P['rid'](pre['target']['partner_id'])],['name','parent_id'])[0]
        if partner['name']!='MIMAKI SINGAPORE PTE LTD':raise RuntimeError('Approved vendor changed')
        vendors=sorted({partner['id'],P['rid'](partner['parent_id'])}-{False})
        approval=dict(approved=True,approved_by='Bruce',authority='User continuation after the explicit pending approval question for these two MIMAKI links',recorded_utc=datetime.now(timezone.utc).isoformat(),scope_identity=identity,orders=[dict(source_id=5114,target_id=1066,target_product_ids=sorted(products),target_line_ids=sorted(required),vendor_ids=vendors)])
        P['save'](phase/'po04384-supplier-approval.json',approval)
        runner=S['ApprovedPO'](OUT,identity,readiness,approval)
        approved=runner.preflight(row)
        if approved['issues']:raise RuntimeError('PO still blocked')
        token=uuid.uuid4().hex;runner.session_token=token;old=P['load'](phase/'phased-control-enabled.json')
        P['save'](phase/'phased-control-enabled.json',dict(identity=identity,supported_phases=['confirm-po']))
        P['save'](phase/'active-phase.json',dict(identity=identity,phase='confirm-po',pid=os.getpid(),token=token));active=True
        history=phase/'history';history.mkdir(exist_ok=True)
        P['save'](history/'po04384-before-approved-reopen.json',runner.j['orders']['purchase.order:5114'])
        runner.j['orders']['purchase.order:5114']=dict(source_id=5114,target_id=1066,status='reopened_workflow_preflight',prior_workflow_hold=previous,supplier_approval=P['digest'](approval));runner.persist()
        result=runner.confirm(row,approved)
        P['save'](phase/'po04384-completion.json',result)
        print(__import__('json').dumps(dict(source_id=5114,target_id=1066,confirmed=True,new_supplier_ids=result['approved_supplier_changes']['created_supplier_ids'],new_contacts=0,new_invoices=0,warehouse_done_by_this_phase=0)),flush=True)
    finally:
        if active:P['save'](phase/'active-phase.json',dict(identity=identity,phase=None,pid=None,token=None,stopped_utc=datetime.now(timezone.utc).isoformat()))
        if old is not None:P['save'](phase/'phased-control-enabled.json',old)
        lock.close()

if __name__=='__main__':main()
