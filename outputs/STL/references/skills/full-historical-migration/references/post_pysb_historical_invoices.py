"""Post only proven migrated Invoice/Bill ids; no payments or reconciliation."""
from create_pysb_historical_invoice_drafts import Run
from inspect_pysb_historical_invoices import OUT
from execute_pysb_stock_migration import require,save,rid,index
from collections import Counter
import json,sys
from historical_invoice_checks import require_manifest,validation_errors,extra_read_fields
def main():
 m=Run();manifest=json.loads((OUT/'invoice-draft-manifest.json').read_text(encoding='utf8'));docs=manifest['documents'];require(len(docs)==1057 and all(not d['errors'] for d in docs),'Unexpected scope')
 if '--invoices-only' in sys.argv:docs=[d for d in docs if d['source']['move_type']=='out_invoice']
 if '--eligible-only' in sys.argv:
  review=json.loads((OUT/'archived-account-review.json').read_text(encoding='utf8'));blocked={p['source_id'] for p in review['proposals']};docs=[d for d in docs if d['source_id'] not in blocked]
 if '--configured-only' in sys.argv:
  review=json.loads((OUT/'archived-account-review.json').read_text(encoding='utf8'));blocked={p['source_id'] for p in review['proposals'] if not p['configured_account']};docs=[d for d in docs if d['source_id'] not in blocked]
 require_manifest(docs)
 records=m.j['documents'];ids=[records[str(d['source_id'])]['target_id'] for d in docs];require(len(set(ids))==len(docs),'Duplicate target')
 fields=['name','state','move_type','company_id','partner_id','currency_id','journal_id','date','invoice_date','invoice_date_due','invoice_payment_term_id','invoice_origin','ref','x_studio_v14_refererce','invoice_line_ids','line_ids','amount_untaxed','amount_tax','amount_total']+extra_read_fields(docs);linefields=['name','sequence','display_type','product_id','product_uom_id','quantity','price_unit','discount','tax_ids','account_id','sale_line_ids','purchase_line_id','price_subtotal','price_total','base_price','packing_ratio','balance','amount_currency']
 def verify(batch,states):
  moves=index(m.b.read('account.move',[records[str(d['source_id'])]['target_id'] for d in batch],fields));lines=index(m.b.read('account.move.line',[i for v in moves.values() for i in v['line_ids']],linefields));errors=[]
  for d in batch:
   v=moves[records[str(d['source_id'])]['target_id']];require(v['state'] in states,'Unexpected target state '+d['source_name'])
   errors.extend({'source':d['source_name'],**e} for e in validation_errors(d,v,lines))
   for k,want in d['header'].items():
    if k in ['invoice_currency_rate','x_foreign_to_company_rate','invoice_user_id']:continue
    if k not in v:continue
    have=rid(v[k]) if k.endswith('_id') else v[k]
    if have!=want:errors.append({'source':d['source_name'],'field':k,'expected':want,'actual':have})
   for k in ['amount_untaxed','amount_tax','amount_total']:
    if abs(v[k]-d['source'][k])>0.00501:errors.append({'source':d['source_name'],'field':k,'expected':d['source'][k],'actual':v[k]})
   require(len(v['invoice_line_ids'])==len(d['lines']),'Invoice line count changed')
   for expected,lid in zip(d['lines'],v['invoice_line_ids']):
    actual=lines[lid]
    for k,want in expected['values'].items():
     if k not in actual:continue
     have=actual[k]
     if k.endswith('_id'):have=rid(have)
     if k in ['tax_ids','sale_line_ids']:have=sorted(have);want=sorted(want[0][2])
     differs=abs(have-want)>1e-6 if isinstance(want,(int,float)) and not isinstance(want,bool) else have!=want
     if differs:errors.append({'source':d['source_name'],'line':lid,'field':k,'expected':want,'actual':have})
   if abs(sum(lines[i]['balance'] for i in v['line_ids']))>0.00501:errors.append({'source':d['source_name'],'field':'unbalanced'})
  require(not errors,'Commercial/date validation failed: '+json.dumps(errors[:8],ensure_ascii=False));return moves
 before=verify(docs,['draft','posted']);posting=m.j.setdefault('posting',{'operations':[],'documents':{},'stage':'posting_only_no_payment_or_reconciliation'});save(OUT/'invoice-pre-post-snapshot.json',{'moves':list(before.values())})
 # Resume by reading native state; posted documents are never posted twice.
 for d in docs:
  t=records[str(d['source_id'])]['target_id']
  if before[t]['state']=='posted':posting['documents'][str(d['source_id'])]={'status':'verified_posted','target_id':t,'after':before[t],'read_back_before_resume':True}
 m.persist();remaining=[d for d in sorted(docs,key=lambda d:(d['source']['date'],d['source_id'])) if before[records[str(d['source_id'])]['target_id']]['state']=='draft'];samples=[]
 if not posting['documents']:
  for kind in ['out_invoice','in_invoice']:
   if any(d['source']['move_type']==kind for d in remaining):samples.append(next(d for d in remaining if d['source']['move_type']==kind))
 groups=[[d] for d in samples];rest=[d for d in remaining if d not in samples];groups.extend(rest[i:i+20] for i in range(0,len(rest),20))
 for batch in groups:
  current=verify(batch,['draft']);targets=[records[str(d['source_id'])]['target_id'] for d in batch];op={'status':'intent','target_ids':targets,'source_references':[d['source_name'] for d in batch]};posting['operations'].append(op);m.persist()
  try:m.mutate('account.move','action_post',[targets],{'context':{'allowed_company_ids':[1]}})
  except Exception as e:
   op.update(status='failed_or_uncertain',error=str(e),native_after=m.b.read('account.move',targets,['state','name','date']));m.persist();raise
  after=verify(batch,['posted'])
  for d in batch:
   t=records[str(d['source_id'])]['target_id'];posting['documents'][str(d['source_id'])]={'status':'verified_posted','target_id':t,'source_name':d['source_name'],'after':after[t]}
  op['status']='verified';m.persist();print(json.dumps({'verified_posted':len(posting['documents']),'last_source':batch[-1]['source_name']}),flush=True)
 final=verify(docs,['posted']);summary={'database':m.b.db,'company_id':1,'posted':len(final),'scope_pending':1057-len(final),'types':dict(Counter(v['move_type'] for v in final.values())),'dates_totals_and_lines_match':True,'payments_or_reconciliation_performed':False};posting['summary']=summary;m.j['stage']='posting_partial_accounts_pending' if len(final)<1057 else 'invoices_bills_posted_payments_reconciliation_deferred';m.persist();save(OUT/'invoice-posted-final-report.json',{'summary':summary,'moves':list(final.values()),'source_target':[{'source_id':d['source_id'],'source_name':d['source_name'],'target_id':records[str(d['source_id'])]['target_id']} for d in docs]});print(json.dumps(summary),flush=True)
if __name__=='__main__':main()
