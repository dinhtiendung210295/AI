"""Sequential stock-only continuation, fresh coverage between groups; fail on error."""
import json,subprocess,sys,runpy
from pathlib import Path
BASE=Path(__file__).parent
I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'));OUT=I['OUT']
def load(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def run(n,*args):
    result=subprocess.run([sys.executable,str(BASE/n),*args])
    if result.returncode:raise RuntimeError('Stopped without retry: '+n+' exit '+str(result.returncode))
def totals():
    result={}
    for name,key,field,done in [('independent-receipts-journal.json','groups','phase','completed'),('independent-delivery-journal.json','groups','phase','completed'),('independent-mo-journal.json','mos','status','verified_done'),('independent-inventory-journal.json','groups','status','verified_done')]:
        j=load(name)
        if any(x['status'] in ['intent','uncertain'] for x in j['operations']):raise RuntimeError('Uncertain operation in '+name)
        if any(x.get(field)!=done and not x.get('execution_hold') for x in j[key].values()):raise RuntimeError('Interrupted group in '+name)
        result[name]=sum(x.get(field)==done for x in j[key].values())
    return result
def main():
    month_order=OUT/'phases/operator-month-first-stock-order.json'
    if month_order.exists() and not load('phases/operator-month-first-stock-order.json').get('auto_advance_with_unresolved',False):
        raise RuntimeError('Month-first control: legacy eligible-only queue disabled. Complete and reconcile every warehouse category in the earliest unresolved month before later months.')
    start=totals();run('check_pysb_aug_oct_coverage.py','--after-run')
    groups_since_full=0
    def refresh(force=False):
        nonlocal groups_since_full
        groups_since_full+=1
        if force or groups_since_full>=5:
            run('check_pysb_aug_oct_coverage.py','--after-run');groups_since_full=0
        else:run('check_pysb_aug_oct_coverage.py','--after-run','--incremental')
    receipt_preflight_needed=True
    for cycle in range(2000):
        before=totals();progress=False
        if receipt_preflight_needed or groups_since_full==0:run('migrate_pysb_independent_receipts.py','--mode','preflight')
        receipt_preflight_needed=False
        plan=load('independent-receipts-manifest.json');j=load('independent-receipts-journal.json')
        receipt_pending=[x for x in plan['groups'] if not x['issues'] and x['target']['state']=='purchase' and not j['groups'].get(str(x['source']['id']),{}).get('execution_hold') and j['groups'].get(str(x['source']['id']),{}).get('phase')!='completed']
        if receipt_pending:
            run('resume_pysb_stock_phase.py','--kind','receipt','--mode','batch','--limit','10');refresh();receipt_preflight_needed=True
            # Exhaust the admitted supply queue before consuming stock again.
            print(json.dumps(dict(receipt_priority=True,current=totals())),flush=True)
            continue
        I['save']('phases/stock-receipts-priority.json',dict(handoff_requested=False,eligible_receipts_exhausted=True))
        run('prepare_pysb_inventory_adjustments.py')
        plan=load('independent-inventory-adjustment-plan.json');j=load('independent-inventory-journal.json')
        if any(x['eligible'] and x['group_key'] not in j['groups'] for x in plan['groups']):
            run('resume_pysb_stock_phase.py','--kind','inventory','--mode','batch','--limit','10');refresh();progress=True
        run('prepare_pysb_independent_mos.py')
        plan=load('independent-mo-supply-plan.json');j=load('independent-mo-journal.json')
        if any(x['eligible'] and not j['mos'].get(str(x['source_mo']),{}).get('execution_hold') and j['mos'].get(str(x['source_mo']),{}).get('status')!='verified_done' for x in plan['rows']):
            run('resume_pysb_stock_phase.py','--kind','mo','--mode','batch','--limit','10');refresh();progress=True
        run('prepare_pysb_independent_deliveries.py')
        plan=load('independent-delivery-plan.json');j=load('independent-delivery-journal.json')
        if any(x['eligible'] and not j['groups'].get(str(x['source_so']),{}).get('execution_hold') and j['groups'].get(str(x['source_so']),{}).get('phase')!='completed' for x in plan['rows']):
            run('resume_pysb_stock_phase.py','--kind','delivery','--mode','batch','--monthly');refresh();progress=True
        after=totals();result=dict(cycle=cycle,baseline=start,current=after)
        I['save']('phases/stock-queue-progress.json',result);print(json.dumps(result),flush=True)
        if not progress:
            refresh(force=True)
            I['save']('phases/stock-queue-result.json',dict(**result,eligible_queue_exhausted=True,full_acceptance=False));return
        if after==before:raise RuntimeError('No verified progress; inspect without retry')
    raise RuntimeError('Iteration limit reached')
if __name__=='__main__':main()
