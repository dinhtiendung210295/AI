"""Find all July closing gaps, not just products already mapped; read-only."""
import json
from scan_pysb_july_other_stock_coverage import cli_args, run_scan, load, save, mapping_evidence
from discover_pysb_supporting_stock import discover


def main():
    args = cli_args(__doc__)
    a, _, coverage = run_scan(args.evidence_dir, args.output_dir)
    maps, _ = mapping_evidence(load(args.evidence_dir/'execution-manifest.json'),
                               load(args.evidence_dir/'execution-journal.json'))
    details = discover(a, coverage, maps)
    # Keep the established consumer keys; MO and unknown categories are retained
    # explicitly instead of discarded or silently fed into receipt execution.
    save(args.output_dir/'supporting-stock-discovery.json', details)
    save(args.output_dir/'closing-gap-source-documents.json', details)
    print(json.dumps({'output_dir': str(args.output_dir),
                      'unresolved_moves': len(details['unresolved_source_move_ids']),
                      'source_documents': len(details['pickings']), 'MO': len(details['mos']),
                      'missing': details['missing']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
