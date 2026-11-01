"""Exact target-unit alias proof, without quantity conversion or master edits."""
def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False
def prove(mapped,native,units):
    if mapped==native:return None
    def chain(uid):
        rows=[];seen=set()
        while uid:
            if uid in seen or uid not in units:raise ValueError('Missing or cyclic target unit root')
            seen.add(uid);row=units[uid]
            rows.append({key:row.get(key) for key in ['id','factor','rounding','relative_factor','relative_uom_id']})
            uid=rid(row.get('relative_uom_id'))
        return rows
    left=chain(mapped);right=chain(native)
    if left[-1]['id']!=right[-1]['id']:raise ValueError('Different unit dimensions')
    if not left[0]['factor'] or left[0]['factor']!=right[0]['factor']:raise ValueError('Unit quantities are not identical')
    if not left[0]['rounding'] or left[0]['rounding']!=right[0]['rounding']:raise ValueError('Different target unit precision')
    return {'mapped_target_unit':mapped,'native_target_unit':native,'root_unit':left[-1]['id'],'factor':left[0]['factor'],'rounding':left[0]['rounding'],'mapped_chain':left,'native_chain':right,'quantity_conversion':1}
def check(proof,mapped,native,units):
    expected=prove(mapped,native,units)
    if not expected or expected!=proof:raise ValueError('Target unit alias proof changed')
    return expected
