"""Offline creation values for exactly 16 authorized source SOs."""
import runpy
from pathlib import Path
from collections import defaultdict
BASE=Path(__file__).parent;M=runpy.run_path(str(BASE/'inspect_pysb_so_remediation.py'));D=M['DEST'];OUT=M['OUT'];load=M['load'];save=M['save'];rid=M['rid']
def main():
    maps={m:{int(k):v for k,v in pairs.items()} for m,pairs in load(OUT/'resolved-master-evidence.json')['maps'].items()}
    repairs=load(D/'repair-plan.json')
    for model,pairs in repairs['maps'].items():maps.setdefault(model,{}).update({int(k):v for k,v in pairs.items()})
    proof=[];additions=defaultdict(dict)
    # Exact barcode/name plus the full exported template identity. Reject old
    # template links known to have been repurposed to a different product.
    sx=load(D/'missing-so-source-product-xids.json');tx=load(D/'missing-so-target-product-xids.json');candidates=load(D/'missing-so-product-candidates.json')
    for s in load(D/'source-supplement-products.json'):
        if s['id'] in maps['product.product']:continue
        names={x['name'] for x in sx if x['model']=='product.template' and x['res_id']==rid(s['product_tmpl_id'])}
        hits=[t for t in candidates if s.get('barcode') and t['barcode']==s['barcode'] and t['name']==s['name'] and any(x['model']=='product.template' and x['res_id']==rid(t['product_tmpl_id']) and x['name'] in names and x['module']=='v14_v2___export__' for x in tx)]
        if len(hits)==1:
            t=hits[0];maps['product.product'][s['id']]=t['id'];additions['product.product'][s['id']]=t['id'];proof.append(dict(model='product.product',source_id=s['id'],target_id=t['id'],evidence='complete_export_template_xmlid_exact_barcode_name',source=s,target=t))
    # Salesperson identity is unique login, active, company allowed.
    for s in load(D/'source-all-users.json'):
        hits=[t for t in load(D/'target-all-users.json') if t['login'].casefold()==s['login'].casefold() and t['active'] and 1 in t['company_ids']]
        if len(hits)==1:maps['res.users'][s['id']]=hits[0]['id'];additions['res.users'][s['id']]=hits[0]['id']
    for s in load(D/'source-all-pricelists.json'):
        hits=[t for t in load(D/'target-all-pricelists.json') if t['name']==s['name'] and rid(t['currency_id'])==maps['res.currency'].get(rid(s['currency_id'])) and rid(t['company_id'])==1 and t['active']]
        if len(hits)==1:maps.setdefault('product.pricelist',{})[s['id']]=hits[0]['id'];additions['product.pricelist'][s['id']]=hits[0]['id']
    sl={x['id']:x for x in load(D/'source-payment-term-lines.json')};tl={x['id']:x for x in load(D/'target-payment-term-lines.json')}
    for s in load(D/'source-all-payment-terms.json'):
        if len(s['line_ids'])!=1:continue
        source=sl[s['line_ids'][0]]
        if source['value']!='balance':continue
        hits=[]
        for t in load(D/'target-all-payment-terms.json'):
            if not t['active'] or len(t['line_ids'])!=1:continue
            line=tl[t['line_ids'][0]]
            if line['value']=='percent' and line['value_amount']==100 and line['delay_type']=='days_after' and line['nb_days']==source['days']:hits.append(t)
        if len(hits)==1:maps['account.payment.term'][s['id']]=hits[0]['id'];additions['account.payment.term'][s['id']]=hits[0]['id']
    for s in load(D/'source-routes.json'):
        hits=[t for t in load(D/'target-routes.json') if t['active'] and t['name']==s['name'] and rid(t['company_id']) in [False,1]]
        if len(hits)==1:maps.setdefault('stock.route',{})[s['id']]=hits[0]['id'];additions['stock.route'][s['id']]=hits[0]['id']
    missing={x['source_id'] for x in load(D/'classification.json') if x['classification']=='missing_target_order'}
    lines={x['id']:x for x in load(D/'source-line-extra.json')};orders=[]
    for s in load(D/'source-order-extra.json'):
        if s['id'] not in missing:continue
        errors=[]
        def mapped(model,v,field):
            sid=rid(v)
            if not sid:return False
            target=maps.get(model,{}).get(sid)
            if not target:errors.append(dict(field=field,model=model,source_id=sid))
            return target
        values=dict(company_id=1,date_order=s['date_order'],client_order_ref=s['client_order_ref'] or False,origin=s['origin'] or False,x_studio_v14_reference_studio=s['name'],note=s['note'] or False,attn=s.get('attn') or False)
        for field,model in [('partner_id','res.partner'),('partner_invoice_id','res.partner'),('partner_shipping_id','res.partner'),('warehouse_id','stock.warehouse'),('pricelist_id','product.pricelist'),('payment_term_id','account.payment.term'),('user_id','res.users')]:values[field]=mapped(model,s.get(field),field)
        commands=[];line_ids=[]
        for lid in s['order_line']:
            line=lines[lid];v=dict(name=line['name'],sequence=line['sequence'],display_type=line['display_type'] or False)
            if not line['display_type']:
                for field,model in [('product_id','product.product'),('product_uom','uom.uom')]:v['product_uom_id' if field=='product_uom' else field]=mapped(model,line.get(field),field)
                v.update(product_uom_qty=line['product_uom_qty'],price_unit=line['price_unit'],discount=line['discount'],base_price=line['base_price'],is_free=line['is_free'],purchase_price=line['purchase_price'],packing_ratio=line['packing_ratio'])
                if line['base_price']<=0 and not line['is_free'] and (line['product_uom_qty']==0 or line['price_unit']==0):v['is_free']=True
                v['tax_ids']=[(6,0,[mapped('account.tax',i,'tax_ids') for i in line.get('tax_id',[])])]
                route=mapped('stock.route',line.get('route_id'),'route_ids');v['route_ids']=[(6,0,[route] if route else [])]
            commands.append((0,0,v));line_ids.append(lid)
        values['order_line']=commands
        orders.append(dict(source_id=s['id'],source_name=s['name'],source=s,source_line_ids=line_ids,values=values,errors=errors))
    save(D/'missing-so-create-plan.json',dict(orders=orders,maps=additions,product_proof=proof,eligible=sum(not x['errors'] for x in orders),total=len(orders),read_only=True))
    print(dict(total=len(orders),eligible=sum(not x['errors'] for x in orders),errors=[dict(name=x['source_name'],errors=x['errors']) for x in orders if x['errors']]))
if __name__=='__main__':main()
