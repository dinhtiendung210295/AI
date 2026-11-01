"""Offline MO header and move checks. Never uses delivered/invoiced for MO."""
from order_quantity_checks import quantity_check, rid

def compare_mos(source, target, source_moves, target_moves, maps, units, move_coverage):
    ti={x['id']:x for x in target};sm={x['id']:x for x in source_moves};tm={x['id']:x for x in target_moves}
    rows=[]
    for s in source:
        tid=maps.get('mrp.production',{}).get(s['id']);t=ti.get(tid)
        row={'source_id':s['id'],'target_id':tid,'name':s['name'],'issues':[],'metrics':{},'moves':[]};rows.append(row)
        if t is None:
            row['issues'].append('missing_target_mo_or_mapping');row['match']=False;continue
        for field in ['state','date_finished']:
            if s.get(field)!=t.get(field):row['issues'].append('different:'+field)
        source_start=s.get('date_start') or s.get('date_planned_start')
        if source_start and t.get('date_start')!=source_start:row['issues'].append('different:date_start')
        if t.get('state')!='done':row['issues'].append('target_not_done')
        if rid(t.get('company_id'))!=1:row['issues'].append('wrong_company')
        for model,field in [('product.product','product_id'),('uom.uom','product_uom_id')]:
            if not maps.get(model,{}).get(rid(s.get(field))) or maps[model][rid(s[field])]!=rid(t.get(field)):
                row['issues'].append('different_or_unmapped:'+field)
        rounding=units.get(rid(s.get('product_uom_id')),{}).get('rounding')
        for label,field in [('planned','product_qty'),('produced','qty_produced')]:
            row['metrics'][label]=quantity_check(s.get(field),t.get(field),rounding)
        mapped_target_moves=set()
        for key,role in [('move_raw_ids','consumption'),('move_finished_ids','finished_or_byproduct')]:
            for sid in s[key]:
                move=sm.get(sid)
                if move is not None and move['state']=='cancel':continue
                mtid=maps.get('stock.move',{}).get(sid);actual=tm.get(mtid)
                item={'source_move':sid,'target_move':mtid,'role':role,'issues':[],'metrics':{}}
                row['moves'].append(item)
                if move is None or actual is None:
                    item['issues'].append('missing_move_or_mapping');item['match']=False;continue
                mapped_target_moves.add(mtid)
                if mtid not in t[key]:item['issues'].append('wrong_mo_or_move_role')
                uom_rounding=units.get(rid(move.get('product_uom')),{}).get('rounding')
                item['metrics']['demand']=quantity_check(move.get('product_uom_qty'),actual.get('product_uom_qty'),uom_rounding)
                item['metrics']['done']=quantity_check(move.get('quantity_done'),actual.get('quantity'),uom_rounding)
                if move_coverage.get(sid)!='verified':item['issues'].append('move_dimensions_or_state_not_verified')
                item['match']=not item['issues'] and all(x['match'] for x in item['metrics'].values())
        extras={i for key in ['move_raw_ids','move_finished_ids'] for i in t[key] if tm.get(i,{}).get('state')!='cancel'}-mapped_target_moves
        if extras:row['issues'].append('extra_target_moves:'+','.join(map(str,sorted(extras))))
        row['match']=not row['issues'] and all(x['match'] for x in row['metrics'].values()) and all(x['match'] for x in row['moves'])
    return {'rows':rows,'summary':{'source_mos':len(source),'matched':sum(x['match'] for x in rows),'mismatched':sum(not x['match'] for x in rows)}}
