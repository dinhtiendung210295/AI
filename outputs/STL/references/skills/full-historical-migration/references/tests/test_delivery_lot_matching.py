import copy,runpy,unittest
from pathlib import Path
M=runpy.run_path(str(Path(__file__).resolve().parents[1]/'delivery_lot_matching.py'))
class Tests(unittest.TestCase):
    def rows(self):return [{'id':10,'name':'10082026','product_id':[20,'P'],'company_id':[1,'C']}]
    def test_exact_api_name_and_pinned_identity(self):self.assertEqual(M['select']('10082026',20,1,self.rows(),10)['id'],10)
    def test_duplicate_exact_names_block(self):
        rows=self.rows();rows.append(dict(rows[0],id=11))
        with self.assertRaises(RuntimeError):M['select']('10082026',20,1,rows,10)
    def test_other_product_company_or_trimmed_name_never_match(self):
        for change in [{'name':'10082026 '},{'product_id':21},{'company_id':2}]:
            rows=self.rows();rows[0].update(change)
            with self.subTest(change=change),self.assertRaises(RuntimeError):M['select']('10082026',20,1,rows,10)
    def test_conflicting_external_identity_blocks(self):
        with self.assertRaises(RuntimeError):M['select']('10082026',20,1,self.rows(),11)
if __name__=='__main__':unittest.main()
