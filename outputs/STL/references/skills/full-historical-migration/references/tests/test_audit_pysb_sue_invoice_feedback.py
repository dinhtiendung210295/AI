"""Behavioral audit regressions. No network, credentials or live Odoo constructors."""
from pathlib import Path
import copy
import importlib.util
import unittest
from unittest.mock import patch

FILE=Path(__file__).resolve().parents[1]/'audit_pysb_sue_invoice_feedback.py'
spec=importlib.util.spec_from_file_location('sue_audit',FILE)
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.s={'id':1,'name':'BILL/2026/07/0001','state':'posted','move_type':'in_invoice','company_id':[1,'PYSB'],'currency_id':[2,'USD'],'partner_id':[20,'Vendor'],'invoice_user_id':False,'invoice_date':'2026-07-02','date':'2026-07-02','invoice_date_due':'2026-07-02','invoice_origin':'PO1','ref':'Ref1','amount_untaxed':100,'amount_tax':0,'amount_total':100,'amount_total_signed':-428.2}
        self.t={**copy.deepcopy(self.s),'id':10,'partner_id':[200,'Vendor'],'currency_id':[22,'USD'],'amount_total_in_currency_signed':-100}
        self.h={1:{'run':'fixture','manifest':{'source':copy.deepcopy(self.s),'header':{'partner_id':200}},'journal':{'target_id':10,'after':copy.deepcopy(self.t)}}}
        currency_s=[{'id':2,'name':'USD','rounding':0.01},{'id':34,'name':'MYR','rounding':0.01}]
        currency_t=[{'id':22,'name':'USD','rounding':0.01},{'id':34,'name':'MYR','rounding':0.01}]
        self.data={'sides':{'source':{'database':'source','company':{'currency_id':[34,'MYR']},'records':[self.s],'july_ids':[1],'users':[],'currencies':currency_s},'target':{'database':'target','company':{'currency_id':[34,'MYR']},'records':[self.t],'july_ids':[10],'users':[],'currencies':currency_t,'external_ids':[]}}}

    def result(self):
        with patch.object(audit,'history',return_value=(self.h,[])):
            return audit.compare(self.data)

    def test_company_money_change_caught_with_identical_native_total(self):
        self.t['amount_total_signed']=-408.5
        row=self.result()['rows'][0]
        self.assertIn('amount_total_signed',row['differences'])
        self.assertNotIn('amount_total',row['differences'])

    def test_wrong_currency_caught_even_with_equal_amounts(self):
        self.data['sides']['target']['currencies'][0]['name']='EUR'
        self.assertIn('currency',self.result()['rows'][0]['differences'])

    def test_cnh_cny_not_silently_accepted(self):
        self.data['sides']['source']['currencies'][0]['name']='CNH'
        self.data['sides']['target']['currencies'][0]['name']='CNY'
        self.assertIn('currency',self.result()['rows'][0]['differences'])

    def test_same_user_login_different_name_is_same_person(self):
        self.assertTrue(audit.user_equal({'name':'SALES 3','login':'SALES3'},{'name':'Ta Kai Tan','login':'sales3'}))

    def test_same_name_different_login_is_not_same_person(self):
        self.assertFalse(audit.user_equal({'name':'Alice','login':'A'},{'name':'Alice','login':'B'}))

    def test_missing_salesperson_caught(self):
        self.s['invoice_user_id']=[3,'Agent']
        self.data['sides']['source']['users']=[{'id':3,'login':'Agent'}]
        self.assertIn('salesperson',self.result()['rows'][0]['differences'])

    def test_partner_rename_is_not_wrong_mapped_record(self):
        self.t['partner_id']=[200,'Vendor cleaned']
        diff=self.result()['rows'][0]['differences']
        self.assertIn('partner_name',diff);self.assertNotIn('partner_mapping',diff)

    def test_case_only_name_difference_is_separate(self):
        self.t['partner_id']=[200,'VENDOR']
        diff=self.result()['rows'][0]['differences']
        self.assertIn('partner_name',diff);self.assertNotIn('partner_name_ignore_case',diff)

    def test_wrong_partner_mapping_caught(self):
        self.t['partner_id']=[999,'Vendor']
        self.assertIn('partner_mapping',self.result()['rows'][0]['differences'])

    def test_missing_target_does_not_disappear(self):
        self.data['sides']['target']['records']=[]
        self.assertEqual(self.result()['rows'][0]['status'],'target_not_extracted')

    def test_duplicate_provenance_not_first_match(self):
        self.data['sides']['target']['external_ids']=[{'model':'account.move','name':'account_move_1_other','res_id':99}]
        self.assertEqual(self.result()['rows'][0]['status'],'duplicate_target')

    def test_source_change_after_run_remains_visible(self):
        self.s['amount_total']=101
        self.assertIn('amount_total',self.result()['rows'][0]['historical_source_changed_fields'])

    def test_whole_currency_rounding_preserved(self):
        self.assertTrue(audit.money_equal(100.1,100.4,1))
        self.assertFalse(audit.money_equal(100.1,100.6,1))

    def test_signed_native_invoice_and_credit_note(self):
        self.assertEqual(audit.signed_native({'move_type':'in_invoice','amount_total':100}),-100)
        self.assertEqual(audit.signed_native({'move_type':'out_refund','amount_total':100}),-100)
        self.assertEqual(audit.signed_native({'move_type':'in_refund','amount_total':100}),100)

    def test_sequence_not_certified_without_policy(self):
        self.s['move_type']=self.t['move_type']='out_invoice'
        self.assertIn('approved_sequence_policy_required',self.result()['rows'][0]['unverified'])

if __name__=='__main__':unittest.main()
