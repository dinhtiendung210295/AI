"""Explicit Bruce-authorized PO identity repair and 19 missing PO imports.

Public ORM only, single writer, intent/result before/after every mutation.
No receipt validation, billing, contact or product creation.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import runpy
import subprocess
import sys
import uuid

BASE=Path(__file__).parent
P=runpy.run_path(str(BASE/'confirm_pysb_prod_orders.py'))
C=runpy.run_path(str(BASE/'run_pysb_phased_migration.py'))
rid=P['rid'];load=P['load'];save=P['save'];digest=P['digest']


def create_values(header,lines,maps):
    def mapped(model,value):
        sid=rid(value)
        if not sid:return False
        if sid not in maps.get(model,{}):raise RuntimeError('Missing mapping '+model+':'+str(sid))
        return maps[model][sid]
    commands=[]
    for line in sorted(lines,key=lambda x:(x.get('sequence',0),x['id'])):
        values=dict(sequence=line.get('sequence',0),name=line.get('name') or '',display_type=line.get('display_type') or False,product_qty=0)
        if not line.get('display_type'):
            values.update(product_id=mapped('product.product',line['product_id']),product_uom_id=mapped('uom.uom',line['product_uom']),product_qty=line['product_qty'],price_unit=line['price_unit'],discount=line.get('discount',0),date_planned=line['date_planned'],tax_ids=[(6,0,[mapped('account.tax',x) for x in line['taxes_id']])])
        commands.append((0,0,values))
    return dict(company_id=1,partner_id=mapped('res.partner',header['partner_id']),currency_id=mapped('res.currency',header['currency_id']),payment_term_id=mapped('account.payment.term',header.get('payment_term_id')),picking_type_id=mapped('stock.picking.type',header['picking_type_id']),user_id=mapped('res.users',header.get('user_id')),date_order=header['date_order'],partner_ref=header.get('partner_ref') or False,note=((('Attn: '+header['attn']+'\n\n') if header.get('attn') else '')+(header.get('notes') or '')),x_studio_v14_reference_studio=header['name'],x_studio_date_ref_v14_studio=header.get('date_approve') or header['date_order'],order_line=commands)


class Run:
    def __init__(self,out,identity,token):
        self.out=out;self.phase=out/'phases';self.identity=identity;self.token=token
        self.a=P['I']['ReadOnly']('v14-prod',('http://175.145.85.151','paoyeang_live'))
        self.b=P['I']['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
        self.plan=load(self.phase/'authorized-po-completion-plan.json')
        if self.plan['unresolved_dependencies']:raise RuntimeError('Unresolved PO dependencies')
        self.maps={m:{int(k):v for k,v in pairs.items()} for m,pairs in self.plan['maps'].items()}
        self.maps,_=runpy.run_path(str(BASE/'approved_order_currency_mapping.py'))['apply'](self.maps,self.a.scan('res.currency',[['name','=','CNH']],['name','rounding']),self.b.scan('res.currency',[['name','=','CNY']],['name','rounding']))
        self.log=P['Log'](self.phase,identity)
        if self.log.unresolved():raise RuntimeError('Prior unresolved writes require readback')
        path=self.phase/'authorized-po-gaps-journal.json'
        self.j=load(path) if path.exists() else dict(identity=identity,orders={},repairs={})
        if self.j['identity']!=identity:raise RuntimeError('PO gap journal scope mismatch')

    def persist(self):save(self.phase/'authorized-po-gaps-journal.json',self.j)

    def mutate(self,key,model,method,args):
        oid=self.identity['scope_hash']+':authorized-po-gaps:'+key
        self.log.append_intent(dict(operation_id=oid,phase='confirm-po',model=model,method=method,args=args,authorization='Bruce annotations: repair 8 draft, add 19 missing, fix 5 confirmed'))
        try:value=P['W']['call'](self.b.r,model,method,args,{'context':dict(pysb_phase_token=self.token,tz='UTC',tracking_disable=True,mail_notrack=True,mail_create_nolog=True,mail_create_nosubscribe=True,mail_auto_subscribe_no_notify=True,send_email=False)})
        except Exception:
            self.log.mark_uncertain(oid,'RPC failed; inspect readback before further writes');raise
        self.log.append_result(oid,dict(result=value))
        return value

    def attach(self,model,sid,tid):
        name=model.replace('.','_')+'_'+str(sid)
        existing=self.b.scan('ir.model.data',[['module','=','pysb_v14'],['name','=',name]],['model','res_id'])
        if existing:
            if len(existing)!=1 or existing[0]['model']!=model or existing[0]['res_id']!=tid:raise RuntimeError('External ID conflict')
        else:self.mutate('xmlid:'+model+':'+str(sid),'ir.model.data','create',[dict(module='pysb_v14',name=name,model=model,res_id=tid,noupdate=True)])
        self.maps.setdefault(model,{})[sid]=tid

    def install_maps(self):
        path=self.out/'resolved-master-evidence.json';current=load(path)
        history=self.phase/'history';history.mkdir(exist_ok=True)
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        save(history/('resolved-masters-before-po-gap-'+stamp+'.json'),current)
        # Merge only evidence-backed new identities; preserve all existing maps.
        for proof in self.plan['identity_proofs']:
            model=proof['model'];sid=proof['source']['id'];tid=proof['target']['id']
            if proof.get('requires_schedule_review'):continue
            if model not in ('res.partner','product.product','stock.picking.type','res.users','account.payment.term'):continue
            old=current['maps'].setdefault(model,{}).get(str(sid))
            if old is not None and old!=tid:raise RuntimeError('Existing master mapping conflict')
            current['maps'][model][str(sid)]=tid
            current.setdefault('resolutions',[]).append(dict(model=model,source_id=sid,target_id=tid,evidence='authorized-po-completion-plan.json',authorization='Bruce requested fixing PO exceptions'))
        save(path,current)
        self.j['repairs']['mapping_overlay']=dict(status='verified',evidence='authorized-po-completion-plan.json');self.persist()

    def repair_ed42(self):
        key='ED42:5479'
        if self.j['repairs'].get(key,{}).get('status')=='verified':return
        order=self.b.read('purchase.order',[860],['state','order_line','picking_ids','invoice_ids'])[0]
        if order['state'] not in ('draft','sent') or order['picking_ids'] or order['invoice_ids']:raise RuntimeError('ED42 PO is no longer an untouched draft')
        old=self.b.read('purchase.order.line',[2946,2947],['order_id','product_id','product_qty','product_uom_id','price_unit','discount','tax_ids','price_subtotal','price_total'])
        self.j['repairs'][key]=dict(status='prepared',before=old);self.persist()
        for lid,previous,new in [(2946,129963,130515),(2947,129962,130516)]:
            row=next(x for x in old if x['id']==lid)
            if rid(row['order_id'])!=860 or rid(row['product_id'])!=previous:raise RuntimeError('ED42 line no longer matches approved repair')
            product=self.b.read('product.product',[new],['active','uom_id'])[0]
            if not product['active'] or rid(product['uom_id'])!=rid(row['product_uom_id']):raise RuntimeError('ED42 master/unit invalid')
            self.mutate('ed42-line:'+str(lid),'purchase.order.line','write',[[lid],{'product_id':new}])
        after=self.b.read('purchase.order.line',[2946,2947],list(old[0]))
        for row in after:
            expected=copy.deepcopy(next(x for x in old if x['id']==row['id']))
            expected['product_id']=row['product_id']
            P['assert_fresh'](expected,row,'ED42 commercial line')
        if [rid(x['product_id']) for x in after]!=[130515,130516]:raise RuntimeError('ED42 product readback failed')
        self.j['repairs'][key].update(status='verified',after=after);self.persist();self.log.build_checkpoint()

    def import_one(self,sid):
        key=str(sid)
        if key in self.j['orders']:
            if self.j['orders'][key].get('status')=='verified_draft':return
            if self.j['orders'][key].get('status')!='verified_not_created_schema_error':raise RuntimeError('Incomplete imported PO requires readback recovery')
        s=next(x for x in self.plan['source_headers'] if x['id']==sid)
        sl=[x for x in self.plan['source_lines'] if rid(x['order_id'])==sid]
        P['assert_fresh'](s,self.a.read('purchase.order',[sid],list(s))[0],'Source PO before create')
        P['assert_fresh']({x['id']:x for x in sl},{x['id']:x for x in self.a.read('purchase.order.line',[x['id'] for x in sl],list(sl[0]))},'Source PO lines before create')
        names=['purchase_order_'+str(sid)]+['purchase_order_line_'+str(x['id']) for x in sl]
        if self.b.scan('ir.model.data',[['module','=','pysb_v14'],['name','in',names]],['name','res_id']):raise RuntimeError('Source PO/line XMLID already exists')
        if self.b.scan('purchase.order',['|',['x_studio_v14_reference_studio','=',s['name']],['name','=',s['name']]],['name','state']):raise RuntimeError('Target PO reference already exists')
        values=create_values(s,sl,self.maps)
        unsupported=set(values)-set(self.b.fields('purchase.order',list(values)))
        linekeys={k for c in values['order_line'] for k in c[2]}
        unsupported_lines=linekeys-set(self.b.fields('purchase.order.line',list(linekeys)))
        if unsupported or unsupported_lines:raise RuntimeError('Unsupported import schema fields: '+str(unsupported|unsupported_lines))
        before={m:self.b.call(m,'search_count',[[['company_id','=',1]]]) for m in ('purchase.order','account.move','mrp.production')}
        self.j['orders'][key]=dict(source_id=sid,source_name=s['name'],status='create_intent',expected=values);self.persist()
        tid=self.mutate('create-po:'+str(sid)+':'+digest(values),'purchase.order','create',[values])
        self.j['orders'][key].update(target_id=tid,status='created_pending_validation');self.persist()
        target=self.b.read('purchase.order',[tid],['state','company_id','partner_id','currency_id','payment_term_id','picking_type_id','user_id','date_order','partner_ref','order_line','amount_untaxed','amount_tax','amount_total','picking_ids','invoice_ids','x_studio_v14_reference_studio'])[0]
        for field in ('partner_id','currency_id','payment_term_id','picking_type_id','user_id','company_id'):
            if rid(target[field])!=values[field]:raise RuntimeError('Created PO header mismatch '+field)
        if target['state']!='draft' or target['picking_ids'] or target['invoice_ids'] or target['date_order']!=s['date_order']:raise RuntimeError('Created PO workflow/date mismatch')
        rounding=self.b.read('res.currency',[values['currency_id']],['rounding'])[0]['rounding']
        for f in ('amount_untaxed','amount_tax','amount_total'):
            if not P['R']['same_number'](s[f],target[f],rounding):raise RuntimeError('Created PO amount mismatch '+f)
        tl=self.b.read('purchase.order.line',target['order_line'],['order_id','sequence','display_type','name','product_id','product_uom_id','product_qty','date_planned','price_unit','discount','tax_ids','price_subtotal','price_total'])
        ordered_s=sorted(sl,key=lambda x:(x.get('sequence',0),x['id']));ordered_t=sorted(tl,key=lambda x:(x.get('sequence',0),x['id']))
        if len(ordered_s)!=len(ordered_t):raise RuntimeError('Imported PO line count differs')
        for src,dst,command in zip(ordered_s,ordered_t,values['order_line']):
            expected=command[2]
            for field,value in expected.items():
                actual=dst[field]
                if field in ('product_id','product_uom_id'):actual=rid(actual)
                if field=='tax_ids':value=value[0][2];actual=sorted(actual);value=sorted(value)
                if actual!=value:raise RuntimeError('Imported PO line mismatch '+field)
            for f in ('price_subtotal','price_total'):
                if not src.get('display_type') and not P['R']['same_number'](src[f],dst[f],rounding):raise RuntimeError('Imported PO line amount mismatch')
        after={m:self.b.call(m,'search_count',[[['company_id','=',1]]]) for m in before}
        if after!={**before,'purchase.order':before['purchase.order']+1}:raise RuntimeError('Unexpected records created by PO import')
        self.attach('purchase.order',sid,tid)
        for src,dst in zip(ordered_s,ordered_t):self.attach('purchase.order.line',src['id'],dst['id'])
        self.j['orders'][key].update(status='verified_draft',after=target,line_mapping={str(s['id']):t['id'] for s,t in zip(ordered_s,ordered_t)});self.persist();self.log.build_checkpoint()
        print(__import__('json').dumps(dict(source_id=sid,target_id=tid,created_draft=True,verified=True,new_receipts=0,new_invoices=0)),flush=True)


def main(directory,mode):
    out=Path(directory).resolve();phase=out/'phases';lock=runpy.run_path(str(BASE/'production_write_lock.py'))['acquire'](out)
    old=None;active=False
    try:
        identity,_=C['validate_context'](out)
        approval=load(phase/'authorized-po-gaps-approval.json')
        if not approval['approved'] or approval['identity']!=identity:raise RuntimeError('New PO authorization missing')
        tests=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(BASE/'tests'),'-q'],capture_output=True,text=True)
        save(phase/'authorized-po-gaps-tests.json',dict(returncode=tests.returncode,output=tests.stdout+tests.stderr))
        if tests.returncode:raise RuntimeError('Offline tests failed')
        code=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        if mode=='batch':
            sample=load(phase/'authorized-po-gaps-sample.json')
            if not sample.get('passed') or sample['code_hash']!=code:raise RuntimeError('Missing successful import sample')
        token=uuid.uuid4().hex;runner=Run(out,identity,token)
        old=load(phase/'phased-control-enabled.json')
        save(phase/'phased-control-enabled.json',dict(identity=identity,supported_phases=['confirm-po'],code_hash=code))
        save(phase/'active-phase.json',dict(identity=identity,phase='confirm-po',pid=os.getpid(),token=token));active=True
        runner.install_maps();runner.repair_ed42()
        count=0
        for sid in approval['missing_source_ids']:
            if runner.j['orders'].get(str(sid),{}).get('status')=='verified_draft':continue
            runner.import_one(sid);count+=1
            if mode=='sample':break
        # Persist newly created order/line maps without changing frozen scope.
        resolved=load(out/'resolved-master-evidence.json')
        for sid,item in runner.j['orders'].items():
            if item['status']!='verified_draft':continue
            resolved['maps'].setdefault('purchase.order',{})[sid]=item['target_id']
            resolved['maps'].setdefault('purchase.order.line',{}).update(item['line_mapping'])
        save(out/'resolved-master-evidence.json',resolved)
        save(phase/('authorized-po-gaps-'+mode+'.json'),dict(passed=bool(count),code_hash=code,created_verified_this_run=count,completed_utc=datetime.now(timezone.utc).isoformat()))
    finally:
        if active:save(phase/'active-phase.json',dict(identity=identity,phase=None,pid=None,token=None,stopped_utc=datetime.now(timezone.utc).isoformat()))
        if old is not None:save(phase/'phased-control-enabled.json',old)
        lock.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--evidence-dir',required=True);p.add_argument('--mode',choices=['sample','batch'],required=True);args=p.parse_args();main(args.evidence_dir,args.mode)
