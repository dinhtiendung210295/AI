"""Drive existing sampled MO batches; any failure stops without retrying it."""
import json
import subprocess
import sys
from pathlib import Path
import runpy

BASE=Path(__file__).parent
I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'))
OUT=I['OUT']


def completed():
    journal=json.loads((OUT/'independent-mo-journal.json').read_text(encoding='utf8'))
    if any(x['status'] not in ['returned','verified_rejected_by_readback'] for x in journal['operations']):
        raise RuntimeError('Uncertain MO operation; queue cannot resume it')
    if any(x['status']!='verified_done' and not (x['status']=='expiry_held' and x.get('execution_hold')) for x in journal['mos'].values()):
        raise RuntimeError('Incomplete MO needs explicit read-back recovery')
    return {int(k) for k,v in journal['mos'].items() if v['status']=='verified_done'}


def main():
    for _ in range(1324):
        before=completed()
        plan=json.loads((OUT/'independent-mo-supply-plan.json').read_text(encoding='utf8'))
        journal=json.loads((OUT/'independent-mo-journal.json').read_text(encoding='utf8'))
        held={int(k) for k,v in journal['mos'].items() if v.get('execution_hold')}
        if held & {x['source_mo'] for x in plan['rows'] if x['eligible']}:raise RuntimeError('Held MO still proposed as supply; replan before queue')
        pending={x['source_mo'] for x in plan['rows'] if x['eligible']}-before
        if not pending:
            print(json.dumps({'queue_complete':True,'verified_mos':len(before)}),flush=True)
            return
        result=subprocess.run([sys.executable,str(BASE/'migrate_pysb_independent_mos.py'),'--mode','batch','--limit','1000'])
        if result.returncode:
            raise SystemExit(result.returncode)
        after=completed()
        if not before<after:
            raise RuntimeError('Batch returned without verified progress; stop without retry')
    raise RuntimeError('Queue iteration bound exceeded')


if __name__=='__main__':main()
