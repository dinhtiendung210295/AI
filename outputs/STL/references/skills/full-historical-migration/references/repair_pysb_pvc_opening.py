"""Exactly the authorized missing 50 UNIT opening, no master or direct quant edits."""
import runpy,json
from pathlib import Path
BASE=Path(__file__).parent
R=runpy.run_path(str(BASE/'migrate_pysb_independent_receipts.py'));I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'));OUT=I['OUT'];rid=R['rid']
DATE='2026-06-30 15:59:59'
FIELDS=['product_id','location_id','lot_id','owner_id','package_id','quantity','reserved_quantity','inventory_quantity','inventory_quantity_set']
DOMAIN=[['company_id','=',1],['product_id','=',112635]]
class Run(R['Run']):
 def __init__(self):
  super().__init__();self.j=R['load']('pvc-opening-correction-journal.json') if (OUT/'pvc-opening-correction-journal.json').exists() else {'database':self.b.r.db,'company_id':1,'operations':[],'status':'not_started','approval_file':'operator-pvc-opening-approval.json'}
  self.uncertain=[x for x in self.j['operations'] if x['status'] in ['intent','uncertain']]
 def persist(self):I['save']('pvc-opening-correction-journal.json',self.j)
 def mutate(self,model,method,args,context=None,jsonrpc=False):
  allowed={('stock.quant','create'),('stock.quant','action_apply_inventory'),('stock.move','write'),('stock.move.line','write'),('ir.model.data','create')}
  if (model,method) not in allowed:raise RuntimeError('Forbidden opening mutation')
  if model=='stock.quant' and method=='create' and args!=[{'product_id':112635,'location_id':9,'lot_id':False,'owner_id':False,'package_id':False,'inventory_quantity':50.0,'user_id':self.b.r.uid}]:raise RuntimeError('Wrong count input')
  if model in ['stock.move','stock.move.line'] and args[1]!={'date':DATE}:raise RuntimeError('Only authorized opening date may be restored')
  return super().mutate(model,method,args,context={**(context or {}),'inventory_mode':True,'inventory_name':'PYSB v14 missing opening PVC 50 UNIT - approved correction'},jsonrpc=jsonrpc)
def historical(reader,pid,date):
 return reader.call('product.product','read',[[pid]],{'fields':['qty_available'],'context':{'allowed_company_ids':[1],'to_date':date,'active_test':False}})[0]['qty_available']
