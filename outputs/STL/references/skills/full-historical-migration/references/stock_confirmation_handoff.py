"""Consume reviewed SO handoff identities without changing master data or UoMs."""
import json

MODELS=('res.partner','stock.warehouse','product.product','sale.order','sale.order.line')

def apply(maps,directory):
    path=directory/'phases/so-confirmation-handoff.json'
    if not path.exists():return maps
    handoff=json.loads(path.read_text(encoding='utf8'))
    gate=json.loads((directory/'phases/confirm-so-gate.json').read_text(encoding='utf8'))
    identity=handoff['identity']
    if identity.get('target_database')!='py19-main-33843450' or identity.get('source_database')!='paoyeang_live' or identity.get('company_id')!=1 or any(gate.get(k)!=v for k,v in identity.items()):raise RuntimeError('Stock handoff identity mismatch')
    if gate['status'] not in ['fully_passed','closed_with_holds'] or not gate['live_verification_complete']:raise RuntimeError('SO handoff not verified')
    for model in MODELS:
        dest=maps.setdefault(model,{})
        for sid,tid in handoff['maps'].get(model,{}).items():
            key=int(sid) if dest and isinstance(next(iter(dest)),int) else str(sid)
            if key in dest and dest[key]!=tid:raise RuntimeError('Stock handoff mapping conflicts with existing evidence')
            dest[key]=tid
    return maps
