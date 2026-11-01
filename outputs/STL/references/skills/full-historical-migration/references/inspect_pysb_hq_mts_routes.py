"""Capture current route evidence only; never confirms a sales order."""
import json
import runpy
from pathlib import Path
BASE=Path(__file__).parent
I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'))
if __name__=='__main__':
    r=I['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    proof=runpy.run_path(str(BASE/'hq_mts_delivery_proof.py'))['inspect'](r)
    I['save']('hq-mts-delivery-route-proof.json',proof)
    print(json.dumps({'ready':proof['ready'],'errors':proof['errors']}),flush=True)
