"""Replay one evidenced source inventory adjustment, then finish its blocked MO."""
import runpy,json
from pathlib import Path
from xmlrpc.client import Fault
ROOT=Path(__file__).resolve().parents[6]
H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/complete_pysb_stock_migration.py'))
def main():
 m=H['Completion']();rid=H['rid'];require=H['require'];m.prepare_validation()
 source=m.a.read('stock.move',[508338],['company_id','state','date','product_id','location_id','location_dest_id','quantity_done'])[0]
 require(rid(source['company_id'])==1 and source['state']=='done' and rid(source['product_id'])==46624 and abs(source['quantity_done']-23.056)<1e-6,'Source adjustment changed')
 require(m.maps['product.product'][46624]==110783 and m.maps['stock.location'][rid(source['location_dest_id'])]==5,'Wrong adjustment mapping')
 external=m.b.call('ir.model.data','search_read',[[['module','=','pysb_v14'],['name','=','stock_move_508338']]],{'fields':['res_id']})
 domain=[['company_id','=',1],['product_id','=',110783],['is_inventory','=',True]]
 if not external:
  q=m.b.search_read('stock.quant',[['company_id','=',1],['product_id','=',110783],['location_id','=',5],['lot_id','=',False],['package_id','=',False],['owner_id','=',False]],['quantity'])
  require(len(q)==1 and abs(q[0]['quantity'])<1e-6,'Inventory changed; stop before adjusting')
  before=m.b.call('stock.move','search',[domain]);m.j['source_adjustment_508338']={'source':source,'before_quant':q,'before_moves':before,'status':'before_inventory'};m.persist()
  m.mutate('stock.quant','write',[[q[0]['id']],{'inventory_quantity':23.06}],{'context':{'inventory_mode':True}})
  try:m.mutate('stock.quant','action_apply_inventory',[[q[0]['id']]],{'context':{'inventory_mode':True,'inventory_name':'v14 508338: STOCK ADJ - AFTER STOCK CHECK (5058A)'}})
  except Fault as exc:
   if 'cannot marshal None' not in str(exc):raise
   # Odoo returns None after commit; read back rather than calling again.
  after=m.b.search_read('stock.move',domain,['state','quantity','location_id','location_dest_id','move_line_ids']);created=[x for x in after if x['id'] not in before]
  require(len(created)==1 and created[0]['state']=='done' and abs(created[0]['quantity']-23.06)<1e-6 and rid(created[0]['location_id'])==11 and rid(created[0]['location_dest_id'])==5,'Adjustment result uncertain')
  adj=created[0];m.attach('stock.move',[(508338,adj['id'])])
 else:adj=m.b.read('stock.move',[external[0]['res_id']],['state','quantity','location_id','location_dest_id','move_line_ids'])[0]
 require(adj['state']=='done' and abs(adj['quantity']-23.06)<1e-6,'Existing adjustment differs')
 m.mutate('stock.move','write',[[adj['id']],{'date':source['date']}])
 m.mutate('stock.move.line','write',[adj['move_line_ids'],{'date':source['date']}])
 m.j['supplementary_inventory_adjustments']=[{'source_move':508338,'target_move':adj['id'],'date':source['date'],'source_qty':23.056,'target_qty':23.06,'deltas':[[[110783,11,False,False,False],-23.06],[[110783,5,False,False,False],23.06]]}];m.persist()
 event={'kind':'mo','source':21829,'target':533,'reference':'HQ/MO/24396','date':m.mos[21829]['date_finished']}
 state=m.b.read('mrp.production',[533],['state','company_id'])[0];require(rid(state['company_id'])==1,'Wrong MO company')
 if state['state']!='done':
  mids,lines=m.verify_details([event])
  q=m.b.search_read('stock.quant',[['company_id','=',1],['product_id','=',110783],['location_id','=',5],['lot_id','=',False],['package_id','=',False]],['quantity']);require(sum(x['quantity'] for x in q)>=20.86,'Insufficient stock after adjustment')
  result=m.mutate('mrp.production','button_mark_done',[[533]],{'context':{'skip_backorder':True,'skip_redirection':True}})
  require(not isinstance(result,dict),'Unexpected MO wizard; read back before continuing')
 require(m.b.read('mrp.production',[533],['state'])[0]['state']=='done','MO not completed')
 m.mutate('mrp.production','write',[[533],{'date_finished':event['date']}])
 mids=[i for i in m.mos[21829]['move_raw_ids']+m.mos[21829]['move_finished_ids'] if i in m.maps['stock.move']]
 for i in mids:m.mutate('stock.move','write',[[m.maps['stock.move'][i]],{'date':m.mm[i]['date']}])
 for x in m.expected(event):m.mutate('stock.move.line','write',[[m.maps['stock.move.line'][x['id']]],{'date':x['date']}])
 key=m.eventkey(event);m.j['event_results'][key]={'status':'done',**event};m.j['completed_events']=sorted(set(m.j['completed_events'])|{key})
 q=m.b.search_read('stock.quant',[['company_id','=',1],['product_id','=',110783],['location_id','=',5]],['quantity']);require(abs(sum(x['quantity'] for x in q)-2.2)<1e-6,'Unexpected raw balance')
 m.j['source_adjustment_508338'].update(status='adjustment_and_MO_done',target_adjustment=adj,raw_remaining=q);m.persist();print(json.dumps({'adjustment_move':adj['id'],'MO':533,'state':'done','remaining':2.2}),flush=True)
if __name__=='__main__':main()
