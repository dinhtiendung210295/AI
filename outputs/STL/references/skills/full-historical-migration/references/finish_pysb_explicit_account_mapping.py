"""Apply Bruce's explicit machine-account choices to the 13 remaining draft lines."""
from create_pysb_historical_invoice_drafts import Run
from inspect_pysb_historical_invoices import OUT
from execute_pysb_stock_migration import require,index,rid,save
from collections import defaultdict
import json
def main():
 m=Run();review=json.loads((OUT/'archived-account-review.json').read_text(encoding='utf8'));manifest=json.loads((OUT/'invoice-draft-manifest.json').read_text(encoding='utf8'));docs={d['source_id']:d for d in manifest['documents']};ps=[p for p in review['proposals'] if not p['configured_account']];require(len(ps)==13,'Unexpected explicit scope');choices={116864:3849,112916:3850,118544:3850,116972:3851};codes={3849:'5060.00000',3850:'5070.00000',3851:'6060.00000'};accounts=index(m.b.read('account.account',list(codes),['code','active']));require(all(accounts[i]['active'] and accounts[i]['code']==code for i,code in codes.items()),'Approved account changed');states=m.b.read('account.move',[p['target_id'] for p in ps],['state','company_id']);require(all(x['state']=='draft' and rid(x['company_id'])==1 for x in states),'Only draft company 1 allowed');require(not m.j.get('explicit_machine_account_mapping'),'Already started: read-back before retry');groups=defaultdict(list);pairs=[]
 for p in ps:
  aid=choices[p['product']['id']];rec=m.j['documents'][str(p['source_id'])];lid=next(x['target_line'] for x in rec['source_line_target_pairs'] if x['source_line']==p['source_line']);groups[aid].append(lid);pairs.append({'proposal':p,'target_line':lid,'account':aid})
 fields=['account_id','product_id','quantity','price_unit','discount','price_subtotal','price_total','sale_line_ids','purchase_line_id','balance','amount_currency'];before=index(m.b.read('account.move.line',[x['target_line'] for x in pairs],fields));require(all(rid(before[x['target_line']]['account_id'])==x['proposal']['archived_account']['id'] for x in pairs),'Original account changed');op={'status':'intent','approved_by':'Bruce','choices':codes,'before':list(before.values()),'pairs':pairs};m.j['explicit_machine_account_mapping']=op;m.persist()
 for aid,ids in groups.items():m.mutate('account.move.line','write',[ids,{'account_id':aid}],{'context':{'allowed_company_ids':[1]}})
 after=index(m.b.read('account.move.line',[x['target_line'] for x in pairs],fields))
 for x in pairs:
  lid=x['target_line'];require(rid(after[lid]['account_id'])==x['account'] and all(after[lid][k]==before[lid][k] for k in fields if k!='account_id'),'Read-back mismatch');p=x['proposal'];line=next(y for y in docs[p['source_id']]['lines'] if y['source_line_id']==p['source_line']);line['values']['account_id']=x['account'];line['approved_account_mapping']={'approved_by':'Bruce','reason':'Explicit account choice because product/journal configuration is absent','target_account_code':codes[x['account']]}
 save(OUT/'invoice-draft-manifest.json',manifest);op.update(status='verified',after=list(after.values()));m.j['approved_posting_account_remap'].update(status='verified',deferred=[],explicit_choices=op['choices']);m.persist();print(json.dumps({'explicit_mappings':13,'masters_changed':False}))
if __name__=='__main__':main()
