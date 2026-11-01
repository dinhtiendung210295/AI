"""Exactly three authorized tracking changes; no quant/lot rewrites."""
import runpy,json
from pathlib import Path
BASE=Path(__file__).parent
R=runpy.run_path(str(BASE/'migrate_pysb_independent_receipts.py'));I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'));OUT=I['OUT'];rid=R['rid']
SCOPE={115235:(54456,115703,'serial'),116236:(49431,116704,'lot'),130168:(54662,130636,'serial')}
class Run(R['Run']):
 def __init__(self):
  super().__init__();self.j=R['load']('tracking-change-journal.json') if (OUT/'tracking-change-journal.json').exists() else {'database':self.b.r.db,'company_id':1,'authorization':'User explicitly approved MIMAKI serial, PTC lot, AINKJET serial; PP PRIMER remains none','operations':[],'products':{}}
  self.uncertain=[x for x in self.j['operations'] if x['status'] in ['intent','uncertain']]
 def persist(self):I['save']('tracking-change-journal.json',self.j)
 def mutate(self,model,method,args,**kwargs):
  if model!='product.template' or method!='write' or len(args[0])!=1 or args[0][0] not in [x[1] for x in SCOPE.values()] or set(args[1])!={'tracking'}:raise RuntimeError('Forbidden tracking mutation')
  return super().mutate(model,method,args,**kwargs)
def main():
 r=Run();lock=runpy.run_path(str(BASE/'production_write_lock.py'))['acquire'](OUT)
 if r.uncertain:raise RuntimeError('Read back uncertain change before continuing')
 for pid,(sid,tid,tracking) in SCOPE.items():
  before=r.b.read('product.product',[pid],['name','tracking','product_tmpl_id','company_id','qty_available'])[0]
  if rid(before['product_tmpl_id'])!=tid or rid(before['company_id']) not in ([False] if pid==130168 else [1]):raise RuntimeError('Wrong product identity')
  quants=r.b.scan('stock.quant',[['product_id','=',pid],['company_id','=',1]],['quantity','reserved_quantity','lot_id','location_id','owner_id','package_id'])
  if r.b.call('stock.move','search_count',[[['product_id','=',pid],['company_id','=',1],['state','not in',['done','cancel']]]]):raise RuntimeError('Open stock moves require review')
  locations={x['id']:x['usage'] for x in r.b.read('stock.location',[rid(q['location_id']) for q in quants],['usage'])}
  internal=[q for q in quants if locations[rid(q['location_id'])] in ['internal','transit'] and q['quantity']]
  if any(q['reserved_quantity'] for q in quants):raise RuntimeError('Unexpected reservation')
  if pid==115235:
   if len(internal)!=1 or internal[0]['quantity']!=1 or rid(internal[0]['lot_id'])!=28047:raise RuntimeError('MIMAKI stock/serial changed')
   lot=r.b.read('stock.lot',[28047],['name','product_id'])[0]
   if lot['name']!='JN58E169' or rid(lot['product_id'])!=pid:raise RuntimeError('Serial identity changed')
  elif internal:raise RuntimeError('Previously empty product now has stock')
  key=str(pid)
  if before['tracking']==tracking:
   if key not in r.j['products']:raise RuntimeError('Tracking changed outside this journal; review')
  elif before['tracking']=='none':
   r.j['products'][key]={'source_product':sid,'before':before,'quants_before':quants,'requested_tracking':tracking,'phase':'prepared'};r.persist()
   r.mutate('product.template','write',[[tid],{'tracking':tracking}])
  else:raise RuntimeError('Unexpected existing tracking')
  after=r.b.read('product.product',[pid],list(before))[0]
  actual=r.b.read('stock.quant',[q['id'] for q in quants],list(quants[0])) if quants else []
  all_after=r.b.scan('stock.quant',[['product_id','=',pid],['company_id','=',1]],['quantity','reserved_quantity','lot_id','location_id','owner_id','package_id'])
  if after['tracking']!=tracking or after['qty_available']!=before['qty_available'] or {q['id']:q for q in actual}!={q['id']:q for q in quants} or {q['id']:q for q in all_after}!={q['id']:q for q in quants}:raise RuntimeError('Tracking or stock readback mismatch')
  r.j['products'][key].update(after=after,phase='verified_stock_unchanged');r.persist()
  print(json.dumps({'product':pid,'tracking':tracking,'stock_unchanged':True}),flush=True)
 pp=r.b.read('product.product',[116045],['tracking','qty_available'])[0]
 if pp['tracking']!='none':raise RuntimeError('PP PRIMER must remain untracked')
 I['save']('operator-pp-primer-untracked-approval.json',{'approved':True,'source_product':54465,'target_product':116045,'tracking':'none','source_lot_metadata_retained_in_evidence':True,'policy':'User authorizes untracked execution. Any actual source/target lot difference must be individually recorded and independently verified as approved exception; no fake lot or stock allocation. Quantity, location, dates, package and owner still require proof.','target_readback':pp})
if __name__=='__main__':main()
