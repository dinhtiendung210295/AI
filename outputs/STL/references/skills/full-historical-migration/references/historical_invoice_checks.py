"""Pure FX, salesperson and contact checks shared by historical invoice tools."""
from decimal import Decimal, ROUND_HALF_UP
import math
import re

VERSION = 1
READ_FIELDS = ['amount_total_signed', 'invoice_currency_rate', 'invoice_user_id']
CONTACT_FIELDS = ['name', 'company_id', 'active', 'parent_id', 'company_name', 'commercial_partner_id']

def rid(value):
    return value[0] if isinstance(value, (tuple, list)) and value else value or False

def rounded(value, unit):
    unit = Decimal(str(unit))
    return (Decimal(str(value)) / unit).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * unit

def equal_money(a, b, unit):
    return rounded(a, unit) == rounded(b, unit)

def rate_lines(move, lines):
    # v14 stock price-difference entries may add offsetting foreign cents with
    # zero company balance outside invoice_line_ids. They do not define invoice FX.
    ancillary = [l for l in lines if 'invoice_line_ids' in move and l['id'] not in move['invoice_line_ids'] and not l['balance'] and l['amount_currency']]
    totals = {}
    for line in ancillary:
        cid = rid(line['currency_id'])
        totals[cid] = totals.get(cid, Decimal('0')) + Decimal(str(line['amount_currency']))
    excluded = {l['id'] for l in ancillary if totals[rid(l['currency_id'])] == 0}
    return [l for l in lines if l.get('id') not in excluded], sorted(excluded)

def historical_rate(move, lines, company_currency_id, company_rounding=0.01, fallback=None):
    """Find one rate reproducing ALL source journal balances; never edit global rates."""
    if rid(move['currency_id']) == company_currency_id:
        return 1.0
    pairs = []
    considered, _ = rate_lines(move, lines)
    for line in considered:
        amount, balance = float(line['amount_currency']), float(line['balance'])
        if not math.isfinite(amount) or not math.isfinite(balance):
            raise ValueError('non_finite_source_amount')
        if rid(line['currency_id']) != rid(move['currency_id']) and (amount or balance):
            raise ValueError('mixed_line_currencies_require_review')
        if amount or balance:
            pairs.append((amount, balance))
    candidates = [move.get('invoice_currency_rate'), fallback]
    if move['amount_total'] and move['amount_total_signed']:
        candidates.append(abs(move['amount_total'] / move['amount_total_signed']))
    low, high = 0.0, float('inf')
    half = company_rounding / 2
    for amount, balance in pairs:
        if amount * balance < 0 or (not amount and balance):
            raise ValueError('inconsistent_source_fx_sign_or_zero')
        a, b = abs(amount), abs(balance)
        if a:
            low = max(low, a / (b + half))
            if b > half:
                high = min(high, a / (b - half))
        if amount and balance:
            candidates.append(amount / balance)
    if low < high and math.isfinite(high):
        candidates.append((low + high) / 2)
    # All-zero documents require an evidenced rate, not division of zero totals.
    for rate in candidates:
        if rate and math.isfinite(rate) and rate > 0 and all(equal_money(a / rate, b, company_rounding) for a, b in pairs):
            return rate
    raise ValueError('no_single_evidenced_rate_reproduces_source_balances')

def salesperson(source_user_id, source_users, target_users, overrides=None, company_id=1):
    if not source_user_id:
        return False
    sources = [u for u in source_users if u['id'] == source_user_id]
    if len(sources) != 1:
        raise ValueError('source_salesperson_missing')
    login = (sources[0].get('login') or '').strip().casefold()
    if not login:
        raise ValueError('source_salesperson_login_missing')
    login = (overrides or {}).get(login, login).casefold()
    matches = [u for u in target_users if (u.get('login') or '').strip().casefold() == login]
    if len(matches) != 1 or not matches[0]['active']:
        raise ValueError('target_salesperson_missing_ambiguous_or_archived: ' + login)
    if 'company_ids' in matches[0] and company_id not in matches[0]['company_ids']:
        raise ValueError('target_salesperson_wrong_company')
    return matches[0]['id']

