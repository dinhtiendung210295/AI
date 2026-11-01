import copy
import runpy
import unittest
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
guard=runpy.run_path(str(BASE/'unconsumed_mo_recovery_guard.py'))['guard']
choose=runpy.run_path(str(BASE/'native_mo_placeholder_matching.py'))['choose']


class Tests(unittest.TestCase):
    def test_unconsumed_recovery(self):
        mo={'id':1,'state':'to_close','qty_produced':0,'move_raw_ids':[1],'move_finished_ids':[2],'name':'MO'}
        moves=[{'state':'assigned','picked':False}]
        guard(mo,moves,moves,[],{'name':'MO'})
        for bad in [dict(mo,state='done'),dict(mo,qty_produced=1),dict(mo,move_raw_ids=[])]:
            with self.assertRaises(RuntimeError):guard(bad,moves,moves,[],{'name':'MO'})

    def test_previous_done_attempt_and_picked_block_recovery(self):
        mo={'id':1,'state':'to_close','qty_produced':0,'move_raw_ids':[1],'move_finished_ids':[2]}
        moves=[{'state':'assigned','picked':False}]
        with self.assertRaises(RuntimeError):guard(mo,moves,moves,[{'model':'mrp.production','method':'button_mark_done','args':[[1]]}],{})
        with self.assertRaises(RuntimeError):guard(mo,moves,[{'state':'assigned','picked':True}],[],{})

    def candidates(self):
        value={'id':2,'product_uom_qty':5.,'state':'assigned','picked':False,'move_orig_ids':[],'move_dest_ids':[],'origin_returned_move_id':False}
        return [value,dict(value,id=1)]

    def test_interchangeable_and_existing_binding(self):
        self.assertEqual(choose(self.candidates(),5.)[0]['id'],1)
        self.assertEqual(choose(self.candidates(),5.,2)[0]['id'],2)
        with self.assertRaises(RuntimeError):choose(self.candidates(),5.,9)

    def test_linked_picked_or_different_demand_cannot_be_interchanged(self):
        for field,value in [('state','done'),('picked',True),('move_orig_ids',[8]),('move_dest_ids',[9]),('origin_returned_move_id',4)]:
            rows=self.candidates();rows[0][field]=value
            with self.subTest(field=field),self.assertRaises(RuntimeError):choose(rows,5.)
        rows=self.candidates()
        rows[0]['product_uom_qty']=4.
        self.assertEqual(choose(rows,5.)[0]['id'],1)
        with self.assertRaises(RuntimeError):choose(rows,3.)
        with self.assertRaises(RuntimeError):choose(rows,5.,2)


if __name__=='__main__':unittest.main()
