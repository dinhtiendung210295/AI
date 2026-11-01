"""Read-only diagnosis of native receipt matching holds; no automatic release."""
import json
import runpy
from pathlib import Path

M=runpy.run_path(str(Path(__file__).with_name('migrate_pysb_independent_receipts.py')))

def main():
    r=M['Run']();rid=M['rid'];rows=[]
    for sid,state in r.j['groups'].items():
        if not state.get('execution_hold'):continue
        native=r.target_chain(state['target_order'])
        smid=int(state['error'].rsplit(':',1)[1]) if state.get('error','').startswith('Ambiguous generated source move match:') else None
        source=r.sm.get(smid)
        candidates=[]
        if source:
            for t in native:
                if rid(t['product_id'])!=r.maps['product.product'][rid(source['product_id'])]:continue
                equivalent=M['equivalent_demand'](rid(t['product_uom']),t['product_uom_qty'],r.maps['uom.uom'][rid(source['product_uom'])],source['product_uom_qty'],r.tu)
                candidates.append({'target':t,'equivalent_base_quantity':equivalent,
                    'same_locations':all(rid(t[f])==r.maps['stock.location'][rid(source[f])] for f in ['location_id','location_dest_id']),
                    'same_po_line':rid(t['purchase_line_id'])==r.maps['purchase.order.line'].get(rid(source['purchase_line_id']))})
        rows.append({'source_po':int(sid),'name':state['source_name'],'error':state['error'],'source_move':source,'candidates':candidates,'native_moves':native})
    M['save']('receipt-execution-holds-readback.json',rows)
    print(json.dumps([{'source_po':x['source_po'],'name':x['name'],'error':x['error'],'equivalent_candidates':sum(c['equivalent_base_quantity'] and c['same_locations'] and c['same_po_line'] for c in x['candidates'])} for x in rows]),flush=True)

if __name__=='__main__':main()
