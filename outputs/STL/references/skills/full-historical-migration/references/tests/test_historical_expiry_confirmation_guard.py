import copy
import runpy
import unittest
from pathlib import Path
F=runpy.run_path(str(Path(__file__).resolve().parents[1]/'historical_expiry_confirmation_guard.py'))['authorize']


class Tests(unittest.TestCase):
    def fixture(self):
        approval={'scope_sha256':'frozen','company_id':1,'target_database':'py19-main-33843450','approved_source_mos':[22928]}
        source={'id':22928,'state':'done','company_id':1}
        mo={'id':1178,'state':'to_close','company_id':1,'qty_produced':0}
        warning={'res_model':'expiry.picking.confirmation','context':{'default_production_ids':[1178],'default_lot_ids':[[6,0,[24384]]]}}
        return [approval,'frozen',source,mo,[{'state':'assigned'}],warning,[24384]]

    def test_authorized_history_only(self):self.assertEqual(F(*self.fixture()),[24384])

    def test_no_approval_or_different_scope_blocks(self):
        for field,value in [('scope_sha256','other'),('approved_source_mos',[]),('target_database','staging'),('company_id',2)]:
            args=self.fixture();args[0][field]=value
            with self.subTest(field=field),self.assertRaises(RuntimeError):F(*args)

    def test_already_consumed_or_cancelled_blocks(self):
        for state in ['done','cancel']:
            args=self.fixture();args[3]['state']=state
            with self.assertRaises(RuntimeError):F(*args)
        args=self.fixture();args[3]['qty_produced']=1
        with self.assertRaises(RuntimeError):F(*args)
        args=self.fixture();args[4][0]['state']='done'
        with self.assertRaises(RuntimeError):F(*args)

    def test_wrong_lot_or_target_and_other_wizards_block(self):
        for mutation in ['lot','target','picking','model']:
            args=self.fixture();warning=args[5]
            if mutation=='lot':warning['context']['default_lot_ids']=[[6,0,[9]]]
            elif mutation=='target':warning['context']['default_production_ids']=[1179]
            elif mutation=='picking':warning['context']['default_picking_ids']=[1]
            else:warning['res_model']='mrp.production.backorder'
            with self.subTest(mutation=mutation),self.assertRaises(RuntimeError):F(*args)


if __name__=='__main__':unittest.main()
