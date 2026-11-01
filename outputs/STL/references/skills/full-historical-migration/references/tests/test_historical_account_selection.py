import unittest,runpy
from pathlib import Path
M=runpy.run_path(str(Path(__file__).parents[1]/'historical_account_selection.py'))
class TestHistoricalSelection(unittest.TestCase):
 def terms(self):
  return {'source_terms':[{'id':38,'name':'14 Days','line_ids':[40]}],'target_terms':[{'id':2,'name':'15 Days','active':True,'line_ids':[2]}],'source_term_lines':[{'id':40,'value':'balance','value_amount':0,'option':'day_after_invoice_date','days':14}],'target_term_lines':[{'id':2,'value':'percent','value_amount':100,'delay_type':'days_after','nb_days':14}],'term_inferences':[{'source_id':38,'evidence':[{'target_term':[2,'15 Days']}]}]}
 def test_different_name_same_schedule(self):self.assertEqual(M['term_mapping'](self.terms()),{38:2})
 def test_different_schedule(self):
  d=self.terms();d['target_term_lines'][0]['nb_days']=15;self.assertEqual(M['term_mapping'](d),{})
 def test_term_ambiguity(self):
  d=self.terms();d['term_inferences'][0]['evidence'].append({'target_term':[3,'other']});self.assertEqual(M['term_mapping'](d),{})
 def data(self):
  return {'source_accounts':[{'id':21,'internal_group':'income'}],'target_accounts':[{'id':85,'code':'5010','internal_group':'income','active':True,'company_ids':[1]},{'id':3820,'code':'v14','internal_group':'asset','active':True,'company_ids':[1]}],'account_inferences':[{'source_id':21,'evidence':[{'target_account':[85,'x'],'product':[1,'p'],'move_type':'out_invoice'},{'target_account':[3820,'v14'],'product':[1,'p'],'move_type':'out_invoice'}]}]}
 def test_business(self):self.assertEqual(M['select'](self.data(),21,1,'out_invoice')['target_account'],85)
 def test_archived(self):
  d=self.data();d['target_accounts'][0]['active']=False;self.assertIsNone(M['select'](d,21,1,'out_invoice'))
 def test_wrong_company(self):
  d=self.data();d['target_accounts'][0]['company_ids']=[2];self.assertIsNone(M['select'](d,21,1,'out_invoice'))
 def test_ambiguous(self):
  d=self.data();d['target_accounts'].append(dict(d['target_accounts'][0],id=86));d['account_inferences'][0]['evidence'].append({'target_account':[86,'x'],'product':[1,'p'],'move_type':'out_invoice'});self.assertIsNone(M['select'](d,21,1,'out_invoice'))
 def test_product_type_disambiguates(self):
  d=self.data();d['target_accounts'].append(dict(d['target_accounts'][0],id=86));d['account_inferences'][0]['evidence'].append({'target_account':[86,'x'],'product':[2,'p'],'move_type':'out_invoice'});self.assertEqual(M['select'](d,21,2,'out_invoice')['target_account'],86)
