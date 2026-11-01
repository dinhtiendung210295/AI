"""Refresh PO snapshots after authorized gap repairs, keep frozen source scope."""
import argparse
from collections import defaultdict,Counter
from pathlib import Path
import runpy
from datetime import datetime, timezone

BASE=Path(__file__).parent
P=runpy.run_path(str(BASE/'confirm_pysb_prod_orders.py'))
C=runpy.run_path(str(BASE/'run_pysb_phased_migration.py'))

def main(directory):
    out=Path(directory).resolve();phase=out/'phases'
    lock=runpy.run_path(str(BASE/'production_write_lock.py'))['acquire'](out)
    try:
        identity,readiness=C['validate_context'](out)
        runner=P['ConfirmPO'](out,identity,readiness)
        source_ids=[r['source_id'] for r in readiness['models']['purchase.order']['rows']]
        target_ids=[runner.maps['purchase.order'][sid] for sid in source_ids if sid in runner.maps.get('purchase.order',{})]
        sf=list(next(iter(runner.source.values())));tf=list(next(iter(runner.target.values())))
        source=runner.a.read('purchase.order',source_ids,sf);target=runner.b.read('purchase.order',target_ids,tf)
        sl=runner.a.read('purchase.order.line',[i for h in source for i in h['order_line']],list(next(iter(runner.sl.values()))))
        tl=runner.b.read('purchase.order.line',[i for h in target for i in h['order_line']],list(next(iter(runner.tl.values()))))
        sg,tg=defaultdict(list),defaultdict(list)
        for x in sl:sg[P['rid'](x['order_id'])].append(x)
        for x in tl:tg[P['rid'](x['order_id'])].append(x)
        su={x['id']:x for x in runner.a.read('uom.uom',{P['rid'](x.get('product_uom')) for x in sl if x.get('product_uom')},['rounding'])}
        tu={x['id']:x for x in runner.b.read('uom.uom',{P['rid'](x.get('product_uom_id')) for x in tl if x.get('product_uom_id')},['rounding'])}
        currency={x['id']:x['rounding'] for x in runner.a.read('res.currency',{P['rid'](h['currency_id']) for h in source},['rounding'])}
        ti={x['id']:x for x in target};old={x['source_id']:x for x in readiness['models']['purchase.order']['rows']};rows=[]
        scope=P['load'](out/'scope.json')
        for s in source:
            tid=runner.maps.get('purchase.order',{}).get(s['id']);t=ti.get(tid)
            row=dict(source_id=s['id'],source_name=s['name'],target_id=tid,target_name=t['name'] if t else None,source_state=s['state'],target_state=t['state'] if t else None,date_order=s['date_order'],origins=old[s['id']]['origins'])
            row.update(P['R']['compare_order']('purchase.order',s,t,sg[s['id']],tg[tid],runner.maps,su,tu,currency,scope['end_utc_exclusive']));rows.append(row)
        for reader,headers in [(runner.a,source),(runner.b,target)]:
            baseline={x['id']:x for x in headers}
            check=reader.read('purchase.order',list(baseline),['write_date'])
            if any(x['write_date']!=baseline[x['id']]['write_date'] for x in check):raise RuntimeError('PO changed during refresh')
        history=phase/'history'/('before-po-readiness-refresh-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));history.mkdir(parents=True)
        for name in ['phase-readiness.json','source-purchase.order.json','target-purchase.order.json','source-purchase.order.line.json','target-purchase.order.line.json']:
            P['save'](history/name,P['load'](phase/name))
        for name,data in [('source-purchase.order.json',source),('target-purchase.order.json',target),('source-purchase.order.line.json',sl),('target-purchase.order.line.json',tl)]:P['save'](phase/name,data)
        summary=dict(Counter(x['classification'] for x in rows));readiness['models']['purchase.order'].update(rows=rows,summary=summary,source_lines=len(sl),target_lines=len(tl))
        readiness['po_refreshed_utc']=datetime.now(timezone.utc).isoformat()
        readiness['po_mapping_update_note']='Frozen source IDs unchanged; target identifiers expanded by explicit Bruce authorization, see authorized-po-gaps-journal.json. Original phase-scope mapping entries remain historical baseline.'
        P['save'](phase/'phase-readiness.json',readiness)
        print(__import__('json').dumps(dict(orders=len(rows),classification=summary)),flush=True)
    finally:lock.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--evidence-dir',required=True);main(p.parse_args().evidence_dir)
