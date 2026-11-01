"""Read-only MO lot expiry evidence and audit of lots created by this run."""
import json
import runpy
from pathlib import Path
I=runpy.run_path(str(Path(__file__).with_name('inspect_pysb_aug_oct_prod.py')))
def load(n):return json.loads((I['OUT']/n).read_text(encoding='utf8'))
def rid(x):return x[0] if isinstance(x,(tuple,list)) and x else x or False

def main():
    mos=load('source-mos.json');mids={i for x in mos for f in ['move_raw_ids','move_finished_ids'] for i in x[f]}
    ids={rid(x['lot_id']) for x in load('source-move-lines.json') if rid(x['move_id']) in mids and x['lot_id']}
    a=I['ReadOnly']('v14-prod',('http://175.145.85.151','paoyeang_live'));b=I['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    fields='name product_id company_id expiration_date use_date removal_date alert_date write_date'.split()
    source=a.read('stock.production.lot',ids,fields);byid={x['id']:x for x in source};end=load('scope.json')['end_utc_exclusive']
    journal=load('independent-mo-journal.json');created={x['result'] for x in journal['operations'] if x['model']=='stock.lot' and x['method']=='create' and x['status']=='returned'}
    target=b.read('stock.lot',created,fields);inverse={tid:int(sid) for sid,tid in journal['maps'].get('stock.lot',{}).items() if tid in created};differences=[]
    for t in target:
        s=byid[inverse[t['id']]]
        for f in ['expiration_date','use_date','removal_date','alert_date']:
            if s.get(f) and t.get(f)!=s[f]:differences.append({'source_lot':s['id'],'target_lot':t['id'],'field':f,'source':s[f],'target':t.get(f)})
    result={'rows':source,'changed_since_snapshot':[x['id'] for x in source if x['write_date']>=end],'own_created_lot_differences':differences,'policy':'Copy populated historical expiry dates on new lots; preserve product masters; report old-lot differences separately'}
    I['save']('source-mo-lot-metadata.json',result);print(json.dumps({'lots':len(source),'source_with_expiry':sum(bool(x.get('expiration_date')) for x in source),'changed_since_snapshot':len(result['changed_since_snapshot']),'own_created_differences':len(differences)}),flush=True)

if __name__=='__main__':main()
