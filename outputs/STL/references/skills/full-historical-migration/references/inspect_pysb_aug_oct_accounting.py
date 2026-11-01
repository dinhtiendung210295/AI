"""Read-only accounting configuration and invoice identity evidence."""
import json
import runpy
import socket
from pathlib import Path

BASE = Path(__file__).resolve().parent
I = runpy.run_path(str(BASE / 'inspect_pysb_aug_oct_prod.py'))
OUT, save, ReadOnly = I['OUT'], I['save'], I['ReadOnly']
def rid(v): return v[0] if isinstance(v,list) and v else v or False
def load(n): return json.loads((OUT/n).read_text(encoding='utf8'))

def main():
    socket.setdefaulttimeout(120)
    a = ReadOnly('v14-prod', ('http://175.145.85.151', 'paoyeang_live'))
    b = ReadOnly('v19-prod', ('https://py19.odoo.com', 'py19-main-33843450'))
    lines, invoices = load('source-invoice-lines.json'), load('source-invoices.json')
    for label, r in [('source',a),('target',b)]:
        accounts = r.read('account.account',[rid(x['account_id']) for x in lines], 'code name internal_type internal_group user_type_id account_type reconcile currency_id company_id company_ids deprecated active'.split()) if label=='source' else r.scan('account.account',[['company_ids','in',[1]]], 'code name account_type internal_group reconcile currency_id company_ids active deprecated'.split())
        save(label+'-accounts.json',accounts)
        save(label+'-taxes.json',r.scan('account.tax',[['company_id','=',1]],'name amount amount_type type_tax_use price_include price_include_override include_base_amount is_base_affected company_id active children_tax_ids'.split()))
        save(label+'-users.json',r.scan('res.users',[],['login','name','active','company_ids']))
        if label=='source':
            contacts=r.read('res.partner',[rid(x['partner_id']) for x in invoices], 'name company_id active parent_id company_name commercial_partner_id vat email'.split())
        else:
            d=load('discovery-manifest.json');mp=d['maps'].get('res.partner',{})
            contacts=r.read('res.partner',[mp[str(rid(x['partner_id']))] for x in invoices if str(rid(x['partner_id'])) in mp], 'name company_id active parent_id company_name commercial_partner_id vat email'.split())
            save('target-existing-invoices.json',r.scan('account.move',[['company_id','=',1],['move_type','in',['out_invoice','out_refund','in_invoice','in_refund']]],'name ref state move_type invoice_date date partner_id currency_id amount_total amount_total_signed invoice_user_id invoice_line_ids reversed_entry_id x_studio_v14_refererce write_date'.split()))
            save('target-account-move-schema.json',r.call('account.move','fields_get',[],{'attributes':['type','store','readonly']}))
        save(label+'-invoice-contacts.json',contacts)
        print(label,'accounting evidence saved',flush=True)

if __name__=='__main__':main()
