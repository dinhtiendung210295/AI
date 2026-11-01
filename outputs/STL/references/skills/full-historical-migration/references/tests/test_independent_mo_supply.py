import copy
import runpy
import unittest
import tempfile
from pathlib import Path
M=runpy.run_path(str(Path(__file__).resolve().parents[1]/'prepare_pysb_independent_mos.py'))

class Tests(unittest.TestCase):
    def fixture(self,receipt_date='2026-08-03'):
        def move(i,date,src,dst):return {'id':i,'date':date,'product_id':[1,'Raw'],'state':'done'}
        def line(i,src,dst):return {'id':i,'move_id':[i,'Move'],'product_id':[1,'Raw'],'product_uom_id':[1,'Unit'],'qty_done':1,'location_id':[src,'L'],'location_dest_id':[dst,'L'],'lot_id':False,'package_id':False,'result_package_id':False,'owner_id':False}
        return {
            'discovery-manifest.json':{'maps':{'product.product':{'1':101},'uom.uom':{'1':1},'stock.location':{'1':1,'2':2,'3':3}}},
            'independent-receipts-journal.json':{'maps':{}},'opening-lot-resolution.json':{'maps':{'stock.lot':{}}},
            'source-moves.json':[move(1,'2026-08-02',1,3),move(2,'2026-08-02',3,2),move(3,receipt_date,3,1)],
            'source-mo-execution-details.json':[{'id':10,'name':'MO10','move_raw_ids':[1],'move_finished_ids':[2]}],
            'source-move-lines.json':[line(1,1,3),line(2,3,2),line(3,3,1)],
            'source-uom.uom.json':[{'id':1,'factor':1}], 'target-uom.uom.json':[{'id':1,'rounding':0.01}],
            'source-products.json':[{'id':1,'uom_id':[1,'Unit']}],
            'source-stock.location.json':[{'id':1,'usage':'internal'},{'id':2,'usage':'internal'},{'id':3,'usage':'supplier'}],
            'after-run-stock-coverage.json':{'results':[{'source_move_id':3,'target_move_id':103,'status':'verified'}]},
            'target-stock-moves-in-period.json':[], 'native-opening-comparison.json':{'rows':[]},'resolved-master-evidence.json':{'issues':[]},
            'source-mo-lot-metadata.json':{'changed_since_snapshot':[]},
            'detailed-opening-comparison.json':{'rows':[]},'source-detailed-opening-reconstruction.json':{'rows':[]},'scope.json':{}
        }
    def runplan_all(self,data):
        result={};g=M['main'].__globals__;old=(g['load'],g['save'],g['OUT'])
        g['load']=lambda n:copy.deepcopy(data[n]);g['save']=lambda n,v:result.update(v)
        with tempfile.TemporaryDirectory() as directory:
            g['OUT']=Path(directory)
            for name in data:(g['OUT']/name).touch()
            try:M['main']()
            finally:g['load'],g['save'],g['OUT']=old
        return result['rows']
    def runplan(self,data):return self.runplan_all(data)[0]
    def test_later_verified_receipt_cannot_supply_earlier_mo(self):
        row=self.runplan(self.fixture())
        self.assertFalse(row['eligible']);self.assertIn('historical_supply_shortage',row['errors'])
    def test_earlier_verified_receipt_supplies_mo(self):
        self.assertTrue(self.runplan(self.fixture('2026-08-01'))['eligible'])
    def test_unmigrated_delivery_still_reduces_historical_supply(self):
        data=self.fixture('2026-08-01')
        delivery=copy.deepcopy(data['source-moves.json'][0]);delivery.update(id=4,date='2026-08-01 12:00:00')
        line=copy.deepcopy(data['source-move-lines.json'][0]);line.update(id=4,move_id=[4,'Delivery'])
        data['source-moves.json'].append(delivery);data['source-move-lines.json'].append(line)
        self.assertFalse(self.runplan(data)['eligible'])
    def test_material_and_output_keep_distinct_historical_dates(self):
        data=self.fixture('2026-08-01');data['source-moves.json'][1]['date']='2026-08-03'
        self.assertTrue(self.runplan(data)['eligible'])
    def test_output_not_credited_until_its_actual_move_date(self):
        data=self.fixture('2026-08-01');data['source-moves.json'][1]['date']='2026-08-03'
        raw=copy.deepcopy(data['source-moves.json'][0]);raw.update(id=4,date='2026-08-02 12:00:00')
        finished=copy.deepcopy(raw);finished['id']=5
        rl=copy.deepcopy(data['source-move-lines.json'][0]);rl.update(id=4,move_id=[4,'Material'],location_id=[2,'Output'])
        fl=copy.deepcopy(data['source-move-lines.json'][1]);fl.update(id=5,move_id=[5,'Finished'])
        data['source-moves.json'].extend([raw,finished]);data['source-move-lines.json'].extend([rl,fl]);data['source-mo-execution-details.json'].append({'id':20,'name':'MO20','move_raw_ids':[4],'move_finished_ids':[5]})
        rows=self.runplan_all(data);self.assertTrue(rows[0]['eligible']);self.assertFalse(rows[1]['eligible'])

if __name__=='__main__':unittest.main()
