import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import unittest

BASE = Path(__file__).parents[1]
C = runpy.run_path(str(BASE / 'run_pysb_phased_migration.py'))
R = runpy.run_path(str(BASE / 'inspect_pysb_phase_readiness.py'))


class PhaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        (self.directory / 'phases').mkdir()
        self.identity = dict(source_database='fake-source', target_database='fake-target', company_id=1, scope_hash='frozen')

    def gate(self, **changes):
        evidence = self.directory / 'phases/verified.json'
        evidence.write_text('{}', encoding='utf8')
        gate = dict(self.identity, phase='confirm-po', status='closed_with_holds', eligible_unattempted=0,
                    completed_utc='2026-10-25T14:00:00+00:00', live_verification_complete=True,
                    evidence=[dict(path='phases/verified.json', sha256=hashlib.sha256(evidence.read_bytes()).hexdigest())])
        gate.update(changes)
        (self.directory / 'phases/confirm-po-gate.json').write_text(json.dumps(gate), encoding='utf8')
        return gate

    def test_so_without_po_gate_refused(self):
        with self.assertRaises(FileNotFoundError):
            C['require_previous_gate'](self.directory, 'confirm-so', self.identity)

    def test_valid_gate_allows_next_phase(self):
        self.gate()
        self.assertEqual('closed_with_holds', C['require_previous_gate'](self.directory, 'confirm-so', self.identity)['status'])

    def test_wrong_scope_refused(self):
        self.gate(scope_hash='other')
        with self.assertRaises(RuntimeError):
            C['require_previous_gate'](self.directory, 'confirm-so', self.identity)

    def test_remaining_eligible_refused(self):
        self.gate(eligible_unattempted=1)
        with self.assertRaises(RuntimeError):
            C['require_previous_gate'](self.directory, 'confirm-so', self.identity)

    def test_gate_file_alone_is_insufficient(self):
        self.gate(live_verification_complete=False)
        with self.assertRaises(RuntimeError):
            C['require_previous_gate'](self.directory, 'confirm-so', self.identity)

    def test_changed_evidence_refused(self):
        self.gate()
        (self.directory / 'phases/verified.json').write_text('{"changed":true}', encoding='utf8')
        with self.assertRaises(RuntimeError):
            C['require_previous_gate'](self.directory, 'confirm-so', self.identity)

    def test_invoice_service_expands_order_scope(self):
        scope = R['build_scope']([], [{'id': 1}], {
            'account.move.line': [{'id': 7, 'move_id': [1, 'INV'], 'sale_line_ids': [5]}],
            'sale.order.line': [{'id': 5, 'order_id': [3, 'SO']}], 'purchase.order.line': []}, {})
        self.assertEqual([3], [r['source_id'] for r in scope['sale.order']])

    def test_missing_dependency_preserved(self):
        scope = R['build_scope']([{'id': 1, 'sale_line_id': [5, 'line']}], [], {
            'account.move.line': [], 'sale.order.line': [], 'purchase.order.line': []}, {})
        self.assertEqual(5, scope['unresolved_source_line_dependencies'][0]['source_line'])

    def check_discount(self, discount):
        source = dict(id=1, state='purchase', company_id=[1, 'Company'], order_line=[10])
        target = dict(id=2, state='draft', company_id=[1, 'Company'], order_line=[20])
        line = dict(id=10, order_id=[1, 'PO'], product_id=[100, 'P'], product_uom=[1, 'UNIT'],
                    product_qty=2, price_unit=3, price_subtotal=6, price_total=6, taxes_id=[])
        other = dict(line, id=20, order_id=[2, 'PO'], product_id=[200, 'P'], product_uom_id=[2, 'UNIT'], discount=discount)
        maps = {'purchase.order.line': {10: 20}, 'product.product': {100: 200}, 'uom.uom': {1: 2}}
        result = R['compare_order']('purchase.order', source, target, [line], [other], maps,
                                    {1: {'rounding': 1}}, {2: {'rounding': 1}}, {}, '2026-10-24')
        return [i for i in result['line_results'][0]['issues'] if i.get('field') == 'discount']

    def test_missing_source_purchase_discount_equals_zero_only(self):
        self.assertEqual([], self.check_discount(0))
        self.assertEqual(1, len(self.check_discount(5)))


if __name__ == '__main__':
    unittest.main()
