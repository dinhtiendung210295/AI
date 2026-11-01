"""Per-unit company balances with exact, captured approved-rounding lineage."""
from collections import defaultdict
from pathlib import Path
import runpy
ALIAS=runpy.run_path(str(Path(__file__).with_name('same_factor_unit_alias.py')))
from decimal import Decimal, ROUND_HALF_UP


def rid(value):return value[0] if isinstance(value,(list,tuple)) and value else value or False


def same_quantity(a,b,precision):
    if not precision or precision<=0:return False
    step=Decimal(str(precision))
    return (Decimal(str(a))/step).quantize(Decimal('1'),rounding=ROUND_HALF_UP)==(Decimal(str(b))/step).quantize(Decimal('1'),rounding=ROUND_HALF_UP)


def compare(a,b,maps,rounding_records,blocked_source_units=()):
    ap={x['id']:x for x in a['products']};bp={x['id']:x for x in b['products']}
    au={x['id']:x for x in a['units']};bu={x['id']:x for x in b['units']}
    al={x['id']:x for x in a['done_lines']};bl={x['id']:x for x in b['done_lines']}
    precision={};proven_source_products=set();aliases=[]
    for sid,product in ap.items():
        tp=maps.get('product.product',{}).get(str(sid));base=rid(product['uom_id']);mapped=maps.get('uom.uom',{}).get(str(base))
        if tp not in bp or base in blocked_source_units or base not in au or not mapped:continue
        native=rid(bp[tp]['uom_id'])
        if mapped!=native:
            try:proof=ALIAS['prove'](mapped,native,bu)
            except ValueError:continue
            aliases.append({'source_product':sid,'target_product':tp,'source_base_unit':base,'proof':proof})
        proven_source_products.add(sid);precision[tp]=min(precision.get(tp,au[base]['rounding']),au[base]['rounding'])
    approved=[]
    for source_line,record in rounding_records.items():
        target_line=maps.get('stock.move.line',{}).get(str(source_line))
        if source_line not in al or target_line not in bl:continue
        s=al[source_line];t=bl[target_line]
        original=record.get('source_qty',record.get('source_quantity'));actual=record.get('target_qty',record.get('target_quantity'))
        unit=maps.get('uom.uom',{}).get(str(rid(s['product_uom_id'])))
        if original!=s['qty_done'] or actual!=t['quantity'] or unit!=record['target_unit'] or rid(t['product_uom_id'])!=unit or s['date']!=t['date']:raise RuntimeError('Captured company rounding lineage mismatch')
        if s.get('move_date',s['date'])!=t.get('move_date',t['date']):raise RuntimeError('Captured company rounding move date mismatch')
        want=float((Decimal(str(original))/Decimal(str(bu[unit]['rounding']))).quantize(Decimal('1'),rounding=ROUND_HALF_UP)*Decimal(str(bu[unit]['rounding'])))
        if want!=actual:raise RuntimeError('Company rounding differs from approved unit precision')
        dimensions=[('product.product','product_id'),('stock.location','location_id'),('stock.location','location_dest_id'),('stock.lot','lot_id'),('stock.package','package_id'),('stock.package','result_package_id'),('res.partner','owner_id')]
        if any((maps.get(model,{}).get(str(rid(s[field]))) if s[field] else False)!=rid(t[field]) for model,field in dimensions):raise RuntimeError('Captured company rounding dimensions differ')
        pid=rid(s['product_id']);tp=rid(t['product_id'])
        if tp not in precision or pid not in proven_source_products:continue
        amount=(actual-original)*au[rid(ap[pid]['uom_id'])]['factor']/au[rid(s['product_uom_id'])]['factor']
        for location,package,sign in [('location_id','package_id',-1),('location_dest_id','result_package_id',1)]:
            key=(tp,rid(t[location]),rid(t['lot_id']),rid(t[package]),rid(t['owner_id']))
            approved.append({'source_line':source_line,'target_line':target_line,'date':s.get('move_date',s['date']),'target_key':key,'delta':sign*amount,'record':record})
    reports={}
    for cutoff,source_rows in a['balances'].items():
        source=defaultdict(float);missing=[]
        for row in source_rows:
            key=[];errors=[]
            for model,sid in zip(['product.product','stock.location','stock.lot','stock.package','res.partner'],row['key']):
                tid=maps.get(model,{}).get(str(sid)) if sid else False
                if sid and not tid:errors.append({'model':model,'source_id':sid})
                key.append(tid)
            if key[0] and row['key'][0] not in proven_source_products:errors.append({'reason':'base_unit_equivalence_or_precision_not_proven','source_product':row['key'][0],'target_product':key[0]})
            if errors:missing.append(dict(row,errors=errors))
            else:source[tuple(key)]+=row['quantity']
        target={tuple(x['key']):x['quantity'] for x in b['balances'][cutoff]};rows=[]
        for key in sorted(set(source)|set(target)):
            sv=source.get(key,0);tv=target.get(key,0);sr=precision.get(key[0]);tr=bu[rid(bp[key[0]]['uom_id'])]['rounding'];step=min(sr,tr) if sr and tr else None
            differences=[x for x in approved if x['date']<cutoff and x['target_key']==key]
            delta=sum(x['delta'] for x in differences)
            matched=same_quantity(sv,tv,step)
            accepted=bool(not matched and differences and same_quantity(sv+delta,tv,step))
            rows.append({'target_key':list(key),'source_mapped_quantity':sv,'target':tv,'delta_against_mapped_source':tv-sv,'source_unit_precision':sr,'target_unit_precision':tr,'comparison_precision':step,
                         'matched':matched,'approved_exception':accepted,'approved_rounding_delta':delta,'remaining_delta_after_approved':tv-sv-delta,'approved_rounding_lines':differences})
        reports[cutoff]={'rows':rows,'missing_source_keys':missing,'base_unit_alias_proofs':aliases,'summary':{'keys':len(rows),'matched':sum(x['matched'] for x in rows),'approved_exceptions':sum(x['approved_exception'] for x in rows),'different':sum(not x['matched'] and not x['approved_exception'] for x in rows),'unmapped_source_keys':len(missing)}}
    return reports
