"""Read-only natural identity resolution for opening lots, retaining conflicts."""
import json
import runpy
from collections import defaultdict
from pathlib import Path
I=runpy.run_path(str(Path(__file__).with_name('inspect_pysb_aug_oct_prod.py')))
def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False
def load(n):return json.loads((I['OUT']/n).read_text(encoding='utf8'))

def main():
    opening=load('source-detailed-opening-reconstruction.json')['rows']
    maps=load('discovery-manifest.json')['maps'];pm=maps['product.product']
    a=I['ReadOnly']('v14-prod',('http://175.145.85.151','paoyeang_live'))
    b=I['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    source=a.read('stock.production.lot',sorted({x['key'][2] for x in opening if x['key'][2]}),['name','product_id','company_id'])
    target=b.scan('stock.lot',[['company_id','=',1],['product_id','in',sorted({pm[str(rid(x['product_id']))] for x in source})]],['name','product_id','company_id'])
    bykey=defaultdict(list)
    for x in target:bykey[(rid(x['company_id']),rid(x['product_id']),x['name'])].append(x['id'])
    resolved={};issues=[]
    for x in source:
        candidates=bykey[(1,pm[str(rid(x['product_id']))],x['name'])]
        old=maps.get('stock.lot',{}).get(str(x['id']))
        if len(candidates)==1 and (not old or old==candidates[0]):resolved[str(x['id'])]=candidates[0]
        else:issues.append({'source_lot':x,'candidates':candidates,'existing_mapping':old})
    I['save']('opening-lot-resolution.json',{'maps':{'stock.lot':resolved},'issues':issues,'source_lots':source,'target_lots':target,'identity':'company + mapped product + exact lot name, unique candidate; no Odoo writes'})
    print(json.dumps({'source_lots':len(source),'resolved':len(resolved),'held':len(issues)}),flush=True)

if __name__=='__main__':main()
