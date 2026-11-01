"""Sequential production queue; invokes guarded canonical writers without retries.

Only existing frozen-scope preflights authorize selection. Any failed command,
uncertain mutation, incomplete group or absence of verified progress stops.
"""
import json
import subprocess
import sys
import runpy
from pathlib import Path
BASE=Path(__file__).parent
I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'))
OUT=I['OUT']
def load(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def run(name,*args):
    result=subprocess.run([sys.executable,str(BASE/name),*args])
    if result.returncode:raise SystemExit(result.returncode)
def totals():
    specs=[('independent-inventory-journal.json','groups','status','verified_done'),('independent-mo-journal.json','mos','status','verified_done'),('independent-delivery-journal.json','groups','phase','completed'),('independent-invoice-journal.json','documents','status','verified_posted')]
    result={}
    receipts=load('independent-receipts-journal.json')
    if any(x['status'] in ['intent','uncertain'] for x in receipts.get('operations',[])):raise RuntimeError('Uncertain receipt operation')
    for name,key,field,done in specs:
        journal=load(name)
        if any(x['status'] in ['intent','uncertain'] for x in journal.get('operations',[])):raise RuntimeError('Uncertain operation in '+name)
        for row in journal[key].values():
            if row.get(field)!=done and not row.get('execution_hold'):raise RuntimeError('Incomplete group in '+name)
        result[key+':'+name]=sum(x.get(field)==done for x in journal[key].values())
        result['execution_holds:'+name]=sum(bool(x.get('execution_hold')) and x.get(field)!=done for x in journal[key].values())
    return result
def refresh():run('check_pysb_aug_oct_coverage.py','--after-run')
def main():
    if (OUT/'phases/phased-control-enabled.json').exists():raise RuntimeError('Mixed queue disabled by phased migration controller')
    totals()
    for cycle in range(2000):
        before=totals();refresh()
        run('prepare_pysb_inventory_adjustments.py')
        plan=load('independent-inventory-adjustment-plan.json');journal=load('independent-inventory-journal.json')
        pending_inventory=[x for x in plan['groups'] if x['eligible'] and x['group_key'] not in journal['groups']]
        if pending_inventory:
            run('migrate_pysb_inventory_adjustments.py','--mode','batch','--limit','30');refresh()
        run('prepare_pysb_independent_mos.py')
        plan=load('independent-mo-supply-plan.json');journal=load('independent-mo-journal.json')
        pending_mos=[x for x in plan['rows'] if x['eligible'] and journal['mos'].get(str(x['source_mo']),{}).get('status')!='verified_done']
        if pending_mos:
            run('run_pysb_independent_mo_queue.py');refresh()
        run('prepare_pysb_independent_deliveries.py')
        plan=load('independent-delivery-plan.json');journal=load('independent-delivery-journal.json')
        pending_deliveries=[x for x in plan['rows'] if x['eligible'] and not journal['groups'].get(str(x['source_so']),{}).get('execution_hold') and journal['groups'].get(str(x['source_so']),{}).get('phase')!='completed']
        if pending_deliveries:
            run('migrate_pysb_independent_deliveries.py','--mode','batch','--limit','10');refresh()
        run('prepare_pysb_independent_invoices.py')
        manifest=load('independent-invoice-manifest.json');journal=load('independent-invoice-journal.json')
        pending_invoices=[x for x in manifest['documents'] if not x['errors'] and not x['target_existing'] and journal['documents'].get(str(x['source_id']),{}).get('status')!='verified_posted']
        if pending_invoices:run('migrate_pysb_independent_invoices.py','--mode','batch','--limit','100')
        after=totals();run('render_pysb_aug_oct_execution_report.py')
        print(json.dumps({'cycle':cycle,'completion_and_hold_counts':after}),flush=True)
        if before==after:
            if any([pending_inventory,pending_mos,pending_deliveries,pending_invoices]):raise RuntimeError('No verified progress; stop without retry')
            print(json.dumps({'independent_queue_complete':True,'remaining_groups_require_review':True}),flush=True);return
    raise RuntimeError('Queue iteration limit reached')
if __name__=='__main__':main()
