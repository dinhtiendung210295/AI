"""Fail-closed recovery gate before preparing an already-created, unpicked MO."""
def guard(mo, moves, lines, operations, expected):
    if mo['state'] not in ['confirmed','progress','to_close'] or mo['qty_produced']:
        raise RuntimeError('Recovery MO already consumed, draft, done or cancelled')
    if any(x['state'] in ['done','cancel'] or x.get('picked') for x in moves+lines):
        raise RuntimeError('Recovery stock already picked, done or cancelled')
    if not moves or not mo['move_raw_ids'] or not mo['move_finished_ids']:
        raise RuntimeError('Recovery missing native moves')
    if any(x['model']=='mrp.production' and x['method']=='button_mark_done' and x['args']==[[mo['id']]] for x in operations):
        raise RuntimeError('Prior mark-done attempt requires different read-back recovery')
    for field,value in expected.items():
        actual=mo[field]
        if isinstance(actual,(list,tuple)):actual=actual[0] if actual else False
        if isinstance(value,float):
            if abs(actual-value)>1e-8:raise RuntimeError('Recovery header drift: '+field)
        elif actual!=value:raise RuntimeError('Recovery header drift: '+field)
