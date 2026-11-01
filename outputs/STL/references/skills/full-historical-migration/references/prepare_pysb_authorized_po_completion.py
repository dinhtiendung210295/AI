"""Read-only complete dependency capture for explicitly authorized missing PO."""
import argparse
import re
import runpy
from pathlib import Path
from datetime import datetime, timezone

BASE=Path(__file__).parent
P=runpy.run_path(str(BASE/'confirm_pysb_prod_orders.py'))
rid=P['rid'];load=P['load'];save=P['save']

def main(directory,concurrent_read=False):
    out=Path(directory).resolve();phase=out/'phases'
    lock=None if concurrent_read else runpy.run_path(str(BASE/'production_write_lock.py'))['acquire'](out)
    try:
        a=P['I']['ReadOnly']('v14-prod',('http://175.145.85.151','paoyeang_live'))
        b=P['I']['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
        old=load(phase/'po-exception-investigation.json')
        ids=[r['source_id'] for r in old['original_issues']]
        headers=a.read('purchase.order',ids,'name state company_id partner_id partner_ref currency_id payment_term_id picking_type_id user_id order_line date_order date_approve notes attn amount_untaxed amount_tax amount_total write_date'.split())
        lines=a.read('purchase.order.line',[i for h in headers for i in h['order_line']],'order_id sequence display_type product_id product_uom product_qty name date_planned price_unit discount taxes_id price_subtotal price_total write_date'.split())
        maps={m:{int(k):v for k,v in pairs.items()} for m,pairs in load(out/'resolved-master-evidence.json')['maps'].items()}
        products=a.read('product.product',{rid(l['product_id']) for l in lines if l.get('product_id')},['name','barcode','product_tmpl_id','uom_id','active'])
        partners=a.read('res.partner',{rid(h['partner_id']) for h in headers},['name','vat','company_id','parent_id'])
        target_partner_xml=b.scan('ir.model.data',[['model','=','res.partner'],['module','=','mig_paoyeang_live_20261021']],['name','res_id'])
        proofs=[]
        for s in partners:
            hits=[x for x in target_partner_xml if x['name']=='partner_'+str(s['id'])]
            if len(hits)==1:
                t=b.read('res.partner',[hits[0]['res_id']],['name','vat','company_id','parent_id'])[0]
                if s['name']==t['name'] and s['vat']==t['vat'] and rid(t['company_id']) in (False,1):
                    maps.setdefault('res.partner',{})[s['id']]=t['id'];proofs.append(dict(model='res.partner',source=s,target=t,xmlid=hits[0]))
        missing_products=[x for x in products if x['id'] not in maps.get('product.product',{})]
        if missing_products:
            xml=b.scan('ir.model.data',[['model','=','product.template'],['module','=','v14_v2___export__']],['name','res_id'])
            for s in missing_products:
                hits=[x for x in xml if x['name'].startswith('product_template_'+str(rid(s['product_tmpl_id']))+'_')]
                if len(hits)!=1:continue
                st=a.read('product.template',[rid(s['product_tmpl_id'])],['product_variant_ids'])[0]
                tt=b.read('product.template',[hits[0]['res_id']],['product_variant_ids'])[0]
                if st['product_variant_ids']!=[s['id']] or len(tt['product_variant_ids'])!=1:continue
                t=b.read('product.product',tt['product_variant_ids'],['name','barcode','product_tmpl_id','uom_id','active'])[0]
                if s['name']!=t['name'] or s['barcode']!=t['barcode']:continue
                maps.setdefault('product.product',{})[s['id']]=t['id'];proofs.append(dict(model='product.product',source=s,target=t,xmlid=hits[0],single_variant_both_sides=True))
        # SUPERLINK newly migrated contact may have another module: inspect all
        # XML IDs of its exact existing target, never infer identity from VAT.
        superlink=b.read('res.partner',[108668],['name','vat','company_id','parent_id'])[0]
        sx=b.scan('ir.model.data',[['model','=','res.partner'],['res_id','=',108668]],['module','name','res_id'])
        s=next(x for x in partners if x['id']==37948)
        if any(x['name']=='partner_37948' for x in sx) and s['name']==superlink['name'] and s['vat']==superlink['vat']:
            maps.setdefault('res.partner',{})[37948]=108668;proofs.append(dict(model='res.partner',source=s,target=superlink,xmlids=sx))
        established=load(P['I']['ROOT']/'outputs/po-aug-oct2026-20261024/superlink-confirmed-mapping.json')
        fields=['name','vat','email','phone','street','street2','city','zip','company_id']
        live_s=a.read('res.partner',[37948],fields)[0];live_t=b.read('res.partner',[108668],fields)[0]
        if established['source_id']==37948 and established['target_id']==108668 and all(live_s.get(f)==live_t.get(f)==established['source'].get(f) for f in fields):
            maps.setdefault('res.partner',{})[37948]=108668;proofs.append(dict(model='res.partner',source=live_s,target=live_t,basis=established['basis']))
        users=a.read('res.users',{rid(h['user_id']) for h in headers if h.get('user_id')},['name','login'])
        target_users=b.scan('res.users',[],['name','login','active'])
        for s in users:
            hits=[t for t in target_users if t['login']==s['login'] and t['active']]
            if len(hits)==1:maps.setdefault('res.users',{})[s['id']]=hits[0]['id'];proofs.append(dict(model='res.users',source=s,target=hits[0]))
        term_fields=['name','line_ids','early_discount','discount_percentage','discount_days']
        st=a.read('account.payment.term',{rid(h['payment_term_id']) for h in headers if h.get('payment_term_id')},term_fields)
        tt=b.scan('account.payment.term',[],term_fields+['active'])
        line_fields=['value','value_amount','days','nb_days','option','delay_type','days_after','day_of_the_month']
        slt=a.read('account.payment.term.line',[i for t in st for i in t['line_ids']],line_fields)
        tlt=b.read('account.payment.term.line',[i for t in tt for i in t['line_ids']],line_fields)
        for s in st:
            hits=[t for t in tt if t['name']==s['name'] and t.get('active')]
            if len(hits)==1:
                t=hits[0];proofs.append(dict(model='account.payment.term',source=s,target=t,source_lines=[x for x in slt if x['id'] in s['line_ids']],target_lines=[x for x in tlt if x['id'] in t['line_ids']],requires_schedule_review=True))
                source_lines=[x for x in slt if x['id'] in s['line_ids']];target_lines=[x for x in tlt if x['id'] in t['line_ids']]
                if len(source_lines)==len(target_lines)==1:
                    x,y=source_lines[0],target_lines[0]
                    if x['value']=='balance' and x['option']=='day_after_invoice_date' and not x.get('day_of_the_month') and y['value']=='percent' and y['value_amount']==100 and y['delay_type']=='days_after' and x['days']==y['nb_days'] and not t.get('early_discount'):
                        maps.setdefault('account.payment.term',{})[s['id']]=t['id'];proofs[-1]['requires_schedule_review']=False;proofs[-1]['schedule_equivalent']=True
        source_pick=a.read('stock.picking.type',[19],['code','company_id','default_location_src_id','default_location_dest_id'])[0]
        target_pick=b.read('stock.picking.type',[161],['code','company_id','default_location_src_id','default_location_dest_id'])[0]
        locations_a=a.read('stock.location',[rid(source_pick['default_location_src_id']),rid(source_pick['default_location_dest_id'])],['usage'])
        locations_b=b.read('stock.location',[rid(target_pick['default_location_src_id']),rid(target_pick['default_location_dest_id'])],['usage'])
        if [x['usage'] for x in locations_a]==['supplier','customer'] and [x['usage'] for x in locations_b]==['supplier','customer'] and target_pick['code']=='dropship' and rid(target_pick['company_id'])==1:
            maps.setdefault('stock.picking.type',{})[19]=161;proofs.append(dict(model='stock.picking.type',source=source_pick,target=target_pick,source_locations=locations_a,target_locations=locations_b))
        missing=[]
        for h in headers:
            for field,model in [('partner_id','res.partner'),('currency_id','res.currency'),('payment_term_id','account.payment.term'),('picking_type_id','stock.picking.type'),('user_id','res.users')]:
                sid=rid(h.get(field))
                if sid and sid not in maps.get(model,{}):missing.append(dict(order=h['id'],field=field,model=model,source_id=sid))
        for l in lines:
            if l.get('display_type'):continue
            for field,model in [('product_id','product.product'),('product_uom','uom.uom')]:
                sid=rid(l.get(field))
                if sid not in maps.get(model,{}):missing.append(dict(line=l['id'],field=field,model=model,source_id=sid))
            for tax in l['taxes_id']:
                if tax not in maps.get('account.tax',{}):missing.append(dict(line=l['id'],field='taxes_id',source_id=tax))
        result=dict(captured_utc=datetime.now(timezone.utc).isoformat(),source_headers=headers,source_lines=lines,source_products=products,identity_proofs=proofs,maps=maps,unresolved_dependencies=missing,superlink_xmlids=sx,erp_mutations=0)
        result.update(source_users=users,target_users=target_users,source_terms=st,target_terms=tt,source_term_lines=slt,target_term_lines=tlt)
        save(phase/'authorized-po-completion-plan.json',result)
        print(__import__('json').dumps(dict(orders=len(headers),lines=len(lines),identity_proofs=len(proofs),unresolved_dependencies=missing,superlink_xmlids=sx)),flush=True)
    finally:
        if lock:lock.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--evidence-dir',required=True);p.add_argument('--concurrent-read',action='store_true');args=p.parse_args();main(args.evidence_dir,args.concurrent_read)
