"""Exactly two newly authorized ED42 masters; never reactivate old records."""
import runpy,json
from pathlib import Path
BASE=Path(__file__).parent
R=runpy.run_path(str(BASE/'migrate_pysb_independent_receipts.py'));I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'))
OUT=R['OUT'];rid=R['rid']
class Run(R['Run']):
 def __init__(self):
  super().__init__()
  self.j=R['load']('ed42-new-master-journal.json') if (OUT/'ed42-new-master-journal.json').exists() else {'database':self.b.r.db,'company_id':1,'authorization':'User: v19 nen su dung record moi luon','operations':[],'products':{},'maps':{}}
  self.uncertain=[x for x in self.j['operations'] if x['status'] in ['intent','uncertain']]
 def persist(self):I['save']('ed42-new-master-journal.json',self.j)
 def mutate(self,model,method,args,**kwargs):
  if (model,method) not in [('product.template','create'),('ir.model.data','create')]:raise RuntimeError('Forbidden ED42 mutation')
  return super().mutate(model,method,args,**kwargs)
def main():
 r=Run();lock=runpy.run_path(str(BASE/'production_write_lock.py'))['acquire'](OUT)
 if r.uncertain:raise RuntimeError('Uncertain prior master write; read back before continuing')
 frozen=R['load']('ed42-new-master-source-preparation.json')
 if {x['id'] for x in frozen}!={54870,54871}:raise RuntimeError('Wrong master scope')
 live=r.a.read('product.product',[54870,54871],list(frozen[0]))
 if {x['id']:x for x in live}!={x['id']:x for x in frozen}:raise RuntimeError('Source master changed')
 old_source=r.a.read('product.product',[51810,51932],['categ_id'])
 old_target=r.b.read('product.product',[129962,129963],['categ_id','active','tracking','uom_id'])
 if any(rid(x['categ_id'])!=20 for x in old_source) or any(rid(x['categ_id'])!=134 or x['active'] or x['tracking']!='lot' or rid(x['uom_id'])!=473 for x in old_target):raise RuntimeError('ED42 family category proof changed')
 old_ids=r.b.scan('ir.model.data',[['module','=','v14_v2___export__'],['model','=','product.template'],['res_id','in',[130430,130431]]],['name','res_id'])
 if {x['name']:x['res_id'] for x in old_ids}!={'product_template_64460_ee72a6f2':130430,'product_template_64582_75d1af4c':130431}:raise RuntimeError('Old template identity proof failed')
 for s in frozen:
  sid=s['id'];stid=rid(s['product_tmpl_id']);key=str(sid)
  fields=['name','barcode','default_code','company_id','uom_id','tracking','type','is_storable','categ_id','sale_ok','purchase_ok','list_price','standard_price','taxes_id','supplier_taxes_id','description_sale','description_purchase','active']
  values={k:s[k] for k in ['name','barcode','default_code','sale_ok','purchase_ok','list_price','standard_price','description_sale','description_purchase','active']}
  values.update(company_id=1,uom_id=473,tracking='lot',type='consu',is_storable=True,categ_id=134,taxes_id=[(6,0,[])],supplier_taxes_id=[(6,0,[])])
  if s['taxes_id'] or s['supplier_taxes_id'] or rid(s['uom_id'])!=1059 or rid(s['uom_po_id'])!=1059 or rid(s['categ_id'])!=20:raise RuntimeError('Unexpected source product settings')
  names=['product_product_'+str(sid),'product_template_'+str(stid)]
  existing=r.b.scan('ir.model.data',[['module','=','pysb_v14'],['name','in',names]],['name','model','res_id'])
  if existing and key not in r.j['products']:raise RuntimeError('Master mapping already exists outside this journal')
  if key not in r.j['products']:
   duplicates=r.b.scan('product.product',[['company_id','in',[False,1]],['barcode','=',s['barcode']]],['name','barcode','active'])
   if duplicates:raise RuntimeError('Exact barcode exists; review before create')
   r.j['products'][key]={'source':s,'values':values,'phase':'intent_recorded'};r.persist()
   tid=r.mutate('product.template','create',[values]);r.j['products'][key].update(target_template=tid,phase='created');r.persist()
  row=r.j['products'][key];tid=row['target_template']
  actual=r.b.read('product.template',[tid],fields+['product_variant_ids'])[0]
  for k,v in values.items():
   if k in ['taxes_id','supplier_taxes_id']:
    if actual[k]:raise RuntimeError('Unexpected default taxes')
   elif k in ['company_id','uom_id','categ_id']:
    if rid(actual[k])!=v:raise RuntimeError('Master identity mismatch '+k)
   elif actual[k]!=v:raise RuntimeError('Master value mismatch '+k)
  if len(actual['product_variant_ids'])!=1:raise RuntimeError('Unexpected variants')
  pid=actual['product_variant_ids'][0]
  if r.b.read('product.product',[pid],['qty_available'])[0]['qty_available']:raise RuntimeError('New master unexpectedly has stock')
  vals=[]
  for model,source_id,target_id in [('product.template',stid,tid),('product.product',sid,pid)]:
   name=model.replace('.','_')+'_'+str(source_id)
   found=[x for x in existing if x['name']==name]
   if found:
    if len(found)!=1 or found[0]['res_id']!=target_id or found[0]['model']!=model:raise RuntimeError('XMLID mismatch')
   else:vals.append({'module':'pysb_v14','name':name,'model':model,'res_id':target_id,'noupdate':True})
  if vals:r.mutate('ir.model.data','create',[vals])
  row.update(target_product=pid,phase='verified',readback=actual);r.j['maps'].setdefault('product.product',{})[str(sid)]=pid;r.j['maps'].setdefault('product.template',{})[str(stid)]=tid;r.persist()
  print(json.dumps({'source':sid,'target':pid,'new_master_verified':True}),flush=True)
if __name__=='__main__':main()
