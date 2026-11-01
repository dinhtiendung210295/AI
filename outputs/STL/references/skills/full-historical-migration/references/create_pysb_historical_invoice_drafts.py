"""Idempotent draft-only creation with source freeze, exact commercial read-back."""
from execute_pysb_stock_migration import Migration,rid,index,save
from inspect_pysb_historical_invoices import OUT
from collections import Counter
import json,sys,re
from historical_invoice_checks import require_manifest,validation_errors,extra_read_fields
class Run(Migration):
 def __init__(self):
  super().__init__();self.path=OUT/'invoice-execution-journal.json';self.j=json.loads(self.path.read_text(encoding='utf8')) if self.path.exists() else {'database':self.b.db,'company_id':1,'operations':[],'documents':{},'stage':'draft_only_no_payments_no_reconciliation'}
 def persist(self):save(self.path,self.j)
def main():
 m=Run();manifest=json.loads((OUT/'invoice-draft-manifest.json').read_text(encoding='utf8'));docs=[d for d in manifest['documents'] if not d['errors']];require=__import__('execute_pysb_stock_migration').require
 require_manifest(docs)
 require(all(not d['target_existing'] for d in docs),'Existing targets need reviewed update path');ready=[d for d in docs if str(d['source_id']) not in m.j['documents']]
 require(all(r['status']=='verified' for r in m.j['documents'].values()),'Interrupted batch: read native states before retry')
 if '--batch' not in sys.argv:
  ready=[min([d for d in ready if d['source']['move_type']==t],key=lambda d:d['source_id']) for t in ['out_invoice','in_invoice'] if any(d['source']['move_type']==t for d in ready)]
 source=m.a.read('account.move',[d['source_id'] for d in docs],['write_date','state']);frozen=index(source);require(all(frozen[d['source_id']]['write_date']==d['source_write_date'] and frozen[d['source_id']]['state']=='posted' for d in docs),'Source changed since snapshot')
 custom='x_studio_v14_refererce';existing=m.b.search_read('account.move',[['company_id','=',1],[custom,'in',[d['source_name'] for d in ready]]],['name',custom,'state'])
 if existing:
  provenance=m.b.search_read('ir.model.data',[['module','=','pysb_v14'],['model','=','account.move'],['res_id','in',[x['id'] for x in existing]]],['name','res_id']);linked={}
  for x in provenance:
   match=re.match(r'^account_move_(\d+)(?:_|$)',x['name'])
   if match:linked.setdefault(x['res_id'],set()).add(int(match.group(1)))
  existing=[x for x in existing if not linked.get(x['id']) or any(d['source_id'] in linked[x['id']] for d in ready if d['source_name']==x[custom])]
 require(not existing,'Unjournalled target found: investigate before create')
 def verify(batch,ids):
  moves=index(m.b.read('account.move',ids,['move_type','state','company_id','partner_id','currency_id','journal_id','invoice_date','date','invoice_date_due','invoice_payment_term_id','invoice_origin','ref',custom,'invoice_line_ids','line_ids','amount_untaxed','amount_tax','amount_total']+extra_read_fields(batch)));alllines=index(m.b.read('account.move.line',[i for x in moves.values() for i in x['line_ids']],['name','sequence','display_type','product_id','product_uom_id','quantity','price_unit','discount','tax_ids','account_id','sale_line_ids','purchase_line_id','price_subtotal','price_total','balance','amount_currency','base_price','packing_ratio']))
  for d,t in zip(batch,ids):
   v=moves[t];s=d['source'];errors=validation_errors(d,v,alllines);tolerance=0.00501
   for k,expected in d['header'].items():
    if k in ['invoice_currency_rate','x_foreign_to_company_rate','invoice_user_id']:continue
    if k in v and (rid(v[k]) if k.endswith('_id') else v[k])!=expected:errors.append({'field':k,'source_mapped':expected,'target':v[k]})
   if v['state']!='draft':errors.append({'field':'state','expected':'draft','actual':v['state']})
   for k in ['amount_untaxed','amount_tax','amount_total']:
    if abs(v[k]-s[k])>tolerance:errors.append({'field':k,'source':s[k],'target':v[k]})
   # Odoo preserves command order; read invoice_line_ids in original order.
   got=[alllines[i] for i in v['invoice_line_ids']]
   if len(got)!=len(d['lines']):errors.append({'field':'line_count','source':len(d['lines']),'target':len(got)})
   else:
    for expected,actual in zip(d['lines'],got):
     val=expected['values']
     for k,want in val.items():
      if k not in actual:continue
      have=actual[k]
      if k.endswith('_id'):have=rid(have)
      if k in ['tax_ids','sale_line_ids']:have=sorted(have);want=sorted(want[0][2])
      mismatch=abs(have-want)>1e-6 if isinstance(want,(int,float)) and not isinstance(want,bool) else have!=want
      if mismatch:errors.append({'source_line':expected['source_line_id'],'target_line':actual['id'],'field':k,'expected':want,'actual':have})
     if not val.get('display_type'):
      for k,want in [('price_subtotal',expected['expected_subtotal']),('price_total',expected['expected_total'])]:
       if abs(actual[k]-want)>tolerance:errors.append({'source_line':expected['source_line_id'],'field':k,'source':want,'target':actual[k]})
   balance=sum(alllines[i]['balance'] for i in v['line_ids'])
   if abs(balance)>0.00501:errors.append({'field':'journal_balance','value':balance})
   rec=m.j['documents'][str(d['source_id'])];rec.update(status='verification_failed' if errors else 'verified',after=v,errors=errors,source_line_target_pairs=[{'source_line':e['source_line_id'],'target_line':a['id']} for e,a in zip(d['lines'],got)]);m.persist();require(not errors,'Invoice read-back failed '+d['source_name']+': '+json.dumps(errors[:8],ensure_ascii=False))
  # Provenance attached only after exact commercial validation.
  m.attach('account.move',[(d['source_id'],t) for d,t in zip(batch,ids)]);m.attach('account.move.line',[(p['source_line'],p['target_line']) for d in batch for p in m.j['documents'][str(d['source_id'])]['source_line_target_pairs']]);m.persist()
 for start in range(0,len(ready),20):
  batch=ready[start:start+20]
  for d in batch:m.j['documents'][str(d['source_id'])]={'source_id':d['source_id'],'source_name':d['source_name'],'status':'intent','source_move_type':d['source']['move_type']}
  m.persist();values=[{**d['header'],'invoice_line_ids':[(0,0,x['values']) for x in d['lines']]} for d in batch];ids=m.mutate('account.move','create',[values],{'context':{'allowed_company_ids':[1],'mail_create_nosubscribe':True,'mail_notrack':True}});require(len(ids)==len(batch),'Native create count mismatch')
  for d,t in zip(batch,ids):m.j['documents'][str(d['source_id'])].update(target_id=t,status='created_pending_verification')
  m.persist();verify(batch,ids);print(json.dumps({'verified_drafts':len(m.j['documents']),'last_source':batch[-1]['source_name'],'new_target_ids':ids}),flush=True)
 summary={'created_verified':len(m.j['documents']),'by_type':dict(Counter(x['source_move_type'] for x in m.j['documents'].values())),'stage':'draft_only','remaining':len(docs)-len(m.j['documents']),'blocked_documents':[{'source_id':d['source_id'],'source_name':d['source_name'],'errors':d['errors']} for d in manifest['documents'] if d['errors']]};save(OUT/'invoice-creation-summary.json',summary);print(json.dumps(summary))
if __name__=='__main__':main()
