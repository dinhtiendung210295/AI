"""Read-only native opening balances for mapped products, not full-company acceptance."""
import json
import runpy
import socket
from pathlib import Path

I=runpy.run_path(str(Path(__file__).with_name('inspect_pysb_aug_oct_prod.py')))
OUT,save,ReadOnly=I['OUT'],I['save'],I['ReadOnly']
def load(n):return json.loads((OUT/n).read_text(encoding='utf8'))

def main():
    socket.setdefaulttimeout(120)
    scope=load('scope.json');all_maps=load('resolved-master-evidence.json')['maps']
    all_maps=runpy.run_path(str(Path(__file__).with_name('stock_confirmation_handoff.py')))['apply'](all_maps,OUT);maps=all_maps['product.product']
    products=load('source-products.json')
    source_ids=[p['id'] for p in products if str(p['id']) in maps]
    target_ids=sorted({maps[str(i)] for i in source_ids})
    result={}
    for label,env,identity,ids in [('source','v14-prod',('http://175.145.85.151','paoyeang_live'),source_ids),('target','v19-prod',('https://py19.odoo.com','py19-main-33843450'),target_ids)]:
        r=ReadOnly(env,identity);rows=[]
        for offset in range(0,len(ids),200):
            rows.extend(r.call('product.product','read',[ids[offset:offset+200]],{'fields':['name','uom_id','qty_available'],'context':{'to_date':'2026-07-31 15:59:59','tz':'UTC'}}))
        if {x['id'] for x in rows}!=set(ids):raise RuntimeError('Incomplete opening read')
        result[label]={x['id']:x for x in rows}
        save(label+'-native-opening.json',rows)
        print(label,'opening',len(rows),flush=True)
    rows=[]
    for sid in source_ids:
        s=result['source'][sid];t=result['target'][maps[str(sid)]]
        rows.append({'source_id':sid,'target_id':t['id'],'name':s['name'],'source_unit':s['uom_id'],'target_unit':t['uom_id'],
                     'source_quantity':s['qty_available'],'target_quantity':t['qty_available'],
                     'delta':t['qty_available']-s['qty_available'],'exact_quantity_match':abs(t['qty_available']-s['qty_available'])<=1e-6})
    report={'scope':scope,'as_of_utc_inclusive':'2026-07-31 15:59:59','comparison':'native product qty_available; mapped scope only; unit identity and detailed location/lot/package/owner still require checks',
            'full_company_acceptance':False,'rows':rows,'summary':{'products':len(rows),'quantity_matched':sum(x['exact_quantity_match'] for x in rows),'quantity_mismatched':sum(not x['exact_quantity_match'] for x in rows)}}
    save('native-opening-comparison.json',report)
    print(json.dumps(report['summary']),flush=True)

if __name__=='__main__':main()
