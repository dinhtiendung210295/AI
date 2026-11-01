"""Prepare complete historical draft invoices; no Odoo writes or master creation."""
from execute_pysb_stock_migration import Migration,rid,index,save,ROOT
from inspect_pysb_historical_invoices import OUT
import runpy,json,re
from collections import Counter
from historical_invoice_checks import prepare_context,enrich_document
def main():
 m=Migration();d=json.loads((OUT/'invoice-preflight-snapshot.json').read_text(encoding='utf8'));scope=json.loads((OUT/'invoice-order-scope.json').read_text(encoding='utf8'));selected=[s for s in scope['source_moves'] if s['state']=='posted' and s['move_type'] in ['out_invoice','in_invoice']];ls=index(d['source_lines']);maps={k:dict(v) for k,v in m.maps.items()};exceptions=[]
 def norm(s):return re.sub(r'[^a-z0-9]','',s.casefold())
 for model,field in [('account.account','code'),('account.journal','name'),('res.currency','name'),('account.payment.term','name')]:
  maps[model]={};master=d['masters'][model]
  for s in master['source']:
   if model=='account.journal':matches=[t for t in master['target'] if t['type']==s['type'] and t['code']==s['code']]
   else:
    value=s[field]
    if model=='res.currency' and value=='CNH':value='CNY'
    if model=='account.payment.term' and value=='14 Days':value='15 Days'
    matches=[t for t in master['target'] if norm(t[field])==norm(value)]
   if len(matches)==1:maps[model][s['id']]=matches[0]['id']
   else:exceptions.append({'model':model,'source_id':s['id'],'name':s[field],'reason':'missing_or_ambiguous','candidates':[t['id'] for t in matches]})
 maps['account.tax']={}
 partnerids={rid(s['partner_id']) for s in selected};missing=partnerids-set(maps['res.partner'])
 # Partner identity must be source-ID provenance, never inferred from display name.
 for sid in missing:
  hits=[x['res_id'] for x in d['external_ids'] if x['model']=='res.partner' and re.match(r'^(?:res_partner|partner)_'+str(sid)+r'(?:_|$)',x['name'])]
  if len(set(hits))==1:maps['res.partner'][sid]=hits[0]
 productids={rid(ls[i]['product_id']) for s in selected for i in s['invoice_line_ids'] if ls[i]['product_id']};missing=productids-set(maps['product.product'])
 if missing:
  mapper=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/so-po-migration/scripts/test_prepare_july_2026_so_po_migration.py'))['TargetMapper'](m.b);source=m.a.read('product.product',sorted(missing),['name','default_code','barcode','company_id']);maps['product.product'].update(mapper.products(source));exceptions.extend(mapper.exceptions)
 extra_fields=[k for k in ['base_price','packing_ratio','x_classification_code'] if k in d['schemas']['source_line'] and k in d['schemas']['target_line']];extras=index(m.a.read('account.move.line',[i for s in selected for i in s['invoice_line_ids']],extra_fields))
 context=prepare_context(m.a,m.b,selected,d['external_ids'])
 target_schema=m.b.call('account.move','fields_get',[],{'attributes':['type']})
 docs=[]
 for s in selected:
  errors=[]
  def mapped(model,sid):
   if not sid:return False
   value=maps.get(model,{}).get(sid)
   if not value:errors.append({'model':model,'source_id':sid,'reason':'missing_mapping'})
   return value
  partner=mapped('res.partner',rid(s['partner_id']));currency=mapped('res.currency',rid(s['currency_id']));journal=mapped('account.journal',rid(s['journal_id']));term=mapped('account.payment.term',rid(s['invoice_payment_term_id']));values=[];unlinked=[]
  for lid in s['invoice_line_ids']:
   x=ls[lid];v={'sequence':x['sequence'],'name':x['name']}
   if x['display_type'] in ['line_note','line_section']:v['display_type']=x['display_type']
   else:
    v.update(product_id=mapped('product.product',rid(x['product_id'])),product_uom_id=mapped('uom.uom',rid(x['product_uom_id'])),quantity=x['quantity'],price_unit=x['price_unit'],discount=x['discount'],tax_ids=[(6,0,[mapped('account.tax',i) for i in x['tax_ids']])],account_id=mapped('account.account',rid(x['account_id'])),**{k:extras[lid][k] for k in extra_fields});sale=[maps['sale.order.line'][i] for i in x.get('sale_line_ids',[]) if i in maps['sale.order.line']];v['sale_line_ids']=[(6,0,sale)];v['purchase_line_id']=maps['purchase.order.line'].get(rid(x.get('purchase_line_id')),False)
    if len(sale)!=len(x.get('sale_line_ids',[])) or (x.get('purchase_line_id') and not v['purchase_line_id']):unlinked.append({'source_line':lid,'source_sale_lines':x.get('sale_line_ids',[]),'source_purchase_line':x.get('purchase_line_id')})
   values.append({'source_line_id':lid,'values':v,'expected_subtotal':x['price_subtotal'],'expected_total':x['price_total']})
  header={'company_id':1,'move_type':s['move_type'],'partner_id':partner,'currency_id':currency,'journal_id':journal,'invoice_date':s['invoice_date'],'date':s['date'],'invoice_date_due':s['invoice_date_due'],'invoice_payment_term_id':term,'invoice_origin':s['invoice_origin'],'ref':s['ref'],'payment_reference':s['payment_reference'],'narration':s['narration'],'x_studio_v14_refererce':s['name']}
  provenance=[x['res_id'] for x in d['external_ids'] if x['model']=='account.move' and re.match(r'^account_move_'+str(s['id'])+r'(?:_|$)',x['name'])]
  target_provenance={}
  for ext in d['external_ids']:
   match=re.match(r'^account_move_(\d+)(?:_|$)',ext['name']) if ext['model']=='account.move' else None
   if match:target_provenance.setdefault(ext['res_id'],set()).add(int(match.group(1)))
  matches=[t for t in d['target_moves_before'] if t['id'] in provenance or (not (target_provenance.get(t['id'],set())-{s['id']}) and (t.get('x_studio_v14_refererce')==s['name'] or (not t.get('x_studio_v14_refererce') and t['name']==s['name'])))]
  if len(matches)>1:errors.append({'reason':'duplicate_target_reference'})
  if matches and matches[0]['state']!='draft':errors.append({'reason':'existing_posted_target_requires_separate_review','target_id':matches[0]['id']})
  docs.append({'source_id':s['id'],'source_name':s['name'],'source_write_date':s['write_date'],'target_existing':matches[0]['id'] if len(matches)==1 else False,'header':header,'lines':values,'source':s,'unlinked_outside_scope_lines':unlinked,'errors':errors})
 for document in docs:enrich_document(document,[ls[i] for i in document['source']['line_ids']],context,target_schema)
 save(OUT/'invoice-contact-preflight.json',{'mode':'read_only_report_no_contact_changes','documents':[{'source_id':doc['source_id'],'source_name':doc['source_name'],**doc['contact_review']} for doc in docs]})
 save(OUT/'invoice-draft-manifest.json',{'database':m.b.db,'company_id':1,'maps':maps,'documents':docs,'master_exceptions':exceptions,'deferred_documents':[s for s in scope['source_moves'] if s not in selected],'stage':'Draft Invoice/Bill only. No posting/payment/reconciliation/bank matching.'});print(json.dumps({'documents':len(docs),'eligible':sum(not x['errors'] for x in docs),'blocked':sum(bool(x['errors']) for x in docs),'master_exceptions':exceptions,'document_errors':[{'source':x['source_name'],'errors':x['errors']} for x in docs if x['errors']][:20],'unlinked_mixed_documents':sum(bool(x['unlinked_outside_scope_lines']) for x in docs),'contact_differences':sum(bool(x['contact_review']['differences']) for x in docs)},ensure_ascii=False))
if __name__=='__main__':main()
