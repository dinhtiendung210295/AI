"""Incident-only readback of operation 19092; never writes ERP or repeats RPC."""
import argparse,json,runpy
from pathlib import Path
from datetime import datetime,timezone
BASE=Path(__file__).parent
I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'));OUT=I['OUT']
def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False

def main(apply=False):
    path=OUT/'independent-delivery-journal.json';j=json.loads(path.read_text(encoding='utf8'));idx=19092
    op=j['operations'][idx];state=j['groups']['64436']
    if op['status']!='uncertain' or op['model']!='stock.picking' or op['method']!='write' or op['args']!=[[6213],{'location_id':5,'location_dest_id':9}]:raise RuntimeError('Incident no longer matches; never rerun recovery')
    if [(i,x['status']) for i,x in enumerate(j['operations']) if x['status'] in ['intent','uncertain']]!=[(idx,'uncertain')]:raise RuntimeError('Additional unresolved operations')
    if state['phase']!='native_chain_matched' or state.get('completed_pickings'):raise RuntimeError('Incident chain phase changed')
    mids=set(state['move_pairs'].values());pids=set(state['picking_pairs'].values())
    if 6213 not in pids or any(x['model']=='stock.picking' and x['method']=='button_validate' and set(x['args'][0])&pids for x in j['operations']):raise RuntimeError('Prior validation attempt needs different recovery')
    b=I['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    picks=b.read('stock.picking',sorted(pids),['state','company_id','location_id','location_dest_id','move_ids'])
    moves=b.read('stock.move',sorted(mids),['state','company_id','quantity','picked','move_line_ids','picking_id','location_id','location_dest_id','move_orig_ids','move_dest_ids'])
    order=b.read('sale.order',[state['target_order']],['state','company_id','picking_ids'])[0]
    native_picks=b.read('stock.picking',order['picking_ids'],['move_ids'])
    if rid(order['company_id'])!=1 or order['state'] not in ['sale','done'] or {mid for p in native_picks for mid in p['move_ids']}!=mids:raise RuntimeError('Native SO chain differs from mapping')
    if {p['id'] for p in picks}!=pids or {m for p in picks for m in p['move_ids']}!=mids or any(p['state'] in ['done','cancel'] or rid(p['company_id'])!=1 for p in picks):raise RuntimeError('Picking state changed')
    if {m['id'] for m in moves}!=mids or any(m['state'] in ['done','cancel'] or rid(m['company_id'])!=1 or m['picked'] or rid(m['picking_id']) not in pids or (set(m['move_orig_ids'])|set(m['move_dest_ids']))-mids for m in moves):raise RuntimeError('Chain has execution or external changes')
    lineids=[lid for m in moves for lid in m['move_line_ids']]
    lines=b.read('stock.move.line',lineids,['state','picked','move_id','company_id','quantity','location_id','location_dest_id','owner_id','package_id','result_package_id']) if lineids else []
    byid={m['id']:m for m in moves}
    if {x['id'] for x in lines}!=set(lineids) or any(x['state'] in ['done','cancel'] or x['picked'] or rid(x['company_id'])!=1 or rid(x['move_id']) not in mids or x['quantity']<0 or x['owner_id'] or x['package_id'] or x['result_package_id'] or any(rid(x[f])!=rid(byid[rid(x['move_id'])][f]) for f in ['location_id','location_dest_id']) for x in lines):raise RuntimeError('Reserved lines are not isolated unpicked native reservations')
    if any(abs(m['quantity']-sum(x['quantity'] for x in lines if rid(x['move_id'])==m['id']))>1e-8 for m in moves):raise RuntimeError('Native reservation quantity differs from details')
    target=next(p for p in picks if p['id']==6213)
    if any(rid(target[f])!=v for f,v in op['args'][1].items()):raise RuntimeError('Requested postcondition not proven; do not retry')
    proof=dict(status='requested_postcondition_verified',operation_index=idx,pickings=picks,moves=moves,reservations=lines,order=order,erp_mutations=0,write_repeated=False,readback_utc=datetime.now(timezone.utc).isoformat())
    I['save']('phases/picking-location-503-operation-19092-readback.json',proof)
    if apply:
        fresh=json.loads(path.read_text(encoding='utf8'))
        if fresh!=j:raise RuntimeError('Journal changed during recovery')
        op.update(status='recovered_by_readback',recovery_proof='phases/picking-location-503-operation-19092-readback.json',recovery_result='Requested location values observed; isolated unpicked chain with native reservations only; RPC execution itself not assumed')
        I['save']('independent-delivery-journal.json',j)
    print(json.dumps(dict(status=proof['status'],local_journal_reconciled=apply,erp_mutations=0,write_repeated=False)),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--apply-proof',action='store_true');a=p.parse_args();main(a.apply_proof)
