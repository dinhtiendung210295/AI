"""Offline discovery manifest; blocked items cannot be fed to write scripts."""
import json
import runpy
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
I = runpy.run_path(str(BASE / 'inspect_pysb_aug_oct_prod.py'))
OUT, save = I['OUT'], I['save']
S = runpy.run_path(str(BASE / 'scan_pysb_july_other_stock_coverage.py'))
rid = S['rid']
def load(name): return json.loads((OUT / name).read_text(encoding='utf8'))

def main():
    sx, tx = load('source-master-external-ids.json'), load('target-master-external-ids.json')
    maps, candidates = defaultdict(dict), defaultdict(set)
    target_xids = defaultdict(set)
    for x in tx:
        target_xids[x['model'], x['module'] + '.' + x['name']].add(x['res_id'])
        prefix = x['model'].replace('.', '_') + '_'
        if x['module'] in {'pysb_v14', 'product_delta_v14_paoyeang_live', 'product_review_v14_20261022'} and x['name'].startswith(prefix) and x['name'][len(prefix):].isdigit():
            candidates[x['model'], int(x['name'][len(prefix):])].add(x['res_id'])
    for x in sx:
        for prefix in ['', 'v14_', 'v14_v2_']:
            candidates[x['model'], x['res_id']].update(target_xids[x['model'], prefix + x['module'] + '.' + x['name']])
    for x in load('target-external-ids.json'):
        prefix = x['model'].replace('.', '_') + '_'
        if x['name'].startswith(prefix) and x['name'][len(prefix):].isdigit():
            candidates[x['model'], int(x['name'][len(prefix):])].add(x['res_id'])
    conflicts = []
    for (model, sid), ids in candidates.items():
        if len(ids) == 1: maps[model][sid] = next(iter(ids))
        elif len(ids) > 1: conflicts.append({'model': model, 'source_id': sid, 'targets': sorted(ids)})
    if (OUT / 'resolved-master-evidence.json').exists():
        resolved = load('resolved-master-evidence.json')
        rejected = {(x['model'],x['source_id'],x['rejected_target_id'],x['target_id']) for x in resolved['resolutions'] if 'rejected_target_id' in x}
        for model, pairs in resolved['maps'].items():
            for sid, tid in pairs.items():
                sid = int(sid)
                if sid in maps[model] and maps[model][sid] != tid:
                    if (model,sid,maps[model][sid],tid) in rejected: maps[model][sid] = tid
                    else: conflicts.append({'model':model,'source_id':sid,'targets':[maps[model][sid],tid]})
                else: maps[model][sid] = tid
    moves, lines = load('source-moves.json'), load('source-move-lines.json')
    locations = {x['id']: x for x in load('source-stock.location.json')}
    tl = load('target-stock.location.json')
    # Path plus usage uniquely identifies a warehouse location; never guess by
    # short display name or choose one of several production/inventory locations.
    for loc in locations.values():
        matches = [x['id'] for x in tl if x['complete_name'] == loc['complete_name'] and x['usage'] == loc['usage']]
        if loc['id'] not in maps['stock.location'] and len(matches) == 1:
            maps['stock.location'][loc['id']] = matches[0]
        if loc['id'] not in maps['stock.location'] and loc['usage'] in {'production', 'inventory'}:
            matches = [x['id'] for x in tl if x['name'] == loc['name'] and x['usage'] == loc['usage'] and rid(x['company_id']) == 1]
            if len(matches) == 1: maps['stock.location'][loc['id']] = matches[0]
    target_types = load('target-stock.picking.type.json')
    for typ in load('source-stock.picking.type.json'):
        matches = [t['id'] for t in target_types if t['name'] == typ['name'] and t['code'] == typ['code'] and rid(t['warehouse_id']) == maps['stock.warehouse'].get(rid(typ['warehouse_id']))]
        if typ['id'] not in maps['stock.picking.type'] and len(matches) == 1: maps['stock.picking.type'][typ['id']] = matches[0]
    lots_by_key = defaultdict(list)
    for lot in load('target-lots.json'):
        lots_by_key[rid(lot['company_id']), rid(lot['product_id']), lot['name']].append(lot['id'])
    lot_plan = []
    for lot in load('source-lots.json'):
        product = maps['product.product'].get(rid(lot['product_id']))
        matches = lots_by_key[1, product, lot['name']] if product else []
        status = 'existing' if len(matches) == 1 else 'create_candidate' if not matches and product else 'blocked'
        lot_plan.append({'source_id': lot['id'], 'product_id': product, 'name': lot['name'], 'status': status, 'target_ids': matches})
        if len(matches) == 1:
            known = maps['stock.lot'].get(lot['id'])
            if known and known != matches[0]:
                conflicts.append({'model': 'stock.lot', 'source_id': lot['id'], 'targets': [known, matches[0]]})
            else: maps['stock.lot'][lot['id']] = matches[0]
    bymove = defaultdict(list)
    for line in lines: bymove[rid(line['move_id'])].append(line)
    issues, results = [], []
    for move in moves:
        missing = []
        for field, model in [('product_id', 'product.product'), ('product_uom', 'uom.uom'), ('location_id', 'stock.location'), ('location_dest_id', 'stock.location')]:
            sid = rid(move[field])
            if not maps[model].get(sid): missing.append({'field': field, 'model': model, 'source_id': sid})
        for line in bymove[move['id']]:
            for field, model in [('owner_id', 'res.partner'), ('package_id', 'stock.package'), ('result_package_id', 'stock.package')]:
                if line.get(field) and not maps[model].get(rid(line[field])):
                    missing.append({'field': field, 'model': model, 'source_id': rid(line[field])})
        category = S['category'](move, locations)
        if category == 'unclassified': missing.append({'reason': 'unclassified_source_move'})
        row = {'source_move': move['id'], 'target_move': maps['stock.move'].get(move['id']), 'category': category, 'missing': missing,
               'status': 'requires_live_readback' if maps['stock.move'].get(move['id']) else 'blocked_mapping' if missing else 'requires_preparation_review'}
        results.append(row)
        issues.extend({'source_move': move['id'], **x} for x in missing)
    products = {x['id']: x for x in load('source-products.json')}
    missing_products = sorted({x['source_id'] for x in issues if x.get('model') == 'product.product'})
    summary = {'source_moves': len(moves), 'categories': dict(Counter(x['category'] for x in results)),
               'statuses': dict(Counter(x['status'] for x in results)), 'missing_models': dict(Counter(x.get('model', x.get('reason')) for x in issues)),
               'missing_products': len(missing_products), 'lot_plan': dict(Counter(x['status'] for x in lot_plan)), 'mapping_conflicts': len(conflicts)}
    save('discovery-manifest.json', {'discovery_only': True, 'write_ready': False, 'scope': load('scope.json'), 'target_database': 'py19-main-33843450',
        'maps': maps, 'mapping_conflicts': conflicts, 'moves': results, 'issues': issues, 'lot_plan': lot_plan,
        'missing_products': [products.get(i, {'id': i}) for i in missing_products], 'summary': summary})
    print(json.dumps(summary, ensure_ascii=False), flush=True)

if __name__ == '__main__': main()
