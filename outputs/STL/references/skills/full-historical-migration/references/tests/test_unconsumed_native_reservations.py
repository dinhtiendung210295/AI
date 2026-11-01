import runpy,unittest,copy
from pathlib import Path
M=runpy.run_path(str(Path(__file__).parents[1]/'unconsumed_native_reservations.py'))
class Tests(unittest.TestCase):
    def fixture(self):
        m=dict(id=1,state='assigned',picked=False,company_id=1,quantity=3,move_line_ids=[2],product_id=3,location_id=5,location_dest_id=9)
        line=dict(id=2,move_id=1,state='assigned',picked=False,company_id=1,product_id=3,location_id=5,location_dest_id=9,quantity=3,owner_id=False,package_id=False,result_package_id=False)
        return m,line
    def test_native_unpicked_reservation_accepted(self):
        m,line=self.fixture();M['validate']([m],[line],[])
    def test_picked_done_owner_wrong_dimension_rejected(self):
        for field,value in [('picked',True),('state','done'),('owner_id',7),('product_id',4),('location_id',6),('quantity',-1)]:
            m,line=self.fixture();line[field]=value
            with self.assertRaises(RuntimeError):M['validate']([m],[line],[])
    def test_mapped_historical_or_missing_line_rejected(self):
        m,line=self.fixture()
        for lines,mapped in [([line],[2]),([],[])]:
            with self.assertRaises(RuntimeError):M['validate']([m],lines,mapped)
    def test_totals_or_native_execution_rejected(self):
        m,line=self.fixture();m['quantity']=4
        with self.assertRaises(RuntimeError):M['validate']([m],[line],[])
        m['quantity']=3;m['picked']=True
        with self.assertRaises(RuntimeError):M['validate']([m],[line],[])
    def test_physical_stock_delta_rejected(self):
        M['unchanged']({'key':3},{'key':3})
        with self.assertRaises(RuntimeError):M['unchanged']({'key':3},{'key':2})
if __name__=='__main__':unittest.main()
