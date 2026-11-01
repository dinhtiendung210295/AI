import unittest,runpy
from pathlib import Path
issues=runpy.run_path(str(Path(__file__).parents[1]/'delivery_line_provenance.py'))['issues']
class TestProvenance(unittest.TestCase):
 def test_single(self):
  self.assertEqual(issues([1,2],{1:{'move_dest_ids':[2]},2:{'sale_line_id':[7,'x']}}),[])
 def test_shared(self):
  rows={1:{'move_dest_ids':[2,3]},2:{'sale_line_id':[7,'x']},3:{'sale_line_id':[8,'x']}}
  self.assertEqual(issues([1,2,3],rows),[{'source_move':1,'downstream_source_lines':[7,8],'reason':'shared_internal_so_lines_require_merge_support'}])
 def test_outside_not_credited(self):
  self.assertEqual(issues([1],{1:{'move_dest_ids':[2]}})[0]['reason'],'missing_downstream_so_line')
 def test_cycle_terminates(self):
  self.assertEqual(issues([1,2],{1:{'move_dest_ids':[2]},2:{'move_dest_ids':[1],'sale_line_id':[7,'x']}}),[])
