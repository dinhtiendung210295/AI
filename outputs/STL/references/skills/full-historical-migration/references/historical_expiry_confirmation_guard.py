"""Only operator-authorized expiry confirmation for frozen, unconsumed MO history."""
def rid(value):return value[0] if isinstance(value,(list,tuple)) and value else value or False


def authorize(approval,scope_hash,source,mo,moves,warning,raw_lots):
    if approval.get('scope_sha256')!=scope_hash or approval.get('company_id')!=1 or approval.get('target_database')!='py19-main-33843450' or source['id'] not in approval.get('approved_source_mos',[]):raise RuntimeError('Expiry confirmation outside operator scope')
    if source['state']!='done' or rid(source['company_id'])!=1 or rid(mo['company_id'])!=1:raise RuntimeError('Expiry confirmation requires original done company1 history')
    if mo['state'] not in ['confirmed','progress','to_close'] or mo['qty_produced'] or any(x['state'] in ['done','cancel'] for x in moves):raise RuntimeError('Expiry confirmation cannot repeat consumption')
    context=warning.get('context',{})
    if warning.get('res_model')!='expiry.picking.confirmation' or context.get('default_production_ids')!=[mo['id']] or context.get('button_validate_picking_ids') or context.get('default_picking_ids') or context.get('default_workorder_id'):raise RuntimeError('Unexpected expiry wizard scope')
    commands=context.get('default_lot_ids',[])
    if len(commands)!=1 or commands[0][:2]!=[6,0]:raise RuntimeError('Unexpected expiry lot commands')
    lots=commands[0][2]
    if not lots or not set(lots)<=set(raw_lots):raise RuntimeError('Expiry wizard lot not in exact raw details')
    return lots
