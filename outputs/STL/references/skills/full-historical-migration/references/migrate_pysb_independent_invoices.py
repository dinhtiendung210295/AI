"""Native production create/post for verified independent invoice manifests.

Credit-note origin links are attached after posting to avoid Odoo's automatic
reconciliation of reversals. No payments, reconciliations, sends or submissions.
"""
import argparse
import copy
import json
import runpy
import socket
import sys
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
from historical_invoice_checks import validation_errors,require_manifest
I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'))
ROOT,OUT,ReadOnly,save=I['ROOT'],I['OUT'],I['ReadOnly'],I['save']
WORKFLOW=runpy.run_path(str(BASE/'production_workflow_rpc.py'))
def load(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def rid(x):return x[0] if isinstance(x,(tuple,list)) and x else x or False
CTX={'allowed_company_ids':[1],'active_test':False,'tz':'UTC','tracking_disable':True,'mail_notrack':True,'mail_create_nolog':True,'mail_create_nosubscribe':True,'mail_auto_subscribe_no_notify':True,'send_email':False}

class Run:
    def __init__(self):
        socket.setdefaulttimeout(120)
        self.a=ReadOnly('v14-prod',('http://175.145.85.151','paoyeang_live'));self.b=ReadOnly('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
        self.manifest=load('independent-invoice-manifest.json')
        assert self.manifest['database']==self.b.r.db and self.manifest['company_id']==1
        source_currency=rid(self.a.read('res.company',[1],['currency_id'])[0]['currency_id'])
        target_currency=rid(self.b.read('res.company',[1],['currency_id'])[0]['currency_id'])
        if self.a.read('res.currency',[source_currency],['name'])[0]['name']!=self.b.read('res.currency',[target_currency],['name'])[0]['name']:raise RuntimeError('Company currency mismatch')
        automation=load('invoice-automation-preflight.json')
        if automation['active_related_crons'] or any(x['communication_risk'] or x['state'] not in ['object_write'] for x in automation['actions']):raise RuntimeError('Communication automation needs review')
        self.j=load('independent-invoice-journal.json') if (OUT/'independent-invoice-journal.json').exists() else {'database':self.b.r.db,'company_id':1,'operations':[],'documents':{},'started_utc':datetime.now(timezone.utc).isoformat(),'scope':'create/post only; no payment/reconciliation/send/submission'}
        if any(x['status'] in ['intent','uncertain'] for x in self.j['operations']):raise RuntimeError('Uncertain previous RPC requires read-back recovery')
        require_manifest([d for d in self.manifest['documents'] if not d['errors']])

    def persist(self):save('independent-invoice-journal.json',self.j)
    def mutate(self,model,method,args):
        WORKFLOW['GUARD']()
        if (model,method) not in {('account.move','create'),('account.move','write'),('account.move','action_post'),('ir.model.data','create')}:raise RuntimeError('Forbidden mutation')
        op={'model':model,'method':method,'args':copy.deepcopy(args),'status':'intent','utc':datetime.now(timezone.utc).isoformat()};self.j['operations'].append(op);self.persist()
        try:
            value=WORKFLOW['call'](self.b.r,model,method,args,{'context':CTX});op['status']='returned';op['result']=value;self.persist();return value
        except Exception as e:op['status']='uncertain';op['error']=str(e);self.persist();raise

    def attach(self,model,pairs):
        values=[];names=[model.replace('.','_')+'_'+str(sid) for sid,tid in pairs]
        existing=self.b.scan('ir.model.data',[['module','=','pysb_v14'],['name','in',names]],['name','model','res_id'])
        for sid,tid in pairs:
            name=model.replace('.','_')+'_'+str(sid)
            old=[x for x in existing if x['name']==name]
            if old:
                if len(old)!=1 or old[0]['res_id']!=tid or old[0]['model']!=model:raise RuntimeError('External ID conflict')
            else:values.append({'module':'pysb_v14','name':name,'model':model,'res_id':tid,'noupdate':True})
        if values:self.mutate('ir.model.data','create',[values])

    def verify(self,d,tid,state,reverse_attached=False):
        fields='name state move_type company_id partner_id currency_id journal_id date invoice_date invoice_date_due invoice_payment_term_id invoice_origin ref x_studio_v14_refererce invoice_line_ids line_ids amount_untaxed amount_tax amount_total amount_total_signed invoice_user_id invoice_currency_rate x_foreign_to_company_rate reversed_entry_id is_move_sent x_einvoice_state x_submission_uid x_my_einvoice_longid x_my_einvoice_link_to_portal'.split()
        actual=self.b.read('account.move',[tid],fields)[0]
        rows=self.b.read('account.move.line',actual['line_ids'],'name sequence display_type product_id product_uom_id quantity price_unit discount tax_ids account_id sale_line_ids purchase_line_id price_subtotal price_total balance amount_currency base_price packing_ratio matched_debit_ids matched_credit_ids'.split())
        line_index={x['id']:x for x in rows};errors=validation_errors(d,actual,line_index)
        if actual['state']!=state:errors.append({'field':'state','expected':state,'actual':actual['state']})
        for field,want in d['header'].items():
            if field not in actual or field in ['invoice_currency_rate','x_foreign_to_company_rate','invoice_user_id']:continue
            if field=='reversed_entry_id' and not reverse_attached:want=False
            have=rid(actual[field]) if field.endswith('_id') else actual[field]
            if have!=want:errors.append({'field':field,'expected':want,'actual':have})
        got=[line_index[i] for i in actual['invoice_line_ids']]
        if len(got)!=len(d['lines']):errors.append({'field':'invoice_line_count'})
        else:
            for expected,row in zip(d['lines'],got):
                for field,want in expected['values'].items():
                    if field not in row:errors.append({'field':field,'reason':'missing_required_line_field'});continue
                    have=rid(row[field]) if field.endswith('_id') else row[field]
                    if field in ['sale_line_ids','tax_ids']:have=sorted(have);want=sorted(want[0][2])
                    mismatch=abs(have-want)>1e-6 if isinstance(want,(int,float)) and not isinstance(want,bool) else have!=want
                    if mismatch:errors.append({'source_line':expected['source_line_id'],'field':field,'expected':want,'actual':have})
                if not expected['values'].get('display_type'):
                    for field,key in [('price_subtotal','expected_subtotal'),('price_total','expected_total')]:
                        if abs(row[field]-expected[key])>0.00501:errors.append({'source_line':expected['source_line_id'],'field':field})
        if abs(sum(x['balance'] for x in rows))>0.00501:errors.append({'reason':'unbalanced_move'})
        if any(x.get('matched_debit_ids') or x.get('matched_credit_ids') for x in rows):errors.append({'reason':'unexpected_reconciliation'})
        rec=self.j['documents'][str(d['source_id'])];rec['last_readback']=actual;rec['validation_errors']=errors;self.persist()
        if errors:raise RuntimeError('Invoice read-back mismatch '+d['source_name']+': '+json.dumps(errors[:5]))
        return actual,got

    def process(self,d):
        if d['errors'] or d['target_existing']:raise RuntimeError('Held or existing document cannot be created')
        sid=d['source_id'];key=str(sid);rec=self.j['documents'].get(key)
        if rec and rec.get('status')=='verified_posted':return
        source=self.a.read('account.move',[sid],['state','write_date'])[0]
        if source['state']!='posted' or source['write_date']!=d['source_write_date']:raise RuntimeError('Source changed since snapshot')
        if rec and not rec.get('target_id'):raise RuntimeError('Prior create intent needs recovery')
        duplicate=self.b.scan('account.move',[['company_id','=',1],['x_studio_v14_refererce','=',d['source_name']]],['state'])
        if any(x['id']!=(rec or {}).get('target_id') for x in duplicate):raise RuntimeError('Existing unjournalled source reference')
        reconciliation_before=self.b.call('account.partial.reconcile','search_count',[[]])
        payment_before=self.b.call('account.payment','search_count',[[['company_id','=',1]]])
        if rec is None:
            rec={'status':'create_intent','source_id':sid,'source_name':d['source_name'],'move_type':d['source']['move_type']};self.j['documents'][key]=rec;self.persist()
            header={**d['header']};header.pop('reversed_entry_id',None)
            tid=self.mutate('account.move','create',[{**header,'invoice_line_ids':[(0,0,x['values']) for x in d['lines']]}])
            rec.update(target_id=tid,status='created_pending_verification');self.persist()
        tid=rec['target_id'];state=self.b.read('account.move',[tid],['state'])[0]['state']
        if state not in ['draft','posted']:raise RuntimeError('Unexpected existing native state')
        reverse_attached=bool(rec.get('reverse_attached'))
        actual,got=self.verify(d,tid,state,reverse_attached=reverse_attached)
        self.attach('account.move',[(sid,tid)])
        self.attach('account.move.line',[(e['source_line_id'],a['id']) for e,a in zip(d['lines'],got)])
        if state=='draft':self.mutate('account.move','action_post',[[tid]])
        if d['header'].get('reversed_entry_id') and not reverse_attached:
            # _post reconciles when reversed_entry_id is present before posting.
            # Attach only after posted, preserving the requested link without
            # invoking cancellation, payment or reconciliation workflows.
            self.mutate('account.move','write',[[tid],{'reversed_entry_id':d['header']['reversed_entry_id']}]);rec['reverse_attached']=True;self.persist()
        actual,got=self.verify(d,tid,'posted',reverse_attached=True)
        if self.b.call('account.partial.reconcile','search_count',[[]])!=reconciliation_before:raise RuntimeError('Reconciliation count changed; stop and investigate')
        if self.b.call('account.payment','search_count',[[['company_id','=',1]]])!=payment_before:raise RuntimeError('Payment count changed; stop and investigate')
        rec.update(status='verified_posted',after=actual,source_line_target_pairs=[{'source_line':e['source_line_id'],'target_line':a['id']} for e,a in zip(d['lines'],got)],verified_utc=datetime.now(timezone.utc).isoformat());self.persist()
        print(json.dumps({'posted_source':d['source_name'],'target_id':tid,'target_number':actual['name'],'type':d['source']['move_type']}),flush=True)

def main():
    if (OUT/'queue-handoff-request.json').exists():raise RuntimeError('Controlled handoff requested before invoice writer; no mutation attempted')
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['sample','batch'],default='sample');p.add_argument('--limit',type=int,default=20);p.add_argument('--source-id',type=int)
    args=p.parse_args();r=Run()
    write_lock=runpy.run_path(str(BASE/'production_write_lock.py'))['acquire'](OUT)
    docs=sorted([d for d in r.manifest['documents'] if not d['errors'] and not d['target_existing'] and r.j['documents'].get(str(d['source_id']),{}).get('status')!='verified_posted'],key=lambda d:(d['source']['date'],d['source_id']))
    if args.source_id:docs=[d for d in docs if d['source_id']==args.source_id]
    if args.mode=='sample':
        selected=[]
        for kind in ['in_invoice','out_invoice','out_refund','in_refund']:
            match=next((d for d in docs if d['source']['move_type']==kind),None)
            if match:selected.append(match)
    else:
        if not any(x['status']=='verified_posted' for x in r.j['documents'].values()):raise RuntimeError('Successful sample required')
        selected=docs[:args.limit]
    for doc in selected:r.process(doc)
    print(json.dumps({'verified_posted':sum(x.get('status')=='verified_posted' for x in r.j['documents'].values()),'types':dict(Counter(x['move_type'] for x in r.j['documents'].values() if x.get('status')=='verified_posted'))}),flush=True)

if __name__=='__main__':main()
