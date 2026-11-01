"""Restore historical price/name after verified native product recomputation."""
import runpy
import os
import uuid
import time
from pathlib import Path
BASE=Path(__file__).parent;M=runpy.run_path(str(BASE/'confirm_pysb_prod_so.py'));OUT=M['I']['OUT'];D=OUT/'so-remediation';load=M['load'];save=M['save'];rid=M['rid']
def main():
    jpath=D/'repairs-journal.json';j=load(jpath);e=j['actions']['line:193912'];identity=j['identity']
    if e['status']!='prepared' or e['action']['values']!={'product_id':130303}:raise RuntimeError('Not the known product recomputation')
    a=M['I']['ReadOnly']('v14-prod',('http://175.145.85.151','paoyeang_live'));b=M['I']['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    source=e['action']['source']
    if a.read('sale.order.line',[193912],list(source))[0]!=source:raise RuntimeError('Source changed')
    acquire=runpy.run_path(str(BASE/'production_write_lock.py'))['acquire']
    for attempt in range(50):
        try:lock=acquire(OUT);break
        except RuntimeError:
            if attempt==49:raise
            time.sleep(1)
    token=uuid.uuid4().hex
    try:
        log=M['P']['Log'](OUT/'phases',identity)
        if log.unresolved():raise RuntimeError('Other unresolved RPC')
        before=b.read('sale.order.line',[11842],list(e['before']))[0]
        order=b.read('sale.order',[4393],list(e['order_before']))[0]
        if rid(before['product_id'])!=130303 or before['price_unit']!=1 or order['state']!='draft' or order['picking_ids'] or order['invoice_ids']:raise RuntimeError('Live product recomputation differs; no write')
        values={f:e['before'][f] for f in ['name','price_unit','discount','product_uom_qty','base_price','purchase_price','packing_ratio','is_free']}
        save(OUT/'phases/phased-control-enabled.json',dict(identity=identity,supported_phases=['confirm-so']));save(OUT/'phases/active-phase.json',dict(identity=identity,phase='confirm-so',pid=os.getpid(),token=token))
        oid=identity['scope_hash']+':so-repair:line:193912:restore-commercial'
        log.append_intent(dict(operation_id=oid,phase='confirm-so',source_id=62120,model='sale.order.line',method='write',args=[[11842],values],before=before))
        try:result=M['W']['call'](b.r,'sale.order.line','write',[[11842],values],{'context':dict(pysb_phase_token=token,tz='UTC',tracking_disable=True,mail_notrack=True,mail_create_nolog=True,mail_create_nosubscribe=True,send_email=False)})
        except Exception:log.mark_uncertain(oid,'Commercial restore failed; readback required');raise
        log.append_result(oid,dict(returned=True,result=result))
        after=b.read('sale.order.line',[11842],list(e['before']))[0];final=b.read('sale.order',[4393],list(e['order_before']))[0]
        if rid(after['product_id'])!=130303 or any(after[f]!=e['before'][f] for f in e['before'] if f not in ['product_id']):raise RuntimeError('Commercial restore not exact')
        if any(final[f]!=e['order_before'][f] for f in ['amount_untaxed','amount_tax','amount_total','date_order','state','picking_ids','invoice_ids']):raise RuntimeError('Order totals not restored')
        save(D/'product-193912-commercial-recovery.json',dict(before=before,after=after,order_after=final,verified_utc=M['now']()))
        e.update(status='verified',after=after,verified_utc=M['now'](),recovery='product-193912-commercial-recovery.json');save(jpath,j)
        print(dict(price_restored=after['price_unit'],order_total=final['amount_total'],product_id=rid(after['product_id'])),flush=True)
    finally:
        save(OUT/'phases/active-phase.json',dict(phase=None,pid=None,token=None));save(OUT/'phases/phased-control-enabled.json',dict(identity=identity,supported_phases=[]));lock.close()
if __name__=='__main__':main()