def main():
 r=Run();lock=runpy.run_path(str(BASE/'production_write_lock.py'))['acquire'](OUT)
 if r.j['status']=='verified':print(json.dumps({'opening_already_verified':True}));return
 if r.uncertain or r.j['status']!='not_started':raise RuntimeError('Prior opening attempt needs readback; never reapply automatically')
 approval=R['load']('operator-pvc-opening-approval.json')
 for field,value in {'approved':True,'source_product':51469,'target_product':112635,'source_location':12,'target_location':9,'quantity':50,'unit_id':1}.items():
  if approval.get(field)!=value:raise RuntimeError('Opening permission scope mismatch')
 product=r.b.read('product.product',[112635],['tracking','is_storable','uom_id','company_id','standard_price','cost_method','valuation','property_stock_inventory'])[0]
 if product['tracking']!='none' or not product['is_storable'] or rid(product['uom_id'])!=1 or rid(product['company_id'])!=1 or product['standard_price']!=.7 or product['cost_method']!='average' or product['valuation']!='periodic' or rid(product['property_stock_inventory'])!=11:raise RuntimeError('Native accounting/master preflight changed')
 before=r.b.scan('stock.quant',DOMAIN,FIELDS)
 if before:raise RuntimeError('PVC now has quant/count input; review rather than overwrite')
 moves=r.b.scan('stock.move',DOMAIN,['state','quantity','date','move_line_ids'])
 if any(x['state']!='done' or abs(x['quantity'])>1e-8 for x in moves):raise RuntimeError('Unexpected existing stock activity')
 source_quantities=[historical(r.a,51469,cutoff) for cutoff in [DATE,'2026-07-31 15:59:59']]
 target_quantities=[historical(r.b,112635,cutoff) for cutoff in [DATE,'2026-07-31 15:59:59']]
 if any(abs(q-50)>1e-6 for q in source_quantities) or any(abs(q)>1e-6 for q in target_quantities):raise RuntimeError('Opening difference no longer exactly 50')
 accounting_before=r.b.call('account.move','search_count',[[['company_id','=',1]]])
 name='opening_correction_pvc_51469_20260701'
 if r.b.scan('ir.model.data',[['module','=','pysb_v14'],['name','=',name]],['res_id']):raise RuntimeError('Existing correction identity outside journal')
 r.j.update(status='preparing',before_product=product,before_quants=before,before_move_ids=[x['id'] for x in moves],source_openings=source_quantities,target_openings_before=target_quantities,expected_stock_value=35.0,expected_new_account_moves=0);r.persist()
 qid=r.mutate('stock.quant','create',[{'product_id':112635,'location_id':9,'lot_id':False,'owner_id':False,'package_id':False,'inventory_quantity':50.0,'user_id':r.b.r.uid}]);r.j['target_quant']=qid;r.persist()
 staged=r.b.read('stock.quant',[qid],FIELDS)[0]
 if staged['quantity'] or staged['reserved_quantity'] or staged['inventory_quantity']!=50 or not staged['inventory_quantity_set']:raise RuntimeError('Wrong staged count')
 r.mutate('stock.quant','action_apply_inventory',[[qid]],jsonrpc=True)
 after_moves=r.b.scan('stock.move',DOMAIN,['state','quantity','date','product_id','product_uom','location_id','location_dest_id','move_line_ids','value','account_move_id'])
 new=[x for x in after_moves if x['id'] not in r.j['before_move_ids']]
 if len(new)!=1:raise RuntimeError('Unexpected number of inventory moves')
 move=new[0]
 if move['state']!='done' or move['quantity']!=50 or rid(move['product_id'])!=112635 or rid(move['product_uom'])!=1 or rid(move['location_id'])!=11 or rid(move['location_dest_id'])!=9 or abs(move['value']-35)>1e-6 or move['account_move_id']:raise RuntimeError('Native quantity/valuation result differs')
 details=r.b.read('stock.move.line',move['move_line_ids'],['state','product_id','product_uom_id','quantity','location_id','location_dest_id','lot_id','owner_id','package_id','result_package_id'])
 if len(details)!=1 or details[0]['quantity']!=50 or any(details[0][f] for f in ['lot_id','owner_id','package_id','result_package_id']) or rid(details[0]['location_id'])!=11 or rid(details[0]['location_dest_id'])!=9:raise RuntimeError('Opening dimensions differ')
 r.j.update(target_move=move['id'],target_lines=move['move_line_ids'],status='applied_once');r.persist()
 r.mutate('stock.move.line','write',[move['move_line_ids'],{'date':DATE}]);r.mutate('stock.move','write',[[move['id']],{'date':DATE}])
 r.mutate('ir.model.data','create',[{'module':'pysb_v14','name':name,'model':'stock.move','res_id':move['id'],'noupdate':True}])
 after=r.b.scan('stock.quant',DOMAIN,FIELDS)
 internal=[x for x in after if rid(x['location_id'])==9]
 if len(internal)!=1 or internal[0]['quantity']!=50 or internal[0]['reserved_quantity'] or any(internal[0][f] for f in ['lot_id','owner_id','package_id']):raise RuntimeError('Internal stock readback differs')
 for cutoff in [DATE,'2026-07-31 15:59:59']:
  if abs(historical(r.b,112635,cutoff)-50)>1e-6:raise RuntimeError('Historical opening still differs')
 if r.b.call('account.move','search_count',[[['company_id','=',1]]])!=accounting_before:raise RuntimeError('Unexpected accounting move created')
 final_product=r.b.read('product.product',[112635],list(product))[0]
 if final_product!=product:raise RuntimeError('Product settings/cost changed')
 final_move=r.b.read('stock.move',[move['id']],['date','quantity','value','account_move_id'])[0]
 dates=r.b.read('stock.move.line',move['move_line_ids'],['date'])
 if final_move['date']!=DATE or any(x['date']!=DATE for x in dates):raise RuntimeError('Historical dates differ')
 r.j.update(status='verified',after_quants=after,after_product=final_product,after_move=final_move,after_line_dates=dates,target_openings_after=[50.0,50.0],account_moves_created=0);r.persist()
 print(json.dumps({'pvc_opening_repaired':True,'target_move':move['id'],'quantity':50,'date':DATE,'native_stock_value':35,'account_moves_created':0}),flush=True)
if __name__=='__main__':main()
