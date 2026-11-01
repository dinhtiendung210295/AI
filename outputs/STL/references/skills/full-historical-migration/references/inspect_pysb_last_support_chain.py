from complete_pysb_stock_migration import Completion,rid,index,OUT
from execute_pysb_stock_migration import save
import json
def main():
 m=Completion(); pid=43766
 ls=m.a.search_read('stock.move.line',[['company_id','=',1],['product_id','=',pid],['state','=','done'],['qty_done','>',0]],['move_id','lot_id','qty_done','product_uom_id','location_id','location_dest_id','package_id','result_package_id','owner_id'])
 ms=index(m.a.read('stock.move',list({rid(x['move_id']) for x in ls}),['date','picking_id','inventory_id','name']))
 lotids={rid(x['lot_id']) for x in ls if x['lot_id']}; lots=index(m.a.read('stock.production.lot',list(lotids),['name']))
 rows=[{'move':ms[rid(x['move_id'])],'line':x,'lot_name':lots.get(rid(x['lot_id']),{}).get('name'),'mapped_target_move':m.maps['stock.move'].get(rid(x['move_id']))} for x in ls if '2026-06-01'<=ms[rid(x['move_id'])]['date']<'2026-08-01']
 rows.sort(key=lambda x:(x['move']['date'],x['move']['id']))
 target=m.b.search_read('stock.quant',[['company_id','=',1],['product_id','=',115572]],['quantity','location_id','lot_id','package_id','owner_id'])
 data={'source_rows':rows,'target_quants':target};save(OUT/'last-support-chain-proof.json',data);print(json.dumps(data,ensure_ascii=False))
if __name__=='__main__':main()
