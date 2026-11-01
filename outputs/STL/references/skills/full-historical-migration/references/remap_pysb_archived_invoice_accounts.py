"""Operator-approved transaction-line remap; no account/product master changes."""
from create_pysb_historical_invoice_drafts import Run
from inspect_pysb_historical_invoices import OUT
from execute_pysb_stock_migration import save,require,index,rid
from collections import defaultdict
import json
def main():
 m=Run();review=json.loads((OUT/'archived-account-review.json').read_text(encoding='utf8'));manifest=json.loads((OUT/'invoice-draft-manifest.json').read_text(encoding='utf8'));docs=index([{'id':d['source_id'],**d} for d in manifest['documents']]);allproposals=review['proposals'];require(len(allproposals)==315,'Unexpected remap scope');proposals=[p for p in allproposals if p['configured_account']];deferred=[p for p in allproposals if not p['configured_account']]
 accounts=index(m.b.read('account.account',sorted({p['configured_account'] for p in proposals}),['active','code','name','account_type']));require(all(a['active'] for a in accounts.values()),'Configured account archived');moves=m.b.read('account.move',sorted({p['target_id'] for p in proposals}),['state','company_id','amount_total']);require(all(x['state']=='draft' and rid(x['company_id'])==1 for x in moves),'Remap only draft company-1 documents')
 mapping={sid:{p['source_line']:p['target_line'] for p in rec['source_line_target_pairs']} for sid,rec in m.j['documents'].items()};lineids=[mapping[str(p['source_id'])][p['source_line']] for p in proposals];current=index(m.b.read('account.move.line',lineids,['account_id','quantity','price_unit','discount','price_subtotal','price_total','product_id','product_uom_id','sale_line_ids','purchase_line_id','balance','amount_currency']));previous=m.j.get('approved_posting_account_remap');before=index(previous['before_lines']) if previous else current;groups=defaultdict(list)
 for p in proposals:
  lid=mapping[str(p['source_id'])][p['source_line']];require(rid(current[lid]['account_id']) in [p['archived_account']['id'],p['configured_account']],'Draft account changed')
  if rid(current[lid]['account_id'])!=p['configured_account']:groups[p['configured_account']].append(lid)
 backup=OUT/'invoice-draft-manifest-before-account-remap.json'
 if not backup.exists():save(backup,manifest)
 operation=previous or {'status':'intent','approved_by':'Bruce','approval':'Dùng tài khoản đang cấu hình trên v19','source_documents':129,'line_count':315,'before_lines':list(before.values())};operation.update(accounts=list(accounts.values()),proposals=allproposals,deferred=deferred);m.j['approved_posting_account_remap']=operation;m.persist()
 for aid,ids in groups.items():m.mutate('account.move.line','write',[ids,{'account_id':aid}],{'context':{'allowed_company_ids':[1]}})
 after=index(m.b.read('account.move.line',lineids,list(next(iter(before.values())).keys())));
 for p in proposals:
  lid=mapping[str(p['source_id'])][p['source_line']];require(rid(after[lid]['account_id'])==p['configured_account'],'Account remap mismatch');require(all(after[lid][k]==before[lid][k] for k in before[lid] if k!='account_id'),'Commercial values changed by remap');d=docs[p['source_id']];line=next(x for x in d['lines'] if x['source_line_id']==p['source_line']);line['values']['account_id']=p['configured_account'];line['approved_account_mapping']={'original_target_account':p['archived_account'],'configured_target_account':accounts[p['configured_account']],'approved_by':'Bruce'}
 save(OUT/'invoice-draft-manifest.json',manifest);operation.update(status='verified_with_unconfigured_exceptions' if deferred else 'verified',after_lines=list(after.values()));m.persist();print(json.dumps({'remapped_documents':len({p['source_id'] for p in proposals}),'remapped_lines':len(proposals),'deferred_lines':len(deferred),'masters_changed':False}))
if __name__=='__main__':main()
