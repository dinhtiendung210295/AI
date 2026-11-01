"""Offline evidence-backed corrections; never writes production."""
import runpy
from pathlib import Path
from collections import defaultdict,Counter
import re
BASE=Path(__file__).parent
M=runpy.run_path(str(BASE/'inspect_pysb_so_remediation.py'))
D=M['DEST'];OUT=M['OUT'];load=M['load'];save=M['save'];rid=M['rid']
def index(name):return {x['id']:x for x in load(D/(name+'.json'))}

def main():
    source=index('source-orders');target=index('target-orders');sp=index('source-partners');tp=index('target-partners-complete')
    sx=load(D/'source-partner-xids.json');tx=load(D/'target-partner-xids-complete.json')
    if (D/'target-unresolved-contact-candidates.json').exists():tp.update({x['id']:x for x in load(D/'target-unresolved-contact-candidates.json')})
    if (D/'target-unresolved-contact-xids.json').exists():tx+=load(D/'target-unresolved-contact-xids.json')
    maps={m:{int(k):v for k,v in pairs.items()} for m,pairs in load(OUT/'resolved-master-evidence.json')['maps'].items()}
    additions=defaultdict(dict);proof=[];holds=[];actions=[]
    # Full exported names plus the explicit contact-migration namespace.
    for sid,s in sp.items():
        names={x['name'] for x in sx if x['res_id']==sid}
        hits={x['res_id'] for x in tx if (x['module']=='v14_v2___export__' and x['name'] in names) or (x['module']=='mig_paoyeang_live_20261021' and x['name']=='partner_'+str(sid))}
        if len(hits)==1:
            tid=next(iter(hits));t=tp[tid]
            if not t['active']:continue
            # Identity follows the complete provenance; display names can be cleaned.
            additions['res.partner'][sid]=tid
            proof.append(dict(model='res.partner',source_id=sid,target_id=tid,evidence='full_source_export_xmlid_or_explicit_contact_migration_xmlid',source=s,target=t))
    maps['res.partner'].update(additions['res.partner'])
    def norm(v):return ' '.join(str(v or '').casefold().split())
    def phone(v):
        digits=re.sub(r'\D','',v or '')
        return '0'+digits[2:] if digits.startswith('60') else digits
    for sid in [37740,37893,37947]:
        s=sp[sid];parent=maps['res.partner'].get(rid(s.get('parent_id')))
        matches=[]
        for t in tp.values():
            if not t['active'] or norm(t['name'])!=norm(s['name']) or t['type']!=s['type']:continue
            if not s.get('email') or norm(t['email'])!=norm(s['email']) or phone(t['phone'])!=phone(s['phone']):continue
            if any(norm(s.get(f))!=norm(t.get(f)) for f in ['street','street2','city','zip']):continue
            if rid(s.get('parent_id')):
                ancestry=set();node=rid(t.get('parent_id'))
                while node and node not in ancestry:
                    ancestry.add(node);node=rid(tp.get(node,{}).get('parent_id'))
                if parent not in ancestry and parent!=t['id']:continue
            if not s.get('parent_id') and t.get('parent_id'):continue
            matches.append(t)
        if len(matches)==1:
            t=matches[0];additions['res.partner'][sid]=t['id'];maps['res.partner'][sid]=t['id']
            proof.append(dict(model='res.partner',source_id=sid,target_id=t['id'],evidence='unique_exact_name_type_email_normalized_phone_full_address_and_verified_parent; no_VAT_only_match',source=s,target=t))
    sw=index('source-warehouses');tw=index('target-warehouses')
    for sid,s in sw.items():
        hits=[t for t in tw.values() if (t['name'],t['code'],rid(t['company_id']),t['delivery_steps'])==(s['name'],s['code'],rid(s['company_id']),s['delivery_steps'])]
        if len(hits)==1:
            additions['stock.warehouse'][sid]=hits[0]['id'];proof.append(dict(model='stock.warehouse',source_id=sid,target_id=hits[0]['id'],evidence='unique_exact_name_code_company_delivery_steps',source=s,target=hits[0]))
    maps['stock.warehouse'].update(additions['stock.warehouse'])
    # S-RACE has full exported template identity, exact barcode/name/base unit.
    ps=index('source-suspect-products');pt=index('target-suspect-products')
    s=ps[43967];t=pt[116777]
    if s['name']!=t['name'] or s['barcode']!=t['barcode'] or maps['uom.uom'].get(rid(s['uom_id']))!=rid(t['uom_id']):raise RuntimeError('S-RACE identity drift')
    additions['product.product'][43967]=116777
    proof.append(dict(model='product.product',source_id=43967,target_id=116777,evidence='export_template_56617_00681842_plus_exact_barcode_name_base_unit',source=s,target=t))
    # PC is the base unit of the exact same cut-piece SKU in both versions.
    # This is a product-specific identity; never claim the malformed length
    # conversion factor in v14 equals the v19 Units conversion.
    su=load(D/'source-unit-1087.json')[0];tu=load(D/'target-unit-470.json')[0]
    pp=next(x for x in load(D/'source-supplement-products.json') if x['id']==46577)
    qq=next(x for x in load(D/'target-supplement-products.json') if x['id']==116401)
    if pp['barcode']!=qq['barcode'] or pp['name']!=qq['name'] or rid(pp['uom_id'])!=1087 or rid(qq['uom_id'])!=470:raise RuntimeError('Cut-piece unit proof missing')
    additions['uom.uom'][1087]=470
    proof.append(dict(model='uom.uom',source_id=1087,target_id=470,source_product_id=46577,target_product_id=116401,evidence='exact_same_SKU_barcode_and_description_12x15cm_cut_piece_base_unit_PC; preserve_piece_count_no_length_conversion',source_unit=su,target_unit=tu,conversion_factor_exception=True))
    changed_source_ids=[]
    source_lines=load(D/'source-lines.json')
    rows=load(D/'classification.json')
    for row in rows:
        sid=row['source_id'];tid=row['target_id']
        if not tid:continue
        values={};unresolved=[]
        for issue in row['issues']:
            if issue['reason']=='header_identity_mismatch':
                field=issue['field'];model='stock.warehouse' if field=='warehouse_id' else 'res.partner';expected=maps[model].get(issue['source'])
                if expected is None:unresolved.append(issue);continue
                if rid(target[tid].get(field))!=expected:values[field]=expected
            if issue['reason']=='source_header_written_after_snapshot':changed_source_ids.append(sid)
        if values:
            actions.append(dict(key='order:'+str(sid),source_id=sid,target_id=tid,model='sale.order',values=values,before={k:target[tid][k] for k in values},source=source[sid],source_lines=[x for x in source_lines if rid(x['order_id'])==sid],reason='restore_source_order_partner_and_addresses_using_verified_existing_contacts'))
        if unresolved:holds.append(dict(source_id=sid,name=row['source_name'],unresolved=unresolved))
    sl=index('source-line-extra');tl=index('target-line-extra');inv={v:k for k,v in maps['sale.order.line'].items()}
    for row in rows:
        if not row['target_id']:continue
        for lid in target[row['target_id']]['order_line']:
            t=tl[lid];s=sl[inv[lid]]
            values={};reason=[]
            if row['source_name']=='SO-53906' and rid(s['product_id'])==46485:
                values['product_id']=130303
                # Native product changes recompute stored name and price. Make
                # historical commercial values explicit in the same write.
                values.update({f:t[f] for f in ['name','price_unit','discount','purchase_price','base_price','packing_ratio','is_free','product_uom_qty']})
                reason.append('source_serial_specific_used_PD1900_not_regular_machine')
            if ('zero_base_price_not_free' in row['workflow_issues'] or rid(s.get('product_id'))==46577) and not t.get('display_type') and t.get('product_id') and t.get('base_price',0)<=0 and not t.get('is_free'):
                if s.get('base_price',0)>0:
                    values['base_price']=s['base_price'];reason.append('restore_source_base_price')
                elif s['price_unit']==0 or s['product_uom_qty']==0:
                    # Operator explicitly delegated these exceptions. No fake
                    # positive base price; mark the historical zero-value line.
                    values['is_free']=True;reason.append('approved_historical_zero_value_or_zero_quantity_exception')
            if values:actions.append(dict(key='line:'+str(s['id']),source_id=row['source_id'],source_line_id=s['id'],target_id=lid,model='sale.order.line',values=values,before={k:t[k] for k in values},source=s,reason=reason))
    save(D/'repair-plan.json',dict(maps=additions,identity_proof=proof,actions=actions,holds=holds,reviewed_source_header_timestamp_ids=changed_source_ids,read_only=True,counts=dict(actions=len(actions),orders=sum(x['model']=='sale.order' for x in actions),lines=sum(x['model']=='sale.order.line' for x in actions),unresolved_orders=len(holds))))
    print(dict(actions=len(actions),models=dict(Counter(x['model'] for x in actions)),unresolved_orders=len(holds),new_contact_mappings=len(additions['res.partner'])))

if __name__=='__main__':main()
