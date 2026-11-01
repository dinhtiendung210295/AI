"""Keep original MO metrics; classify only exact, independently proven exceptions."""


def annotate(report, coverage, expected):
    for mo in report['rows']:
        for move in mo.get('moves', []):
            approved = expected.get(move['source_move'], {})
            dimensions_ok = coverage.get(move['source_move']) in {'verified', 'approved_exception'}
            allowed_issues = {'move_dimensions_or_state_not_verified'} if dimensions_ok else set()
            exceptions = []
            checks = []
            for label, metric in move['metrics'].items():
                exception = approved.get(label)
                valid = bool(exception and metric.get('source') == exception['source']
                             and metric.get('target') == exception['target'])
                if valid and metric.get('delta'):
                    exceptions.append(dict(exception, metric=label))
                checks.append(metric['match'] or valid)
            move['approved_exceptions'] = exceptions
            move['accepted_with_approved_exceptions'] = bool(
                exceptions and dimensions_ok and not (set(move['issues']) - allowed_issues)
                and checks and all(checks))
        mo['accepted_with_approved_exceptions'] = bool(
            not mo['match'] and not mo['issues'] and mo.get('moves')
            and all(x['match'] for x in mo['metrics'].values())
            and all(x['match'] or x.get('accepted_with_approved_exceptions') for x in mo['moves']))
    exceptions = sum(x['accepted_with_approved_exceptions'] for x in report['rows'])
    report['summary']['approved_exception_mos'] = exceptions
    report['summary']['unresolved_mos'] = sum(not x['match'] and not x['accepted_with_approved_exceptions'] for x in report['rows'])
    return report
