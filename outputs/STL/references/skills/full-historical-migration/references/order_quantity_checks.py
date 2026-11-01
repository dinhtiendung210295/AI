"""Offline order-line reconciliation, retaining missing mappings and services."""
from decimal import Decimal, ROUND_HALF_UP
from collections import Counter
from pathlib import Path
import runpy
ALIAS=runpy.run_path(str(Path(__file__).with_name('same_factor_unit_alias.py')))

def rid(value):return value[0] if isinstance(value,(list,tuple)) and value else value or False

def quantity_check(source,target,rounding):
    result={'source':source,'target':target,'delta':target-source if source is not None and target is not None else None,'rounding':rounding,'match':False}
    if source is None or target is None:result['reason']='missing_quantity_field';return result
    if not rounding or rounding<=0:result['reason']='invalid_uom_rounding';return result
    step=Decimal(str(rounding));rounded=lambda x:(Decimal(str(x))/step).quantize(Decimal('1'),rounding=ROUND_HALF_UP)
    result['match']=rounded(source)==rounded(target);return result

def compare_lines(model,source,target,maps,source_uoms,target_uoms):
    if model not in {'sale.order.line','purchase.order.line'}:raise ValueError('Unsupported order line model')
    index={x['id']:x for x in target};mapping=maps.get(model,{});use=Counter(mapping.get(x['id']) for x in source if mapping.get(x['id']))
    products=maps.get('product.product',{});units=maps.get('uom.uom',{})
    metrics=(('ordered','product_uom_qty'),('delivered','qty_delivered'),('invoiced','qty_invoiced')) if model=='sale.order.line' else (('ordered','product_qty'),('received','qty_received'),('invoiced','qty_invoiced'))
    rows=[]
    for s in source:
        tid=mapping.get(s['id']);t=index.get(tid);business=s.get('display_type') not in {'line_note','line_section'}
        product=rid(s.get('product_id'));su=rid(s.get('product_uom_id') or s.get('product_uom'));tu=rid(t.get('product_uom_id') or t.get('product_uom')) if t else None
        sr=source_uoms.get(su,{}).get('rounding');tr=target_uoms.get(tu,{}).get('rounding');step=min(sr,tr) if sr and tr and sr>0 and tr>0 else None
        product_match=bool(t and product and products.get(product) and products[product]==rid(t.get('product_id')))
        unit_match=bool(t and units.get(su) and units[su]==tu)
        unit_alias=None
        if t and units.get(su) and tu and not unit_match:
            try:unit_alias=ALIAS['prove'](units[su],tu,target_uoms);unit_match=bool(unit_alias)
            except ValueError:pass
        identity={'product':{'source':product,'target':rid(t.get('product_id')) if t else None,'expected_target':products.get(product),'delta':None,'applicable':business,'match':product_match if business else True},
                  'unit':{'source':su,'target':tu,'expected_target':units.get(su),'delta':None,'applicable':business,'match':unit_match if business else True,'same_factor_alias_proof':unit_alias}}
        row={'source_line':s['id'],'target_line':tid,'order':s.get('order_id'),'issues':[],'identity':identity,'metrics':{},'quantity_applicable':business,'unit_precision':{'source':sr,'target':tr,'comparison':step,'different':sr!=tr}}
        rows.append(row)
        if business:
            for label,field in metrics:
                metric=quantity_check(s.get(field),t.get(field) if t else None,step)
                if t and metric['source'] is not None and metric['target'] is not None and (not product_match or not unit_match):
                    metric.update(raw_numeric_delta=metric['delta'],delta=None,match=False,reason='product_identity_unverified' if not product_match else 'unit_identity_unverified')
                row['metrics'][label]=metric
        if t is None:
            row['issues'].append('missing_target_line_or_mapping');row['match']=False;continue
        if use[tid]>1:row['issues'].append('target_line_shared_by_sources')
        if s.get('order_id'):
            order_model='sale.order' if model=='sale.order.line' else 'purchase.order';expected=maps.get(order_model,{}).get(rid(s['order_id']))
            identity['order']={'source':rid(s['order_id']),'target':rid(t.get('order_id')),'expected_target':expected,'delta':None,'match':bool(expected and expected==rid(t.get('order_id')))}
            if not identity['order']['match']:row['issues'].append('order_mapping_mismatch')
        if s.get('display_type')!=t.get('display_type'):row['issues'].append('display_type_mismatch')
        if not business:row['match']=not row['issues'];continue
        if not product_match:row['issues'].append('product_mapping_mismatch')
        if not unit_match:row['issues'].append('uom_mapping_mismatch')
        if step is None:row['issues'].append('unverified_uom_precision')
        row['match']=not row['issues'] and all(x['match'] for x in row['metrics'].values())
    business_rows=[x for x in rows if x['quantity_applicable']]
    summary={'source_lines':len(source),'matched':sum(x['match'] for x in rows),'mismatched':sum(not x['match'] for x in rows),'business_lines':len(business_rows),'matched_business_lines':sum(x['match'] for x in business_rows),'metric_results':{label:{'matched':sum(x['metrics'][label]['match'] for x in business_rows),'unmatched':sum(not x['metrics'][label]['match'] for x in business_rows),'missing_target_value':sum(x['metrics'][label]['target'] is None for x in business_rows)} for label,field in metrics}}
    return {'model':model,'rows':rows,'summary':summary}
