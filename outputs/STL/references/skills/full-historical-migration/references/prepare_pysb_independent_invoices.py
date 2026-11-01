"""Read-only production Invoice/Bill/Credit Note manifest, using shared FX checks."""
import hashlib
import json
import re
import runpy
import socket
import sys
from collections import Counter
from pathlib import Path

BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
from historical_invoice_checks import prepare_context,enrich_document,salesperson
I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'))
ROOT,OUT,ReadOnly,save=I['ROOT'],I['OUT'],I['ReadOnly'],I['save']
def load(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False
def norm(x):return re.sub('[^a-z0-9]','',(x or '').casefold())

def save_versioned(name,data):
    previous=OUT/name
    if previous.exists():
        raw=previous.read_bytes();digest=hashlib.sha256(raw).hexdigest()[:16]
        history=OUT/'invoice-manifest-history';history.mkdir(exist_ok=True)
        archived=history/(previous.stem+'-'+digest+'.json')
        if not archived.exists():archived.write_bytes(raw)
    save(name,data)

def main():
    socket.setdefaulttimeout(120)
    a=ReadOnly('v14-prod',('http://175.145.85.151','paoyeang_live'));b=ReadOnly('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    a.search_read=a.scan;b.search_read=b.scan
    docs=load('source-invoices.json');lines={x['id']:x for x in load('source-invoice-lines.json')}
    maps={m:{int(s):t for s,t in p.items()} for m,p in load('resolved-master-evidence.json')['maps'].items()}
    if (OUT/'independent-receipts-journal.json').exists():
        for m,pairs in load('independent-receipts-journal.json')['maps'].items():maps.setdefault(m,{}).update({int(s):t for s,t in pairs.items()})
    source_extra=a.read('account.move',[d['id'] for d in docs], 'invoice_payment_term_id payment_reference narration is_move_sent x_einvoice_state x_submission_uid x_my_einvoice_longid x_my_einvoice_link_to_portal write_date'.split())
    extra={x['id']:x for x in source_extra};save_versioned('source-invoice-extra.json',source_extra)
    source_line_extra=a.read('account.move.line',[i for d in docs for i in d['invoice_line_ids']],['sequence','base_price','packing_ratio'])
    lextra={x['id']:x for x in source_line_extra};save_versioned('source-invoice-line-extra.json',source_line_extra)
    fields=b.call('account.move','fields_get',[],{'attributes':['type','readonly','store']})
    context=prepare_context(a,b,docs,[],validated_partner_mapping=maps.get('res.partner',{}))
    target_accounts=load('target-accounts.json');source_accounts=load('source-accounts.json')
    account_issues=[];maps['account.account']={}
    for s in source_accounts:
        candidates=[t for t in target_accounts if norm(t['code'])==norm(s['code']) and t.get('active',True) and t['internal_group']==s['internal_group'] and norm(t['name'])==norm(s['name'])]
        if len(candidates)==1:maps['account.account'][s['id']]=candidates[0]['id']
        else:account_issues.append({'source_id':s['id'],'code':s['code'],'reason':'active_same_code_name_group_not_unique'})
    historical=None;historical_select=None
    if (OUT/'operator-historical-mapping-approval.json').exists():
        if not load('operator-historical-mapping-approval.json').get('approved'):raise RuntimeError('Historical mapping not approved')
        historical=load('historical-account-term-inference.json')
        helper=runpy.run_path(str(BASE/'historical_account_selection.py'));historical_select=helper['select']
        for model,key,reader in [('account.account','target_accounts',b),('account.payment.term','target_terms',b),('account.payment.term.line','target_term_lines',b),('account.payment.term','source_terms',a),('account.payment.term.line','source_term_lines',a)]:
            expected=historical[key]
            if expected:
                live=reader.read(model,[x['id'] for x in expected],list(expected[0]))
                if {x['id']:x for x in live}!={x['id']:x for x in expected}:raise RuntimeError('Historical mapping metadata changed: '+key)
    for model,filename,key in [('account.journal','account.journal','code'),('res.currency','res.currency','name')]:
        maps[model]={};src=load('source-'+filename+'.json');dst=load('target-'+filename+'.json')
        for s in src:
            value={'CNH':'CNY'}.get(s[key],s[key]) if model=='res.currency' else s[key]
            candidates=[t for t in dst if t[key]==value and (model!='account.journal' or t['type']==s['type'])]
            if len(candidates)==1:maps[model][s['id']]=candidates[0]['id']
    term_ids={rid(x.get('invoice_payment_term_id')) for x in source_extra};term_ids.discard(False)
    source_terms=a.read('account.payment.term',term_ids,['name'])
    target_terms=b.scan('account.payment.term',[],['name','active'])
    maps.setdefault('account.payment.term',{})
    for s in source_terms:
        if s['id'] in maps['account.payment.term']:continue
        matches=[t for t in target_terms if norm(t['name'])==norm(s['name']) and t.get('active',True)]
        if len(matches)==1:maps['account.payment.term'][s['id']]=matches[0]['id']
    if historical:maps['account.payment.term'].update(helper['term_mapping'](historical))
    # Read current linked orders. Invoices linked to held/unconfirmed warehouse
    # orders stay pending rather than being detached to force a clean result.
    source_sol={x['id']:x for x in load('verify-source-sale.order.line.json')}
    source_pol={x['id']:x for x in load('verify-source-purchase.order.line.json')}
    order_states={};line_received={}
    for model,ids in [('sale.order',maps.get('sale.order',{}).values()),('purchase.order',maps.get('purchase.order',{}).values())]:
        rows=b.read(model,ids,['state']);order_states[model]={x['id']:x['state'] for x in rows}
    current_pol=b.read('purchase.order.line',maps.get('purchase.order.line',{}).values(),['qty_received'])
    current_sol=b.read('sale.order.line',maps.get('sale.order.line',{}).values(),['qty_delivered'])
    line_received['purchase.order.line']={x['id']:x['qty_received'] for x in current_pol}
    line_received['sale.order.line']={x['id']:x['qty_delivered'] for x in current_sol}
    existing=b.scan('account.move',[['company_id','=',1],['move_type','in',['out_invoice','out_refund','in_invoice','in_refund']]],['name','ref','state','x_studio_v14_refererce'])
    save('target-invoices-current.json' if (OUT/'target-invoices-before-independent.json').exists() else 'target-invoices-before-independent.json',existing)
    existing_ids=b.scan('ir.model.data',[['module','=','pysb_v14'],['model','=','account.move']],['name','res_id'])
    for x in existing_ids:
        match=re.fullmatch('account_move_(\\d+)',x['name'])
        if match:maps.setdefault('account.move',{})[int(match[1])]=x['res_id']
    prepared=[]
    for source in docs:
        s={**source,**{k:v for k,v in extra[source['id']].items() if k!='write_date'}};errors=[]
        d={'source_id':s['id'],'source_name':s['name'],'source':s,'source_write_date':source['write_date'],'errors':errors,'lines':[]}
        if extra[s['id']]['write_date']!=source['write_date']:errors.append({'reason':'source_changed_since_snapshot'})
        def mapped(model,sid):
            if not sid:return False
            value=maps.get(model,{}).get(sid)
            if not value:errors.append({'reason':'missing_mapping','model':model,'source_id':sid})
            return value
        def account_for_line(line):
            sid=rid(line['account_id'])
            selection=historical_select(historical,sid,rid(line['product_id']),s['move_type']) if historical else None
            if selection:
                d.setdefault('historical_account_proofs',[]).append({'source_line':line['id'],'source_account':sid,**selection})
                return selection['target_account']
            return mapped('account.account',sid)
        header={'company_id':1,'move_type':s['move_type'],'partner_id':mapped('res.partner',rid(s['partner_id'])),
                'currency_id':mapped('res.currency',rid(s['currency_id'])),'journal_id':mapped('account.journal',rid(s['journal_id'])),
                'invoice_date':s['invoice_date'],'date':s['date'],'invoice_date_due':s['invoice_date_due'],
                'invoice_payment_term_id':mapped('account.payment.term',rid(s.get('invoice_payment_term_id'))),
                'invoice_origin':s['invoice_origin'],'ref':s['ref'],'payment_reference':s.get('payment_reference'),
                'narration':s.get('narration'),'x_studio_v14_refererce':s['name'],'invoice_user_id':False}
        for field in ['is_move_sent','x_einvoice_state','x_submission_uid','x_my_einvoice_longid','x_my_einvoice_link_to_portal']:
            if field in s and field in fields:header[field]=s[field]
        if s.get('reversed_entry_id'):
            original=maps.get('account.move',{}).get(rid(s['reversed_entry_id']))
            if original:header['reversed_entry_id']=original
            else:errors.append({'reason':'original_invoice_not_yet_mapped','source_id':rid(s['reversed_entry_id'])})
        d['header']=header
        for lid in s['invoice_line_ids']:
            x=lines[lid];v={'name':x['name'],'sequence':lextra[lid]['sequence']}
            if x['display_type'] in ['line_note','line_section']:v['display_type']=x['display_type']
            else:
                if x.get('tax_ids'):errors.append({'reason':'tax_mapping_requires_review','source_line':lid})
                v.update(product_id=mapped('product.product',rid(x['product_id'])),product_uom_id=mapped('uom.uom',rid(x['product_uom_id'])),
                         quantity=x['quantity'],price_unit=x['price_unit'],discount=x['discount'],tax_ids=[(6,0,[])],account_id=account_for_line(x),
                         sale_line_ids=[(6,0,[mapped('sale.order.line',i) for i in x.get('sale_line_ids',[])])],purchase_line_id=mapped('purchase.order.line',rid(x.get('purchase_line_id'))))
                for field in ['base_price','packing_ratio']:
                    if field in lextra[lid] and field in b.fields('account.move.line',[field]):v[field]=lextra[lid][field]
                for lm,linked,source_index,header_model,fulfilled in [('sale.order.line',x.get('sale_line_ids',[]),source_sol,'sale.order','qty_delivered'),('purchase.order.line',[rid(x['purchase_line_id'])] if x.get('purchase_line_id') else [],source_pol,'purchase.order','qty_received')]:
                    for source_lid in linked:
                        sl=source_index.get(source_lid);tlid=maps.get(lm,{}).get(source_lid)
                        soid=rid(sl['order_id']) if sl else False;toid=maps.get(header_model,{}).get(soid)
                        expected=sl.get(fulfilled) if sl else None;actual=line_received[lm].get(tlid)
                        if not toid or order_states[header_model].get(toid) not in ['sale','purchase','done'] or expected is None or actual is None or abs(expected-actual)>1e-6:
                            errors.append({'reason':'linked_warehouse_order_not_ready','model':header_model,'source_line':source_lid})
            d['lines'].append({'source_line_id':lid,'values':v,'expected_subtotal':x['price_subtotal'],'expected_total':x['price_total']})
        enrich_document(d,[lines[i] for i in s['line_ids']],context,fields)
        if s['move_type']=='out_refund':
            try:header['invoice_user_id']=salesperson(rid(s['invoice_user_id']),context['source_users'],context['target_users'],{'warehouse':'BILLING1'})
            except ValueError as e:errors.append({'reason':'salesperson_mapping_requires_review','detail':str(e)})
        d['target_existing']=maps.get('account.move',{}).get(s['id'])
        candidates=[t for t in existing if t.get('x_studio_v14_refererce')==s['name'] and t['id']!=d['target_existing']]
        if candidates:errors.append({'reason':'unproven_existing_reference','target_ids':[t['id'] for t in candidates]})
        prepared.append(d)
    summary={'documents':len(prepared),'eligible_new':sum(not d['errors'] and not d['target_existing'] for d in prepared),'existing':sum(bool(d['target_existing']) for d in prepared),
             'held':sum(bool(d['errors']) for d in prepared),'hold_reasons':dict(Counter(e['reason'] for d in prepared for e in d['errors']))}
    save_versioned('independent-invoice-manifest.json',{'database':b.r.db,'company_id':1,'scope':load('scope.json'),'documents':prepared,'maps':maps,'account_issues':account_issues,'summary':summary,
         'policy':'Sequence v19, preserve source reference; no payment, reconciliation, external e-invoice submission or email sending.'})
    print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
