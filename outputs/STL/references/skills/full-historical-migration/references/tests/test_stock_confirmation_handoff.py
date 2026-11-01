import json,runpy,tempfile,unittest
from pathlib import Path
apply=runpy.run_path(str(Path(__file__).parents[1]/'stock_confirmation_handoff.py'))['apply']

class Tests(unittest.TestCase):
    def setup_evidence(self,path):
        phase=path/'phases';phase.mkdir()
        identity=dict(source_database='paoyeang_live',target_database='py19-main-33843450',company_id=1,scope_hash='scope')
        (phase/'so-confirmation-handoff.json').write_text(json.dumps(dict(identity=identity,maps={'res.partner':{'1':10},'uom.uom':{'1087':470},'res.users':{'2':9}})),encoding='utf8')
        (phase/'confirm-so-gate.json').write_text(json.dumps(dict(**identity,status='fully_passed',live_verification_complete=True)),encoding='utf8')
    def test_only_warehouse_relevant_identities_are_merged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);self.setup_evidence(path)
            maps={'res.partner':{2:20},'uom.uom':{1:1},'res.users':{2:2}}
            result=apply(maps,path)
            self.assertEqual(result['res.partner'],{1:10,2:20})
            self.assertEqual(result['uom.uom'],{1:1})
            self.assertEqual(result['res.users'],{2:2})
    def test_existing_identity_conflict_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);self.setup_evidence(path)
            with self.assertRaisesRegex(RuntimeError,'conflicts'):apply({'res.partner':{'1':99}},path)

if __name__=='__main__':unittest.main()
