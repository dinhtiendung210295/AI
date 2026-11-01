"""Targeted recovery of MO 584; preserve already posted raw consumption."""
from execute_pysb_stock_migration import Migration,require,rid,save,OUT
import json

def main():
 m=Migration();require(m.maps['mrp.production'][21709]==584 and m.maps['mrp.production'][21789]==585,'Wrong MO mapping')
 states=m.b.read('mrp.production',[584,585],['state','product_qty','qty_producing','extra_cost'])
 raw=m.b.read('stock.move',[17403],['state','quantity','value','product_id','move_line_ids'])
 finished=m.b.read('stock.move',[17405],['state','quantity','move_line_ids'])
 require(raw[0]['state']=='done' and raw[0]['quantity']==10,'Raw consumption changed')
 require(states[0]['state']=='cancel' and finished[0]['state']=='cancel' and not finished[0]['move_line_ids'],'Recovery state changed')
 require(states[1]['state'] in ['confirmed','progress','to_close'],'Second MO state changed')
 m.j['resumed_mo_recovery']={'status':'intent','raw_before':raw,'finished_before':finished,'mo_before':states};m.persist()
 source=m.mos[21709]
 m.mutate('stock.move','write',[[17405],{'state':'confirmed','picked':False}])
 m.mutate('mrp.production','write',[[584],{'state':'confirmed','extra_cost':raw[0]['value']/source['product_qty'],'date_start':source['date_start'] or source['date_planned_start'],'date_finished':source['date_finished']}])
 lines=[x for x in m.ml.values() if rid(x['move_id'])==505904 and x['qty_done']>0]
 require(len(lines)==1,'Unexpected finished source lines')
 x=lines[0]
 vals={'company_id':1,'move_id':17405,'product_id':m.maps['product.product'][rid(x['product_id'])],'product_uom_id':m.maps['uom.uom'][rid(x['product_uom_id'])],'location_id':m.maps['stock.location'][rid(x['location_id'])],'location_dest_id':m.maps['stock.location'][rid(x['location_dest_id'])],'quantity':x['qty_done'],'lot_id':False,'picked':False,'date':x['date']}
 tid=m.mutate('stock.move.line','create',[vals]);m.maps['stock.move.line'][x['id']]=tid;m.persist();m.attach('stock.move.line',[(x['id'],tid)])
 m.mutate('stock.move','write',[[17406],{'picked':False}])
 check=m.b.read('mrp.production',[584,585],['state','qty_produced','qty_producing'])
 require(all(x['state'] in ['confirmed','progress','to_close'] and x['qty_produced']==0 for x in check),'Finished still counted as produced')
 require(m.b.read('stock.move',[17403],['state','quantity','value','product_id','move_line_ids'])==raw,'Raw changed during recovery')
 m.j['resumed_mo_recovery'].update(status='prepared',finished_new_line=tid,check=check);m.persist();print(json.dumps(check))
if __name__=='__main__':main()
