"""Read-only MO execution dependencies; never creates or completes an MO."""
import runpy
from pathlib import Path
I=runpy.run_path(str(Path(__file__).with_name('inspect_pysb_aug_oct_prod.py')))
import json

def main():
    rows=json.loads((I['OUT']/'source-mos.json').read_text(encoding='utf8'))
    r=I['ReadOnly']('v14-prod',('http://175.145.85.151','paoyeang_live'))
    fields='name state company_id product_id product_qty qty_produced product_uom_id date_planned_start date_finished move_raw_ids move_finished_ids lot_producing_id picking_type_id location_src_id location_dest_id write_date origin x_studio_reference_no'.split()
    extra=r.read('mrp.production',[x['id'] for x in rows],fields)
    if len(extra)!=len(rows):raise RuntimeError('Incomplete MO dependency snapshot')
    frozen={x['id']:x for x in rows}
    for x in extra:
        for field,value in frozen[x['id']].items():
            if field in x and x[field]!=value:raise RuntimeError('Frozen source MO changed: '+str(x['id']))
    I['save']('source-mo-execution-details.json',extra)
    print('Source MO execution details:',len(extra),flush=True)

if __name__=='__main__':main()
