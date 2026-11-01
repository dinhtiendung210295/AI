import runpy
from pathlib import Path
from types import SimpleNamespace
import unittest
import tempfile
from unittest.mock import patch

M = runpy.run_path(str(Path(__file__).parents[1] / 'confirm_pysb_prod_orders.py'))


class ChainTests(unittest.TestCase):
    def chain(self):
        return dict(pickings=[dict(id=1, company_id=[1, 'P'], state='assigned')],
                    moves=[dict(id=2, company_id=[1, 'P'], state='assigned', picked=False,
                                sale_line_id=False, purchase_line_id=[10, 'POL'], move_orig_ids=[])], move_lines=[])

    def test_native_receipt_chain_valid(self):
        M['validate_new_chain'](self.chain(), [10])

    def test_done_or_foreign_or_external_chain_refused(self):
        for changes in ({'state': 'done'}, {'company_id': [2, 'Other']}, {'purchase_line_id': [11, 'Foreign']}, {'sale_line_id': [3, 'SO']}, {'move_orig_ids': [99]}, {'picked': True}):
            with self.subTest(changes=changes):
                chain = self.chain()
                chain['moves'][0].update(changes)
                with self.assertRaises(RuntimeError):
                    M['validate_new_chain'](chain, [10])

    def test_reservation_does_not_authorize_picked_lines(self):
        chain = self.chain()
        chain['move_lines'] = [dict(id=4, state='assigned', picked=True)]
        with self.assertRaises(RuntimeError):
            M['validate_new_chain'](chain, [10])

    def test_supplier_missing_blocks_master_creation(self):
        order = {'partner_id': [1, 'Vendor']}
        lines = [{'id': 5, 'product_id': [2, 'Product']}]
        products = {2: {'seller_ids': [3]}}
        sellers = {3: {'partner_id': [4, 'Other vendor']}}
        self.assertTrue(M['vendor_issues'](order, lines, products, sellers, False))
        self.assertFalse(M['vendor_issues'](order, lines, products, sellers, [4, 'Parent']))

    def test_native_supplier_cap_boundary_is_preserved(self):
        order = {'partner_id': [1, 'Vendor']}
        lines = [{'id': 5, 'product_id': [2, 'Product']}]
        sellers = {i: {'partner_id': [4, 'Other']} for i in range(11)}
        self.assertTrue(M['vendor_issues'](order, lines, {2: {'seller_ids': list(range(10))}}, sellers, False))
        self.assertFalse(M['vendor_issues'](order, lines, {2: {'seller_ids': list(range(11))}}, sellers, False))

    def test_changed_source_refused(self):
        with self.assertRaises(RuntimeError):
            M['assert_fresh']({'quantity': 2}, {'quantity': 3}, 'Source line')

    def runner(self, status='verified_confirmed', state='purchase'):
        runner = M['ConfirmPO'].__new__(M['ConfirmPO'])
        runner.j = {'orders': {'purchase.order:1': dict(status=status, historical_date='2026-08-01 00:00:00')}}
        runner.b = SimpleNamespace(read=lambda *args: [dict(state=state, date_approve='2026-08-01 00:00:00')])
        runner.mutate = lambda *args: self.fail('Resume must not send a mutation')
        return runner

    def test_resume_confirmed_reuses_order(self):
        runner = self.runner()
        result = runner.confirm({'source_id': 1, 'target_id': 2}, {})
        self.assertEqual('verified_confirmed', result['status'])

    def test_resume_after_intent_without_result_never_reconfirms(self):
        runner = self.runner('prepared')
        with self.assertRaises(RuntimeError):
            runner.confirm({'source_id': 1, 'target_id': 2}, {})

    def test_resume_changed_target_never_reconfirms(self):
        runner = self.runner(state='draft')
        with self.assertRaises(RuntimeError):
            runner.confirm({'source_id': 1, 'target_id': 2}, {})

    def test_confirmation_native_readback_and_historical_date(self):
        runner = M['ConfirmPO'].__new__(M['ConfirmPO'])
        runner.j = {'orders': {}}
        runner.chains = {'orders': {}}
        runner.identity = {'scope_hash': 'test'}
        runner.maps = {'purchase.order.line': {99: 10}}
        runner.persist = lambda: None
        runner.log = SimpleNamespace(build_checkpoint=lambda: None)
        header = dict(id=2, state='draft', date_approve=False, order_line=[10], picking_ids=[], write_date='old')
        line = dict(id=10, order_id=[2, 'PO'], write_date='old')
        preflight = dict(issues=[], source={'date_approve': '2026-08-01 00:00:00'}, target=dict(header),
                         source_lines=[{'id': 99}], target_lines=[line], products={1: {'id': 1, 'seller_ids': [3], 'active': True}},
                         before_chain=dict(pickings=[], moves=[], move_lines=[]))
        runner.preflight = lambda row: preflight
        runner.chain = lambda tid: self.chain()
        runner.counters = lambda: {'account.move': 1, 'mrp.production': 1, 'purchase.order': 1}
        calls = []
        def mutate(sid, tid, method, args, before):
            calls.append(method)
            if method == 'button_confirm':
                header.update(state='purchase', picking_ids=[1], write_date='new')
            else:
                header.update(args[1])
            return method + ':operation'
        runner.mutate = mutate
        def read(model, ids, fields):
            if model == 'purchase.order':
                return [{k: header[k] for k in fields}]
            if model == 'purchase.order.line':
                return [dict(line)]
            if model == 'product.product':
                return list(preflight['products'].values())
            self.fail(model)
        runner.b = SimpleNamespace(read=read)
        result = runner.confirm(dict(source_id=1, target_id=2, target_state='draft'), preflight)
        self.assertEqual(['button_confirm', 'write'], calls)
        self.assertEqual('verified_confirmed', result['status'])
        self.assertEqual(0, result['warehouse_done_by_this_phase'])
        self.assertEqual('created_by_phase', runner.chains['orders']['purchase.order:1']['provenance'])

    def group_runner(self, second_state='purchase'):
        runner = M['ConfirmPO'].__new__(M['ConfirmPO'])
        runner.identity = {'scope_hash': 'test'}
        runner.session_token = 'test-session'
        runner.j = {'orders': {}}
        runner.persist = lambda: None
        runner.counters = lambda: {'account.move': 5}
        selected = []
        for sid, tid in [(1, 2), (3, 4)]:
            selected.append((dict(source_id=sid, target_id=tid, target_state='draft'), dict(issues=[], source={'date_approve': '2026-08-01'}, before_chain={})))
        runner.preflight = lambda row: next(p for r, p in selected if r['source_id'] == row['source_id'])
        runner.b = SimpleNamespace(r=object(), read=lambda *args: [dict(id=2, state='purchase'), dict(id=4, state=second_state)])
        runner.chain = lambda tid: {'captured_target': tid}
        runner.log = SimpleNamespace(append_intent=lambda op: None, append_result=lambda oid, result: None,
                                     mark_uncertain=lambda oid, error: None)
        runner.finish_confirmed = lambda row, preflight, entry, counters: dict(source_id=row['source_id'], target_id=row['target_id'], status='verified_confirmed')
        return runner, selected

    def test_recordset_confirms_two_orders_with_one_native_call(self):
        runner, selected = self.group_runner()
        calls = []
        with patch.dict(M['W'], {'call': lambda *args: calls.append(args) or True}):
            result = runner.confirm_recordset(selected)
        self.assertEqual(1, len(calls))
        self.assertEqual([[2, 4]], calls[0][3])
        self.assertEqual(2, len(result['completed']))

    def test_partial_native_approval_classified_individually(self):
        runner, selected = self.group_runner('to approve')
        with patch.dict(M['W'], {'call': lambda *args: True}):
            result = runner.confirm_recordset(selected)
        self.assertEqual(1, len(result['completed']))
        self.assertEqual('held_native_approval', result['held'][0]['status'])
        self.assertEqual(3, result['held'][0]['source_id'])

    def test_failed_recordset_never_blindly_retries_singletons(self):
        runner, selected = self.group_runner()
        calls = []
        def fail(*args):
            calls.append(args)
            raise RuntimeError('Expected singleton')
        with tempfile.TemporaryDirectory() as temp:
            runner.phase = Path(temp)
            with patch.dict(M['W'], {'call': fail}):
                with self.assertRaises(RuntimeError):
                    runner.confirm_recordset(selected)
        self.assertEqual(1, len(calls))


if __name__ == '__main__':
    unittest.main()
