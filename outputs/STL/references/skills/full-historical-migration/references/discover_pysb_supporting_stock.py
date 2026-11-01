"""Read all unresolved July flows and complete documents; discovery never authorizes replay."""
import json
from collections import defaultdict
from scan_pysb_july_other_stock_coverage import (
    MOVE_FIELDS, LINE_FIELDS, START, END, COMPANY, rid, load, save,
    cli_args, run_scan, mapping_evidence, category)


def discover(a, coverage, maps):
    if coverage.get('schema_version') != 2 or not coverage.get('scan_complete'):
        raise RuntimeError('A complete exhaustive move scan is required')
    pending = {m['id']: m for m in coverage['pending_moves']}
    moves, picks, mos = dict(pending), {}, {}
    queue, visited = set(pending), set()
    # Expand entire documents and their direct move dependencies. Related records
    # outside the month are evidence only, not permission to replay them.
    while queue:
        current = a.read('stock.move', sorted(queue-visited), MOVE_FIELDS)
        visited.update(m['id'] for m in current)
        following = set()
        for m in current:
            if rid(m.get('company_id')) != COMPANY:
                raise RuntimeError('Cross-company source dependency')
            moves[m['id']] = m
            pid = rid(m.get('picking_id'))
            if pid and pid not in picks:
                p = a.read('stock.picking', [pid],
                           'name origin date_done scheduled_date state company_id picking_type_id location_id location_dest_id move_lines'.split())[0]
                picks[pid] = p
                following.update(p['move_lines'])
            moid = rid(m.get('production_id')) or rid(m.get('raw_material_production_id'))
            if moid and moid not in mos:
                mo = a.read('mrp.production', [moid],
                            'name state company_id date_finished move_raw_ids move_finished_ids'.split())[0]
                mos[moid] = mo
                following.update(mo.get('move_raw_ids', []) + mo.get('move_finished_ids', []))
            # Traverse dependencies, not unrelated same-product operations.
            following.update(m.get('move_orig_ids', []) + m.get('move_dest_ids', []))
            if m.get('origin_returned_move_id'):
                following.add(rid(m['origin_returned_move_id']))
        queue = following-visited
    lines = a.read('stock.move.line', [i for m in moves.values() for i in m['move_line_ids']], LINE_FIELDS)
    locs = {x['id']: x for x in a.read('stock.location',
             [rid(m[f]) for m in moves.values() for f in ['location_id', 'location_dest_id']],
             ['usage', 'complete_name'])}
    groups = defaultdict(list)
    in_period = {m['id'] for m in coverage['source_moves']}
    dependency_ids = sorted(set(moves)-set(pending))
    for m in moves.values():
        groups[category(m, locs)].append(m['id'])
    missing = defaultdict(set)
    for model, field in [('product.product', 'product_id'), ('uom.uom', 'product_uom_id'),
                         ('stock.location', 'location_id'), ('stock.location', 'location_dest_id'),
                         ('stock.lot', 'lot_id'), ('stock.package', 'package_id'),
                         ('stock.package', 'result_package_id'), ('res.partner', 'owner_id')]:
        absent = {rid(x.get(field)) for x in lines if x.get(field)} - set(maps.get(model, {}))
        missing[model].update(absent)
    mo_ids = set(groups['mo_raw']) | set(groups['mo_finished'])
    return {'schema_version': 2, 'read_only': True, 'discovery_only': True,
            'execution_authorized': False, 'scope': coverage['scope'],
            'all_moves': list(moves.values()),
            'moves': [m for m in moves.values() if m['id'] not in mo_ids],
            'mo_moves': [m for m in moves.values() if m['id'] in mo_ids],
            'pickings': list(picks.values()), 'mos': list(mos.values()), 'lines': lines,
            'groups': dict(groups), 'unresolved_source_move_ids': sorted(pending),
            'dependency_move_ids': dependency_ids,
            'out_of_period_or_not_done_move_ids': sorted(m['id'] for m in moves.values()
                  if m.get('state') != 'done' or not START <= m['date'] < END),
            'already_in_period_move_ids': sorted(set(dependency_ids) & in_period),
            'missing': {k: sorted(v) for k, v in missing.items() if v},
            'routing': {'mo_raw': 'MO review; do not replay as receipt',
                        'mo_finished': 'MO review; preserve raw/finished pair',
                        'scrap': 'native Scrap review', 'unbuild': 'Unbuild review',
                        'production_independent': 'Unbuild/production review',
                        'unclassified': 'manual classification; blocks acceptance'},
            'unresolved_results': [r for r in coverage['results'] if r['status'] == 'unresolved']}


def main():
    args = cli_args(__doc__)
    a, _, coverage = run_scan(args.evidence_dir, args.output_dir)
    maps, _ = mapping_evidence(load(args.evidence_dir/'execution-manifest.json'),
                               load(args.evidence_dir/'execution-journal.json'))
    report = discover(a, coverage, maps)
    save(args.output_dir/'supporting-stock-discovery.json', report)
    print(json.dumps({'output_dir': str(args.output_dir), 'all_moves': len(report['all_moves']),
                      'pending': len(report['unresolved_source_move_ids']),
                      'groups': {k: len(v) for k, v in report['groups'].items()},
                      'missing': report['missing']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
