"""Use already-approved active account policy for the isolated July supplement."""
from pathlib import Path
import json
import inspect_pysb_historical_invoices as inspection
inspection.OUT=Path(__file__).resolve().parents[6]/'outputs/pysb-invoice-july-supplement-20261014'
from create_pysb_historical_invoice_drafts import Run
from execute_pysb_stock_migration import require,index,rid,save
from collections import defaultdict
OUT=inspection.OUT
def main():
 m=Run();manifest=json.loads((OUT/'invoice-draft-manifest.json').read_text(encoding='utf8'));docs=[d for d in manifest['documents'] if str(d['source_id']) in m.j['documents']];accounts=index(m.b.read('account.account',sorted({l['values']['account_id'] for d in docs for l in d['lines'] if l['values'].get('account_id')}),['active','code','account_type']));proposals=[];blocked=[];fields=['quantity','price_unit','discount','price_subtotal','price_total','product_id','account_id','balance','amount_currency'];known={(116864,'income'):3849,(112916,'income'):3850,(118544,'income'):3850,(116972,'expense'):3851}
 for d in docs:
  ids={p['source_line']:p['target_line'] for p in m.j['documents'][str(d['source_id'])]['source_line_target_pairs']}
  for l in d['lines']:
   v=l['values'];old=accounts.get(v.get('account_id'))
   if not old or old['active']:continue
   pid=v.get('product_id');kind='income' if d['source']['move_type']=='out_invoice' else 'expense';product=m.b.call('product.product','read',[[pid]],{'fields':['categ_id','property_account_'+kind+'_id'],'context':{'allowed_company_ids':[1]}})[0] if pid else {};aid=rid(product.get('property_account_'+kind+'_id'))
   if not aid and product.get('categ_id'):aid=rid(m.b.call('product.category','read',[[rid(product['categ_id'])]],{'fields':['property_account_'+kind+'_categ_id'],'context':{'allowed_company_ids':[1]}})[0]['property_account_'+kind+'_categ_id'])
   if not aid:aid=known.get((pid,kind)) or rid(m.b.read('account.journal',[d['header']['journal_id']],['default_account_id'])[0]['default_account_id'])
   if not aid:blocked.append({'document':d['source_name'],'source_id':d['source_id'],'source_line':l['source_line_id'],'product':pid,'reason':'No configured or previously approved account'});continue
   proposals.append({'source_id':d['source_id'],'source_name':d['source_name'],'source_line':l['source_line_id'],'target_line':ids[l['source_line_id']],'old_account':v['account_id'],'new_account':aid})
 save(OUT/'supplement-posting-account-review.json',{'proposals':proposals,'blocked':blocked});require(not m.j.get('approved_supplement_account_remap'),'Already started; inspect before retry')
 for b in blocked:
  doc=next(d for d in manifest['documents'] if d['source_id']==b['source_id']);doc['errors'].append({'reason':'posting_account_unconfigured','product':b['product'],'source_line':b['source_line']})
 newaccounts=index(m.b.read('account.account',sorted({p['new_account'] for p in proposals}),['active','code']));require(all(a['active'] for a in newaccounts.values()),'Configured account inactive');before=index(m.b.read('account.move.line',[p['target_line'] for p in proposals],fields));groups=defaultdict(list)
 for p in proposals:require(rid(before[p['target_line']]['account_id'])==p['old_account'],'Account changed');groups[p['new_account']].append(p['target_line'])
 op={'status':'intent','approved_by':'Bruce','policy':'Previously approved: active account from v19 configuration; explicit machine account choices retained','proposals':proposals,'before':list(before.values())};m.j['approved_supplement_account_remap']=op;m.persist()
 for aid,ids in groups.items():m.mutate('account.move.line','write',[ids,{'account_id':aid}],{'context':{'allowed_company_ids':[1]}})
 after=index(m.b.read('account.move.line',[p['target_line'] for p in proposals],fields));byid={d['source_id']:d for d in manifest['documents']}
 for p in proposals:
  t=p['target_line'];require(rid(after[t]['account_id'])==p['new_account'] and all(after[t][k]==before[t][k] for k in fields if k!='account_id'),'Account-only remap mismatch');line=next(l for l in byid[p['source_id']]['lines'] if l['source_line_id']==p['source_line']);line['values']['account_id']=p['new_account'];line['approved_account_mapping']=p
 save(OUT/'invoice-draft-manifest.json',manifest);op.update(status='verified',after=list(after.values()),blocked=blocked);m.persist();print(json.dumps({'account_lines_remapped':len(proposals),'documents':len({p['source_id'] for p in proposals}),'blocked':blocked,'master_changes':False}))
if __name__=='__main__':main()
