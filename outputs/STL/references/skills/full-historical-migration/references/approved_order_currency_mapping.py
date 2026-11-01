"""Reuse the approved CNH -> CNY migration choice; never changes currencies."""
import copy


def apply(maps, source_rows, target_rows):
    result = copy.deepcopy(maps)
    source = [x for x in source_rows if x['name'] == 'CNH']
    target = [x for x in target_rows if x['name'] == 'CNY']
    if not source:
        return result, []
    if len(source) != 1 or len(target) != 1:
        raise RuntimeError('Approved CNH/CNY mapping is not unique')
    s, t = source[0], target[0]
    if s.get('rounding') != t.get('rounding') or not s.get('rounding'):
        raise RuntimeError('CNH/CNY monetary precision differs')
    previous = result.setdefault('res.currency', {}).get(s['id'])
    result['res.currency'][s['id']] = t['id']
    proof = dict(source_currency=s, target_currency=t, previous_exact_name_target=previous,
                 decision='Existing historical migration choice CNH -> CNY',
                 basis='full-historical-migration/SKILL.md and prepare_pysb_independent_invoices.py',
                 master_mutations=0, rate_mutations=0)
    return result, [proof]
