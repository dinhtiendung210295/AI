import copy
import runpy
import unittest
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
C=runpy.run_path(str(BASE/'inventory_count_checks.py'))
M=runpy.run_path(str(BASE/'migrate_pysb_inventory_adjustments.py'))


class Tests(unittest.TestCase):
    def fixture(self):
        move={'id':10,'product_id':1,'product_uom':2,'quantity_done':3}
        detail={'product_uom_id':2,'qty_done':3,'lot_id':4}
        header={'id':5,'state':'done','company_id':1,'move_ids':[10]}
        count={'id':6,'inventory_id':5,'product_id':1,'product_uom_id':2,'location_id':7,'prod_lot_id':4,'package_id':False,'partner_id':False,'product_qty':8,'theoretical_qty':5}
        return move,detail,header,[count]

    def test_actual_positive_and_negative_count_delta(self):
        args=self.fixture();self.assertEqual(C['match_count'](*args,1,7)['id'],6)
        args[-1][0].update(product_qty=5,theoretical_qty=8)
        self.assertEqual(C['match_count'](*args,-1,7)['id'],6)

    def test_invented_stock_delta_not_accepted(self):
        args=self.fixture();args[0]['quantity_done']=4
        with self.assertRaises(RuntimeError):C['match_count'](*args,1,7)

    def test_ambiguous_or_unposted_source_count_not_accepted(self):
        args=self.fixture();args[-1].append(copy.deepcopy(args[-1][0]))
        with self.assertRaises(RuntimeError):C['match_count'](*args,1,7)
        args=self.fixture();args[2]['state']='draft'
        with self.assertRaises(RuntimeError):C['match_count'](*args,1,7)

    def test_direct_quant_quantity_and_master_edits_forbidden(self):
        run=M['Run'].__new__(M['Run'])
        for model,method,args in [('stock.quant','write',[[1],{'quantity':10}]),('stock.quant','create',[{'quantity':10}]),('product.product','write',[[1],{'tracking':'none'}]),('stock.move','write',[[1],{'product_uom_qty':10}])]:
            with self.subTest(model=model,method=method),self.assertRaises(RuntimeError):run.mutate(model,method,args)

    def test_verified_count_not_applied_twice(self):
        run=M['Run'].__new__(M['Run']);run.j={'groups':{'inventory:5':{'status':'verified_done'}}}
        run.mutate=lambda *a,**k:self.fail('No second inventory application')
        run.process({'group_key':'inventory:5'})

    def recovery_fixture(self):
        run=M['Run'].__new__(M['Run'])
        rec={'status':'prepared_unapplied','target_quants':[20],'before_move_floor':30,'before':[{'quant_id':20,'quant_before':{'quantity':3},'delta':1}]}
        group={'group_key':'inventory:5','event_utc':'2026-08-01 02:08:47','pending_moves':[10],'name':'Actual count'}
        run.j={'groups':{'inventory:5':rec}}
        run.plan={'groups':[group]}
        run.uncertain=[{'model':'stock.quant','method':'action_apply_inventory','args':[[20],group['event_utc']],'utc':'2026-10-24T16:30:00.123+00:00','status':'uncertain'}]
        class Reader:
            def scan(self,model,domain,fields):
                return [{'id':31,'state':'done','is_inventory':True,'inventory_name':'Actual count','quantity':1}] if model=='stock.move' else []
            def read(self,*args):return [{'id':20,'quantity':4,'reserved_quantity':0,'inventory_quantity_set':False}]
        run.b=Reader();run.persist=lambda:None
        run.mutate=lambda *a,**k:self.fail('Recovery must never reapply inventory')
        return run,rec

    def test_lost_response_recovered_without_second_delta(self):
        run,rec=self.recovery_fixture();finished=[]
        run.finish_applied=lambda group,row:finished.append(row)
        operation=run.uncertain[0]
        run.recover_applied('inventory:5')
        self.assertEqual(finished,[rec]);self.assertEqual(run.uncertain,[])
        self.assertEqual(operation['status'],'verified_applied_by_readback')

    def test_lost_response_wrong_delta_blocks_recovery(self):
        run,rec=self.recovery_fixture()
        run.b.read=lambda *args:[{'id':20,'quantity':5,'inventory_quantity_set':False}]
        run.finish_applied=lambda *args:self.fail('Unproven delta cannot finish')
        with self.assertRaises(RuntimeError):run.recover_applied('inventory:5')
        self.assertEqual(run.uncertain[0]['status'],'uncertain')

    def test_resume_applied_verification_does_not_apply_again(self):
        run,rec=self.recovery_fixture();rec['status']='done_pending_verification'
        operation=run.uncertain[0];operation['status']='returned'
        run.j['operations']=[operation];run.uncertain=[];finished=[]
        run.finish_applied=lambda group,row:finished.append(row)
        run.resume_verification('inventory:5')
        self.assertEqual(finished,[rec])

    def test_resume_verification_requires_single_returned_operation(self):
        run,rec=self.recovery_fixture();rec['status']='done_pending_verification'
        operation=run.uncertain[0];operation['status']='returned'
        run.j['operations']=[operation,copy.deepcopy(operation)];run.uncertain=[]
        run.finish_applied=lambda *args:self.fail('Duplicate apply history cannot finish')
        with self.assertRaises(RuntimeError):run.resume_verification('inventory:5')


if __name__=='__main__':unittest.main()
