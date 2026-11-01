"""Staging-only historical Credit Notes, explicit provenance and resumable journal."""
from execute_pysb_stock_migration import Migration,ROOT,rid,index,save,require
from pathlib import Path
import json,sys
OUT=ROOT/'outputs/pysb-credit-notes-20261014';OLD=ROOT/'outputs/pysb-invoice-migration-20261013'
def load(p):return json.loads(p.read_text(encoding='utf8'))
class Run(Migration):
 def __init__(self):
  super().__init__();OUT.mkdir(exist_ok=True);self.path=OUT/'execution-journal.json';self.j=load(self.path) if self.path.exists() else {'database':self.b.db,'company_id':1,'operations':[],'documents':{}}
def main():
 m=Run();maps={k:{int(s):t for s,t in v.items()} for k,v in load(OLD/'invoice-draft-manifest.json')['maps'].items()};original=load(OLD/'invoice-execution-journal.json')['documents'];scope=load(ROOT/'outputs/pysb-acceptance-20261014/so-invoiced-explanations.json');ids=sorted(x['id'] for x in scope['moves'] if x['move_type']=='out_refund' and x['state']=='posted');require(len(ids)==17,'Wrong scope')
 schema=m.a.call('account.move','fields_get',[],{'attributes':['type']});targetschema=m.b.call('account.move','fields_get',[],{'attributes':['type']});ef=[k for k in ['x_submission_uid','x_my_einvoice_longid','x_my_einvoice_link_to_portal','x_validation_time','x_einvoice_state'] if k in schema and k in targetschema]
 hf=['name','state','company_id','partner_id','currency_id','journal_id','date','invoice_date','invoice_date_due','invoice_payment_term_id','invoice_origin','ref','payment_reference','narration','reversed_entry_id','invoice_line_ids','amount_total','amount_tax','amount_untaxed','write_date'];source=m.a.read('account.move',ids,hf+ef);lf=['name','sequence','display_type','product_id','product_uom_id','quantity','price_unit','discount','tax_ids','account_id','sale_line_ids','price_subtotal','price_total','base_price','packing_ratio'];lines=index(m.a.read('account.move.line',[i for s in source for i in s['invoice_line_ids']],lf));accounts=index(m.b.read('account.account',list(set(maps['account.account'].values())),['active']));errors=[];docs=[]
 for s in source:
  require(rid(s['company_id'])==1,'Wrong source company');header={'company_id':1,'move_type':'out_refund','x_studio_v14_refererce':s['name'],**{k:s[k] for k in ['date','invoice_date','invoice_date_due','invoice_origin','ref','payment_reference','narration']}}
  for key,model in [('partner_id','res.partner'),('currency_id','res.currency'),('journal_id','account.journal'),('invoice_payment_term_id','account.payment.term')]:
   sid=rid(s[key]);header[key]=maps[model].get(sid,False)
   if sid and not header[key]:errors.append([s['name'],key,sid])
  reverse=rid(s['reversed_entry_id'])
  if reverse:
   if str(reverse) not in original:errors.append([s['name'],'reversed_entry_missing',reverse])
   else:header['reversed_entry_id']=original[str(reverse)]['target_id']
  vals=[]
  for lid in s['invoice_line_ids']:
   x=lines[lid];v={k:x[k] for k in ['name','sequence']}
   if x['display_type'] in ['line_note','line_section']:v['display_type']=x['display_type']
   else:
    v.update({k:x[k] for k in ['quantity','price_unit','discount','base_price','packing_ratio']})
    for key,model in [('product_id','product.product'),('product_uom_id','uom.uom'),('account_id','account.account')]:
     sid=rid(x[key]);v[key]=maps[model].get(sid,False)
     if sid and not v[key]:errors.append([s['name'],key,sid])
    if v['account_id'] and not accounts[v['account_id']]['active']:
     # Use the same configured account on the migrated original invoice for this product.
     candidates=[]
     if reverse and str(reverse) in original:
      inv=m.b.read('account.move',[original[str(reverse)]['target_id']],['invoice_line_ids'])[0];candidates=[rid(z['account_id']) for z in m.b.read('account.move.line',inv['invoice_line_ids'],['product_id','account_id']) if rid(z['product_id'])==v['product_id'] and z['account_id']]
     if len(set(candidates))==1:v['account_id']=candidates[0]
     else:errors.append([s['name'],'archived_account_unresolved',lid,candidates])
    v['sale_line_ids']=[(6,0,[maps['sale.order.line'][i] for i in x['sale_line_ids'] if i in maps['sale.order.line']])];v['tax_ids']=[(6,0,[maps['account.tax'][i] for i in x['tax_ids']])]
    if any(i not in maps['sale.order.line'] for i in x['sale_line_ids']):errors.append([s['name'],'unmapped_sale_line',lid])
   vals.append({'source_id':lid,'values':v,'source':x})
  docs.append({'source':s,'header':header,'lines':vals,'metadata':{k:s[k] for k in ef}})
 save(OUT/'plan.json',{'documents':docs,'errors':errors});print('Preflight',len(docs),'errors',errors,flush=True);require(not errors,'Resolve preflight first')
 if '--execute' not in sys.argv:return
 def verify(d,t,state):
  w=m.b.read('account.move',[t],['state','date','invoice_date','amount_total','amount_tax','amount_untaxed','invoice_line_ids','reversed_entry_id'])[0];require(w['state']==state,'Unexpected state');require(w['date']==d['source']['date'] and w['invoice_date']==d['source']['invoice_date'],'Date mismatch');require(all(abs(w[k]-d['source'][k])<0.00501 for k in ['amount_total','amount_tax','amount_untaxed']),'Amount mismatch');require(rid(w['reversed_entry_id'])==d['header'].get('reversed_entry_id',False),'Reversal link mismatch');ls=m.b.read('account.move.line',w['invoice_line_ids'],lf);require(len(ls)==len(d['lines']),'Line count')
  for expected,actual in zip(d['lines'],ls):
   for k,v in expected['values'].items():
    have=actual[k];want=v
    if k.endswith('_id'):have=rid(have)
    if k in ['sale_line_ids','tax_ids']:have=sorted(have);want=sorted(v[0][2])
    require(abs(have-want)<1e-6 if isinstance(want,(int,float)) and not isinstance(want,bool) else have==want,'Line mismatch '+k)
  return w,ls
 for d in sorted(docs,key=lambda d:(d['source']['date'],d['source']['id'])):
  sid=d['source']['id'];key=str(sid);fresh=m.a.read('account.move',[sid],['write_date'])[0];require(fresh['write_date']==d['source']['write_date'],'Source changed')
  ext=m.b.search_read('ir.model.data',[['module','=','pysb_v14'],['model','=','account.move'],['name','=','account_move_'+key]],['res_id']);rec=m.j['documents'].get(key,{})
  if not rec.get('target_id'):
   require(not ext,'Existing unjournaled Credit Note');require(not rec,'Uncertain prior create; investigate');require(not m.b.search_read('account.move',[['company_id','=',1],['move_type','=','out_refund'],['x_studio_v14_refererce','=',d['source']['name']]],['state']),'Duplicate reference');m.j['documents'][key]={'status':'create_intent','source_name':d['source']['name']};m.persist();t=m.mutate('account.move','create',[{**d['header'],'invoice_line_ids':[(0,0,x['values']) for x in d['lines']]}]);m.j['documents'][key].update(target_id=t,status='created');m.persist()
  else:t=rec['target_id']
  state=m.b.read('account.move',[t],['state'])[0]['state'];before,ls=verify(d,t,state);require(state in ['draft','posted'],'Unexpected state');m.j['documents'][key]['before']=before;m.persist();m.attach('account.move',[(sid,t)]);m.attach('account.move.line',[(x['source_id'],y['id']) for x,y in zip(d['lines'],ls)])
  if state=='draft':m.mutate('account.move','action_post',[[t]],{'context':{'allowed_company_ids':[1]}})
  after,ls=verify(d,t,'posted')
  if d['metadata']:m.mutate('account.move','write',[[t],d['metadata']]);actual=m.b.read('account.move',[t],ef)[0];require(all(actual[k]==v for k,v in d['metadata'].items()),'Metadata mismatch')
  m.j['documents'][key].update(status='verified_posted',after=after,source_line_target_pairs=[{'source_line':x['source_id'],'target_line':y['id']} for x,y in zip(d['lines'],ls)]);m.persist();print('Posted',d['source']['name'],t,flush=True)
 print('COMPLETE',len(m.j['documents']),flush=True)
if __name__=='__main__':main()
