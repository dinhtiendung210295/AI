import copy
import runpy
import unittest
from pathlib import Path
M=runpy.run_path(str(Path(__file__).resolve().parents[1]/'hq_mts_delivery_proof.py'))


class Tests(unittest.TestCase):
    def fixture(self):
        wh={'id':1,'company_id':1,'lot_stock_id':5,'delivery_route_id':3,'delivery_steps':'pick_pack_ship','route_ids':[1,3]}
        loc=[{'id':2,'usage':'customer','location_id':False}]
        root={'id':9,'active':True,'action':'pull','procure_method':'make_to_stock','route_id':3,'location_src_id':5,'location_dest_id':2,'warehouse_id':1,'company_id':1}
        manufacture=dict(root,id=5,action='manufacture',procure_method='make_to_order',route_id=5,location_src_id=False,location_dest_id=5)
        archive=dict(root,id=3,active=False,procure_method='make_to_order',route_id=1)
        pick={'warehouse_id':1,'default_location_src_id':5,'default_location_dest_id':9}
        return wh,loc,[root,manufacture,archive],pick

    def test_stock_manufacture_rule_does_not_apply_to_customer(self):
        proof=M['evaluate'](*self.fixture())
        self.assertTrue(proof['ready'])
        self.assertEqual([x['id'] for x in proof['applicable_customer_rules']],[9])

    def test_competing_active_mto_blocks(self):
        wh,loc,rules,pick=self.fixture();rules[-1]['active']=True
        self.assertFalse(M['evaluate'](wh,loc,rules,pick)['ready'])

    def test_missing_or_changed_root_blocks(self):
        for field,value in [('active',False),('procure_method','make_to_order'),('location_src_id',8)]:
            wh,loc,rules,pick=self.fixture();rules[0][field]=value
            self.assertFalse(M['evaluate'](wh,loc,rules,pick)['ready'])

    def test_other_warehouse_or_pick_layout_blocks(self):
        wh,loc,rules,pick=self.fixture();wh['id']=2
        self.assertFalse(M['evaluate'](wh,loc,rules,pick)['ready'])
        wh,loc,rules,pick=self.fixture();pick['default_location_dest_id']=2
        self.assertFalse(M['evaluate'](wh,loc,rules,pick)['ready'])

    def test_stock_inside_customer_ancestors_blocks(self):
        wh,loc,rules,pick=self.fixture();loc.append({'id':5,'usage':'internal'})
        self.assertFalse(M['evaluate'](wh,loc,rules,pick)['ready'])


if __name__=='__main__':unittest.main()