def partner_map(external_ids):
    hits = {}
    for x in external_ids:
        if x.get('model') != 'res.partner':
            continue
        match = re.match(r'^(?:res_partner|partner)_(\d+)(?:_|$)', x['name'])
        if match:
            hits.setdefault(int(match[1]), set()).add(x['res_id'])
    return {sid: next(iter(ids)) for sid, ids in hits.items() if len(ids) == 1}, hits

def contact_differences(source, target, mapping, target_partners):
    """Report master differences; this module never writes or infers a parent by name."""
    issues = []
    for field in CONTACT_FIELDS:
        if field not in source or field not in target:
            issues.append({'reason': 'contact_field_not_checked', 'field': field})
    if mapping.get(source['id']) != target['id']:
        issues.append({'reason': 'contact_identity_not_proven'})
    for field in ['parent_id', 'commercial_partner_id']:
        if field not in source or field not in target:
            continue
        sid, tid = rid(source[field]), rid(target[field])
        expected = mapping.get(sid) if sid else False
        if sid and expected is None:
            issues.append({'reason': 'related_contact_mapping_missing', 'field': field, 'source_id': sid})
        elif expected != tid:
            issues.append({'reason': 'contact_relation_difference', 'field': field, 'expected': expected, 'actual': tid})
        parent = target_partners.get(expected) if expected else None
        if field == 'parent_id' and parent is not None and not parent.get('active'):
            issues.append({'reason': 'expected_parent_archived', 'target_id': expected})
    for field in ['name', 'company_name']:
        if field in source and field in target and (source[field] or '') != (target[field] or ''):
            issues.append({'reason': 'contact_text_difference', 'field': field, 'source': source[field], 'target': target[field]})
    if not target.get('active', True):
        issues.append({'reason': 'target_contact_archived'})
    if rid(target.get('company_id')) not in (False, 1):
        issues.append({'reason': 'target_contact_wrong_company'})
    return issues

def validation_errors(document, actual, lines):
    """Mandatory company money, native FX and explicit Invoice user, both create/post."""
    check = document.get('historical_checks')
    if not check or check.get('version') != VERSION:
        return [{'reason': 'historical_checks_missing_reprepare_manifest'}]
    errors = []
    for field, expected in check['totals'].items():
        unit = check['company_rounding'] if field == 'amount_total_signed' else check['currency_rounding']
        if field not in actual or not equal_money(actual[field], expected, unit):
            errors.append({'field': field, 'expected': expected, 'actual': actual.get(field), 'reason': 'money_or_required_field_mismatch'})
    for field in ['invoice_currency_rate', 'x_foreign_to_company_rate', 'invoice_user_id']:
        if field not in document['header']:
            continue
        want = document['header'][field]
        have = actual.get(field)
        if field == 'invoice_user_id':
            good = field in actual and rid(have) == want
        else:
            good = field in actual and math.isclose(have, want, rel_tol=1e-10, abs_tol=1e-10)
        if not good:
            errors.append({'field': field, 'expected': want, 'actual': have})
    for expected, lid in zip(document['lines'], actual.get('invoice_line_ids', [])):
        if 'expected_balance' not in expected:
            continue
        row = lines[lid]
        for field, key, unit in [('balance', 'expected_balance', check['company_rounding']), ('amount_currency', 'expected_amount_currency', check['currency_rounding'])]:
            if field not in row or not equal_money(row[field], expected[key], unit):
                errors.append({'line': lid, 'field': field, 'expected': expected[key], 'actual': row.get(field)})
    return errors

def require_manifest(documents):
    for document in documents:
        if document.get('historical_checks', {}).get('version') != VERSION:
            raise ValueError('Old manifest: rerun inspect/prepare before any create/post')

def extra_read_fields(documents):
    return READ_FIELDS + (['x_foreign_to_company_rate'] if any('x_foreign_to_company_rate' in d['header'] for d in documents) else [])

