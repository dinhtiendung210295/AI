"""Read-only delivery communication/automation gates; no secrets/code in output."""
import hashlib
import json
import re
import runpy
from pathlib import Path
I=runpy.run_path(str(Path(__file__).with_name('inspect_pysb_aug_oct_prod.py')))

def inspect(r):
    company=r.read('res.company',[1],['stock_move_email_validation','stock_text_confirmation','stock_confirmation_type'])[0]
    automations=r.scan('base.automation',[['active','=',True],['model_id.model','in',['sale.order','stock.picking','purchase.order','mrp.production']]],['name','model_id','trigger','action_server_ids','filter_domain','filter_pre_domain'])
    actions=r.read('ir.actions.server',[i for x in automations for i in x['action_server_ids']],['name','state','model_id','code','child_ids'])
    report=[]
    for x in actions:
        code=x.get('code') or ''
        digest=hashlib.sha256(code.encode()).hexdigest()
        related=[a for a in automations if x['id'] in a['action_server_ids']]
        reviewed_draft_reset=(digest=='9b12b63db8137128a73dbf556b617077e50afbef756725159c5d2dd50013d492' and related and all(a['trigger']=='on_state_set' and a['filter_domain']=="[('state', '=', 'draft')]" and a['filter_pre_domain']=="[('state', '!=', 'draft')]" for a in related))
        report.append({k:v for k,v in x.items() if k!='code'}|{'code_sha256':digest,'reviewed_draft_reset_not_triggered_by_confirmation':bool(reviewed_draft_reset),'communication_risk':bool(re.search(r'send_mail|send_email|send_whatsapp|message_post|requests\.|urlopen|send_to_shipper',code,re.I))})
    result={'company':company,'automations':automations,'actions':report,'delivery_communications_disabled':not company.get('stock_move_email_validation') and not company.get('stock_text_confirmation'),
        'automations_need_review':any((x['state']!='object_write' and not x['reviewed_draft_reset_not_triggered_by_confirmation']) or x['communication_risk'] for x in report)}
    return result

def main():
    r=I['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    result=inspect(r)
    I['save']('stock-automation-preflight.json',result);print(json.dumps(result),flush=True)

if __name__=='__main__':main()
