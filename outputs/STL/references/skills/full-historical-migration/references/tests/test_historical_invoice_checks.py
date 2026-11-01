"""Offline regressions for the migration fixes; no Odoo connections."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

REF = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('checks', REF/'historical_invoice_checks.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
ROOT = REF.parents[5]

class ChecksTests(unittest.TestCase):
    def setUp(self):
        self.move = dict(currency_id=[2, 'USD'], amount_total=100, amount_total_signed=-428.2)
        self.lines = [dict(currency_id=[2, 'USD'], amount_currency=100, balance=428.2), dict(currency_id=[2, 'USD'], amount_currency=-100, balance=-428.2)]
        self.users = [dict(id=7, login='SALES1', active=True, company_ids=[1]), dict(id=14, login='BILLING1', active=True, company_ids=[1])]

    def test_historical_balances_win_over_current_table_rate(self):
        rate = c.historical_rate(self.move, self.lines, 34, fallback=1/4.085)
        self.assertAlmostEqual(1/rate, 4.282)

    def test_zero_total_with_nonzero_lines(self):
        self.move.update(amount_total=0, amount_total_signed=0)
        self.assertAlmostEqual(1/c.historical_rate(self.move, self.lines, 34), 4.282)

    def test_all_zero_needs_evidence(self):
        self.move.update(amount_total=0, amount_total_signed=0)
        with self.assertRaises(ValueError): c.historical_rate(self.move, [], 34)
        self.assertEqual(c.historical_rate(self.move, [], 34, fallback=0.25), 0.25)

    def test_incompatible_line_rates_block(self):
        self.lines[1]['balance'] = -400
        with self.assertRaises(ValueError): c.historical_rate(self.move, self.lines, 34)

    def test_mixed_currency_line_block(self):
        self.lines[1]['currency_id'] = [3, 'EUR']
        with self.assertRaises(ValueError): c.historical_rate(self.move, self.lines, 34)

    def test_source_login_and_warehouse_override(self):
        src = [dict(id=88, login='sales1'), dict(id=99, login='WAREHOUSE')]
        self.assertEqual(c.salesperson(88, src, self.users), 7)
        self.assertEqual(c.salesperson(99, src, self.users, {'warehouse':'BILLING1'}), 14)
        self.assertFalse(c.salesperson(False, src, self.users))

    def test_missing_duplicate_archived_wrong_company_user_block(self):
        src = [dict(id=88, login='SALES1')]
        bad = [[], self.users+[self.users[0]], [dict(self.users[0], active=False)], [dict(self.users[0], company_ids=[2])]]
        for users in bad:
            with self.subTest(users=users), self.assertRaises(ValueError): c.salesperson(88, src, users)

    def test_contact_parent_and_text_are_separate_and_readonly(self):
        src = dict(id=1, name='Person', company_id=False, active=True, parent_id=[2,'Parent'], company_name='Parent', commercial_partner_id=[2,'Parent'])
        target = dict(src, id=11, parent_id=False, company_name=False, commercial_partner_id=[11,'Person'])
        original = copy.deepcopy((src, target))
        issues = c.contact_differences(src, target, {1:11,2:22}, {22:dict(active=False)})
        self.assertIn('contact_relation_difference', [x['reason'] for x in issues])
        self.assertIn('expected_parent_archived', [x['reason'] for x in issues])
        self.assertTrue(any(x.get('field')=='company_name' for x in issues))
        self.assertNotIn('contact_identity_not_proven', [x['reason'] for x in issues])
        self.assertEqual((src,target), original)

    def test_company_name_does_not_invent_parent(self):
        src = dict(id=1, name='GUNALAN', company_id=False, active=True, parent_id=False, company_name='PAWAN', commercial_partner_id=[1,'GUNALAN'])
        target = dict(src, id=11, company_name=False, commercial_partner_id=[11,'GUNALAN'])
        issues = c.contact_differences(src, target, {1:11}, {})
        self.assertEqual([x['field'] for x in issues], ['company_name'])

    def test_ambiguous_external_id_not_accepted(self):
        mapping, hits = c.partner_map([dict(model='res.partner',name='partner_1_a',res_id=11),dict(model='res.partner',name='res_partner_1_b',res_id=12)])
        self.assertNotIn(1, mapping)

    def test_legacy_manifest_refused(self):
        with self.assertRaises(ValueError): c.require_manifest([{'header':{}}])

    def test_missing_money_user_or_line_balance_fails_readback(self):
        document = dict(historical_checks=dict(version=1,company_rounding=.01,currency_rounding=.01,totals=dict(amount_total=100,amount_total_signed=-428.2)),header=dict(invoice_currency_rate=1/4.282,invoice_user_id=7),lines=[dict(expected_balance=428.2,expected_amount_currency=100)])
        actual = dict(amount_total=100,amount_total_signed=-428.2,invoice_currency_rate=1/4.282,invoice_user_id=[7,'Sales'],invoice_line_ids=[10])
        lines = {10:dict(balance=428.2,amount_currency=100)}
        self.assertFalse(c.validation_errors(document, actual, lines))
        for field in ['amount_total_signed','invoice_user_id','invoice_currency_rate']:
            broken = dict(actual);broken.pop(field)
            self.assertTrue(c.validation_errors(document, broken, lines))
        self.assertTrue(c.validation_errors(document, dict(actual,amount_total_signed=-408.5), lines))
        self.assertTrue(c.validation_errors(document, actual, {10:dict(balance=408.5,amount_currency=100)}))

    def test_real_18_bill_regressions_and_17_salespeople(self):
        base = ROOT/'outputs/pysb-sue-invoice-review-20261016'
        if not (base/'live/snapshot.json').exists(): self.skipTest('Incident evidence not installed')
        data = json.loads((base/'live/snapshot.json').read_text(encoding='utf8'))['sides']
        source = {m['id']:m for m in data['source']['records']}
        lines = {l['id']:l for l in data['source']['lines']}
        count = 0
        for folder in ['pysb-invoice-migration-20261013','pysb-invoice-july-supplement-20261014']:
            hist = json.loads((ROOT/'outputs'/folder/'invoice-execution-journal.json').read_text(encoding='utf8'))['documents']
            targets = {m['id']:m for m in data['target']['records']}
            for sid, entry in hist.items():
                m = source[int(sid)]; t = targets[entry['target_id']]
                if abs(m['amount_total_signed']-t['amount_total_signed']) <= .011: continue
                rate = c.historical_rate(m, [lines[i] for i in m['line_ids']], 34)
                self.assertTrue(c.equal_money(m['amount_total']/rate, abs(m['amount_total_signed']), .01))
                count += 1
        self.assertEqual(count, 18)
        mismatches = json.loads((base/'invoice-salesperson-mismatches.json').read_text(encoding='utf8'))
        target_users = json.loads((base/'fx-salesperson-repair/preflight.json').read_text(encoding='utf8'))['target_users']
        for row in mismatches:
            uid = c.salesperson(c.rid(source[row['source_id']]['invoice_user_id']), data['source']['users'], target_users, {'warehouse':'BILLING1'})
            self.assertEqual(uid, 14 if row['source_user_login'].casefold()=='warehouse' else row['candidate_target_user_ids'][0])
        self.assertEqual(len(mismatches),17)

    def prepared(self, kind='out_invoice'):
        source = dict(self.move, id=1, move_type=kind, invoice_user_id=[88,'Sales'],partner_id=[1,'Person'], invoice_date='2026-07-02',date='2026-07-02',amount_untaxed=100,amount_tax=0,line_ids=[1,2],invoice_line_ids=[1])
        source['amount_total_signed'] = 428.2 if kind=='out_invoice' else -428.2
        lines = [dict(l,id=i+1) for i,l in enumerate(self.lines)]
        partner = dict(id=1,name='Person',company_id=False,active=True,parent_id=False,company_name='PAWAN',commercial_partner_id=[1,'Person'])
        target = dict(partner,id=11,company_name=False,commercial_partner_id=[11,'Person'])
        context = dict(company_currency_id=34,currencies={2:dict(rounding=.01),34:dict(rounding=.01)},source_users=[dict(id=88,login='SALES1')],target_users=self.users,rates=[],source_partners={1:partner},target_partners={11:target},partner_mapping={1:11})
        doc = dict(source=source,header=dict(partner_id=11),errors=[],lines=[dict(source_line_id=1,values={})])
        c.enrich_document(doc,lines,context,{'invoice_currency_rate','invoice_user_id','amount_total_signed','x_foreign_to_company_rate'})
        return doc,context,lines

    def test_prepare_transmits_fx_and_explicit_user_with_contact_report(self):
        doc,_,_ = self.prepared()
        self.assertFalse(doc['errors'])
        self.assertEqual(doc['header']['invoice_user_id'],7)
        self.assertAlmostEqual(doc['header']['x_foreign_to_company_rate'],4.282)
        self.assertEqual(doc['lines'][0]['expected_balance'],428.2)
        self.assertTrue(any(x.get('field')=='company_name' for x in doc['contact_review']['differences']))
        self.assertFalse(doc['contact_review']['target']['parent_id'])

    def test_bill_does_not_inherit_invoice_salesperson_requirement(self):
        doc,_,_ = self.prepared('in_invoice')
        self.assertFalse(doc['errors'])
        self.assertNotIn('invoice_user_id',doc['header'])

    def test_missing_native_rate_schema_blocks_before_create(self):
        doc,context,lines = self.prepared()
        doc['errors']=[]
        c.enrich_document(doc,lines,context,{'invoice_user_id','amount_total_signed'})
        self.assertIn({'reason':'required_target_field_missing','field':'invoice_currency_rate'},doc['errors'])

    def test_only_net_zero_ancillary_entries_can_be_excluded(self):
        move = dict(self.move,invoice_line_ids=[1])
        lines = [dict(self.lines[0],id=1),dict(self.lines[1],id=2)]
        lines += [dict(id=3,currency_id=[2,'USD'],amount_currency=.01,balance=0),dict(id=4,currency_id=[2,'USD'],amount_currency=-.01,balance=0)]
        self.assertEqual(c.rate_lines(move,lines)[1],[3,4])
        self.assertAlmostEqual(1/c.historical_rate(move,lines,34),4.282)
        with self.assertRaises(ValueError):c.historical_rate(move,lines[:-1],34)

if __name__ == '__main__': unittest.main()
