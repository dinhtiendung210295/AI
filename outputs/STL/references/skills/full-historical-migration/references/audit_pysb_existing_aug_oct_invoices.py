"""Read-only financial/identity audit of pre-existing mapped invoices.

Mapping errors are retained separately; money match never certifies full lines.
"""
import json
import runpy
import sys
from pathlib import Path
BASE=Path(__file__).resolve().parent;sys.path.insert(0,str(BASE))
from historical_invoice_checks import validation_errors
I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'))
def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False

def main():
    manifest=json.loads((I['OUT']/'independent-invoice-manifest.json').read_text(encoding='utf8'))
    docs=[x for x in manifest['documents'] if x['target_existing']]
    r=I['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    fields='name state company_id move_type partner_id currency_id invoice_date date amount_untaxed amount_tax amount_total amount_total_signed invoice_currency_rate x_foreign_to_company_rate invoice_user_id invoice_line_ids x_studio_v14_refererce'.split()
    target={x['id']:x for x in r.read('account.move',[x['target_existing'] for x in docs],fields)}
    lines={x['id']:x for x in r.read('account.move.line',[i for x in target.values() for i in x['invoice_line_ids']],['balance','amount_currency'])}
    rows=[]
    for d in docs:
        t=target[d['target_existing']];errors=validation_errors(d,t,lines)
        for f in ['company_id','move_type','partner_id','currency_id','invoice_date','date','x_studio_v14_refererce']:
            have=rid(t[f]) if f.endswith('_id') else t[f]
            if have!=d['header'][f]:errors.append({'field':f,'source_expected':d['header'][f],'target':have})
        if t['state']!='posted':errors.append({'field':'state','target':t['state']})
        if len(t['invoice_line_ids'])!=len(d['lines']):errors.append({'field':'invoice_line_count'})
        rows.append({'source_id':d['source_id'],'source_name':d['source_name'],'target_id':t['id'],'target_name':t['name'],'financial_identity_errors':errors,'mapping_preflight_errors':d['errors'],'full_line_acceptance':False})
    result={'read_only':True,'rows':rows,'summary':{'existing_documents':len(rows),'financial_identity_matched':sum(not x['financial_identity_errors'] for x in rows),'financial_identity_mismatched':sum(bool(x['financial_identity_errors']) for x in rows),'with_mapping_holds':sum(bool(x['mapping_preflight_errors']) for x in rows)},'limitation':'Financial/identity check only; no changes to previously posted records; mapping holds require separate line/link audit'}
    I['save']('existing-invoice-financial-audit.json',result);print(json.dumps(result['summary']),flush=True)

if __name__=='__main__':main()