def prepare_context(source_reader, target_reader, moves, external_ids, validated_partner_mapping=None):
    """Read only. Include archived contacts/users; callers' readers use active_test=False."""
    company = source_reader.read('res.company', [1], ['currency_id'])[0]
    currency_ids = sorted({rid(m['currency_id']) for m in moves} | {rid(company['currency_id'])})
    currencies = {c['id']: c for c in source_reader.read('res.currency', currency_ids, ['rounding'])}
    source_users = source_reader.search_read('res.users', [], ['login', 'active'])
    target_users = target_reader.search_read('res.users', [], ['login', 'active', 'company_ids'])
    mapping, hits = partner_map(external_ids)
    if validated_partner_mapping is not None:
        mapping = dict(validated_partner_mapping)
        hits = {sid: {tid} for sid, tid in mapping.items()}
    sources = {p['id']: p for p in source_reader.read('res.partner', sorted({rid(m['partner_id']) for m in moves if m['partner_id']}), CONTACT_FIELDS)}
    relatives = {rid(p[k]) for p in sources.values() for k in ['parent_id', 'commercial_partner_id'] if p[k]}
    if relatives - sources.keys():
        sources.update({p['id']: p for p in source_reader.read('res.partner', sorted(relatives - sources.keys()), CONTACT_FIELDS)})
    tids = sorted({mapping[i] for i in sources if i in mapping})
    targets = {p['id']: p for p in target_reader.read('res.partner', tids, CONTACT_FIELDS)} if tids else {}
    # Snapshot rates are fallback evidence only: source journal balances remain authoritative.
    rates = source_reader.search_read('res.currency.rate', [['currency_id', 'in', currency_ids], ['company_id', 'in', [False, 1]]], ['currency_id', 'company_id', 'name', 'rate'])
    return dict(company_currency_id=rid(company['currency_id']), currencies=currencies,
                source_users=source_users, target_users=target_users, partner_mapping=mapping,
                partner_hits=hits, source_partners=sources, target_partners=targets, rates=rates)

def enrich_document(document, source_lines, context, target_schema):
    source, header = document['source'], document['header']
    errors = document['errors']
    company_rounding = context['currencies'][context['company_currency_id']]['rounding']
    currency_rounding = context['currencies'][rid(source['currency_id'])]['rounding']
    document['historical_checks'] = dict(version=VERSION, company_rounding=company_rounding,
        currency_rounding=currency_rounding, totals={k: source[k] for k in ['amount_untaxed', 'amount_tax', 'amount_total', 'amount_total_signed']})
    for field in ['invoice_currency_rate', 'invoice_user_id', 'amount_total_signed']:
        if field not in target_schema:
            errors.append({'reason': 'required_target_field_missing', 'field': field})
    try:
        rates = [r for r in context['rates'] if rid(r['currency_id']) == rid(source['currency_id']) and r['name'] <= (source['invoice_date'] or source['date'])]
        rates.sort(key=lambda r: (r['name'], bool(r['company_id']), r['id']), reverse=True)
        fallback = rates[0]['rate'] if rates else None
        header['invoice_currency_rate'] = historical_rate(source, source_lines, context['company_currency_id'], company_rounding, fallback)
        document['historical_checks']['fx_evidence'] = {'excluded_net_zero_ancillary_line_ids': rate_lines(source, source_lines)[1], 'rate': header['invoice_currency_rate']}
        if 'x_foreign_to_company_rate' in target_schema:
            header['x_foreign_to_company_rate'] = 1 / header['invoice_currency_rate']
    except (ValueError, KeyError) as exc:
        errors.append({'reason': 'historical_fx_requires_review', 'detail': str(exc)})
    if source['move_type'] == 'out_invoice':
        try:
            header['invoice_user_id'] = salesperson(rid(source['invoice_user_id']), context['source_users'], context['target_users'], {'warehouse': 'BILLING1'})
        except ValueError as exc:
            errors.append({'reason': 'salesperson_mapping_requires_review', 'detail': str(exc)})
    line_index = {line['id']: line for line in source_lines}
    for line in document['lines']:
        original = line_index[line['source_line_id']]
        if not line['values'].get('display_type'):
            line.update(expected_balance=original['balance'], expected_amount_currency=original['amount_currency'])
    sid, tid = rid(source['partner_id']), header['partner_id']
    sp, tp = context['source_partners'].get(sid), context['target_partners'].get(tid)
    if sp and tp:
        issues = contact_differences(sp, tp, context['partner_mapping'], context['target_partners'])
    else:
        issues = [{'reason': 'contact_identity_not_proven', 'source_id': sid, 'target_id': tid}]
    document['contact_review'] = {'source': sp, 'target': tp, 'differences': issues, 'action': 'report_only_no_master_write'}
    if any(x['reason'] in ['contact_identity_not_proven', 'target_contact_wrong_company'] for x in issues):
        errors.append({'reason': 'contact_identity_requires_review', 'differences': issues})
