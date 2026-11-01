"""Create only the 16 authorized missing SO drafts; no automatic confirmation."""
import argparse
import hashlib
import json
import os
import runpy
import uuid
from pathlib import Path
BASE=Path(__file__).parent;M=runpy.run_path(str(BASE/'confirm_pysb_prod_so.py'));OUT=M['I']['OUT'];D=OUT/'so-remediation';load=M['load'];save=M['save'];rid=M['rid']

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');parser.add_argument('--all',action='store_true');args=parser.parse_args()
    plan=load(D/'missing-so-create-plan.json');identity,_=M['C']['validate_context'](OUT)
    if not args.apply:print(json.dumps(dict(total=plan['total'],eligible=plan['eligible'])));return
    if not load(OUT/'phases/operator-so-remediation-approval.json').get('add_missing_16_orders'):raise RuntimeError('Missing SO creation not authorized')
    a=M['I']['ReadOnly']('v14-prod',('http://175.145.85.151','paoyeang_live'));b=M['I']['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    schema=b.call('sale.order','fields_get',[],{'attributes':['type']})
    if 'x_studio_v14_reference_studio' not in schema:raise RuntimeError('Historical reference field missing')
    jpath=D/'missing-so-journal.json';j=load(jpath) if jpath.exists() else dict(identity=identity,orders={})
    log=M['P']['Log'](OUT/'phases',identity);hashcode=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();sample=D/'missing-so-sample.json'
    if args.all and (not sample.exists() or load(sample).get('code_hash')!=hashcode or not load(sample).get('passed')):raise RuntimeError('Creation sample required')
    maps={model:{int(k):v for k,v in pairs.items()} for model,pairs in load(OUT/'resolved-master-evidence.json')['maps'].items()}
    for overlay in [load(D/'repair-plan.json')['maps'],plan['maps']]:
        for model,pairs in overlay.items():maps.setdefault(model,{}).update({int(k):v for k,v in pairs.items()})
    source_orders={x['id']:x for x in load(D/'source-orders.json')};source_lines={x['id']:x for x in load(D/'source-lines.json')}
    su={x['id']:x for x in load(OUT/'source-uom.uom.json')};tu={x['id']:x for x in load(OUT/'target-uom.uom.json')}
    for x in load(D/'missing-so-extra-units.json'):tu[x['id']]=x
    completed=0
    for row in plan['orders']:
        sid=row['source_id'];key=str(sid)
        if key in j['orders']:
            if j['orders'][key]['status']!='verified_draft':raise RuntimeError('Interrupted draft creation; readback required')
            continue
        if row['errors']:continue
        try:lock=runpy.run_path(str(BASE/'production_write_lock.py'))['acquire'](OUT)
        except RuntimeError:print('Another writer active; no draft creation sent',flush=True);break
        token=uuid.uuid4().hex
        try:
            log.events=log.replay()
            if log.unresolved():raise RuntimeError('Another mutation requires readback')
            source=row['source']
            if a.read('sale.order',[sid],list(source))[0]!=source:raise RuntimeError('Source changed before create')
            sl=[source_lines[i] for i in row['source_line_ids']]
            if {x['id']:x for x in a.read('sale.order.line',row['source_line_ids'],list(sl[0]))}!={x['id']:x for x in sl}:raise RuntimeError('Source line changed before create')
            existing=b.scan('sale.order',['|',['x_studio_v14_reference_studio','=',row['source_name']],['name','=',row['source_name']]],['name','state','company_id'])
            existingx=b.scan('ir.model.data',[['module','=','pysb_v14'],['name','=','sale_order_'+str(sid)]],['res_id','model'])
            if existing or existingx:raise RuntimeError('Possible existing SO; do not create duplicate')
            pids=[cmd[2]['product_id'] for cmd in row['values']['order_line'] if cmd[2].get('product_id')]
            products=b.read('product.product',pids,['active','company_id'])
            if any(not x['active'] or rid(x['company_id']) not in [False,1] for x in products):raise RuntimeError('Archived or wrong-company product')
            counters={m:b.call(m,'search_count',[[['company_id','=',1]]]) for m in ['stock.picking','purchase.order','mrp.production','account.move']}
            save(OUT/'phases/phased-control-enabled.json',dict(identity=identity,supported_phases=['confirm-so']))
            save(OUT/'phases/active-phase.json',dict(identity=identity,phase='confirm-so',pid=os.getpid(),token=token))
            def mutate(model,method,args,label):
                oid=identity['scope_hash']+':so-supplement:'+str(sid)+':'+label
                log.append_intent(dict(operation_id=oid,phase='confirm-so',source_id=sid,model=model,method=method,args=args))
                try:result=M['W']['call'](b.r,model,method,args,{'context':dict(pysb_phase_token=token,tz='UTC',tracking_disable=True,mail_notrack=True,mail_create_nolog=True,mail_create_nosubscribe=True,mail_auto_subscribe_no_notify=True,send_email=False)})
                except Exception:log.mark_uncertain(oid,'Draft creation RPC failed; readback required');raise
                log.append_result(oid,dict(returned=True,result=result));return result
            j['orders'][key]=dict(source_name=row['source_name'],status='prepared',values=row['values']);save(jpath,j)
            tid=mutate('sale.order','create',[row['values']],'create')
            j['orders'][key].update(target_id=tid,status='created_pending_verification');save(jpath,j)
            target=b.read('sale.order',[tid],list(source_orders[sid])+['x_studio_v14_reference_studio'])[0]
            tf=list(load(OUT/'phases/target-sale.order.line.json')[0]);tl=b.read('sale.order.line',target['order_line'],tf)
            if target['state']!='draft' or target['picking_ids'] or target['invoice_ids'] or len(target['order_line'])!=len(sl):raise RuntimeError('Created SO is not an isolated complete draft')
            pairs={s['id']:t['id'] for s,t in zip(sl,tl)}
            if len(pairs)!=len(sl):raise RuntimeError('SO line mapping not unique')
            local={m:dict(v) for m,v in maps.items()};local.setdefault('sale.order.line',{}).update(pairs)
            currency=a.read('res.currency',[rid(source_orders[sid]['currency_id'])],['rounding'])[0]
            comparison=M['R']['compare_order']('sale.order',source_orders[sid],target,sl,tl,local,su,tu,{currency['id']:currency['rounding']},'9999')
            if comparison['issues']:raise RuntimeError('Draft commercial readback failed: '+json.dumps(comparison['issues']))
            xids=[dict(module='pysb_v14',name='sale_order_'+str(sid),model='sale.order',res_id=tid,noupdate=True)]
            xids += [dict(module='pysb_v14',name='sale_order_line_'+str(s),model='sale.order.line',res_id=t,noupdate=True) for s,t in pairs.items()]
            mutate('ir.model.data','create',[xids],'external_ids')
            for model,count in counters.items():
                if b.call(model,'search_count',[[['company_id','=',1]]])!=count:raise RuntimeError('Draft create had unexpected workflow side effects')
            j['orders'][key].update(status='verified_draft',target=target,line_map=pairs,comparison=comparison,verified_utc=M['now']());save(jpath,j)
            print(json.dumps(dict(source_name=row['source_name'],created_target=tid,lines=len(pairs),state='draft')),flush=True)
            completed+=1
            if not args.all:save(sample,dict(passed=True,code_hash=hashcode,source_id=sid,target_id=tid))
        finally:
            save(OUT/'phases/active-phase.json',dict(phase=None,pid=None,token=None,stopped_utc=M['now']()));save(OUT/'phases/phased-control-enabled.json',dict(identity=identity,supported_phases=[]));lock.close()
        if not args.all:break
    if all(j['orders'].get(str(x['source_id']),{}).get('status')=='verified_draft' for x in plan['orders']):
        overlay=load(D/'applied-overlay.json')
        for model,pairs in plan['maps'].items():overlay['maps'].setdefault(model,{}).update(pairs)
        for sid,entry in j['orders'].items():
            overlay['maps'].setdefault('sale.order',{})[sid]=entry['target_id'];overlay['maps'].setdefault('sale.order.line',{}).update(entry['line_map'])
            extra={x['id']:x for x in load(D/'source-line-extra.json')}
            for source_lid,target_lid in entry['line_map'].items():overlay['source_line_route_map'][str(target_lid)]=rid(extra[int(source_lid)].get('route_id'))
        save(D/'applied-overlay.json',overlay)
    print(json.dumps(dict(completed_this_run=completed,total_verified=sum(x['status']=='verified_draft' for x in j['orders'].values()))),flush=True)
if __name__=='__main__':main()
