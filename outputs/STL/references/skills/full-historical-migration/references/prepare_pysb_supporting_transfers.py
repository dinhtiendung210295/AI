"""Separate ledger for authorized supporting transfers; reuse reviewed preparation."""
from execute_pysb_stock_migration import Migration,load,save,OUT,rid,require,index,ROOT,chunks
def main():
 m=Migration();d=load('supporting-stock-discovery.json');require(not d.get('discovery_only'), 'Discovery-only coverage: review category, dependencies and approve an execution change set before replay')
 source_lots=m.a.read('stock.production.lot',d['missing'].get('stock.lot',[]),['name','product_id','company_id']);pids={m.maps['product.product'][rid(s['product_id'])] for s in source_lots}
 current_lots=m.b.search_read('stock.lot',[['company_id','=',1],['product_id','in',sorted(pids)]],['name','product_id']);lookup={};pending=[]
 for x in current_lots:
  key=(rid(x['product_id']),x['name']);require(key not in lookup,'Ambiguous target lot');lookup[key]=x['id']
 for s in source_lots:
  pid=m.maps['product.product'][rid(s['product_id'])];key=(pid,s['name'])
  if key in lookup:m.maps['stock.lot'][s['id']]=lookup[key]
  else:pending.append(s)
 for batch in chunks(pending,100):
  ids=m.mutate('stock.lot','create',[[{'name':s['name'],'product_id':m.maps['product.product'][rid(s['product_id'])],'company_id':1} for s in batch]]);require(len(ids)==len(batch),'Incomplete lot creation');m.maps['stock.lot'].update({s['id']:t for s,t in zip(batch,ids)});m.persist()
 m.persist();m.attach('stock.lot',[(s['id'],m.maps['stock.lot'][s['id']]) for s in source_lots])
 require(not any(d['missing'].get(k) for k in ['product.product','stock.location','uom.uom']),'Missing master mapping')
 # Inventory adjustments are handled separately, never disguised as receipts.
 transfermoves=[s for s in d['moves'] if s['picking_id']];ids={s['id'] for s in transfermoves}
 save(OUT/'supporting-transfer-discovery.json',{'moves':transfermoves,'pickings':d['pickings'],'lines':[x for x in d['lines'] if rid(x['move_id']) in ids]})
 m.j.setdefault('supporting_source_transfers',[]);m.persist()
 code=(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/batch_pysb_old_po_receipts.py').read_text(encoding='utf8')
 # Pending stock gates are prepared records, not interrupted native writes.
 code=code.replace("rec['status']=='prepared'","rec['status'] in ['prepared','blocked_stock']").replace("r['status']=='prepared'","r['status'] in ['prepared','blocked_stock']")
 code=code[:code.index(' pending=[(p,ids)')]+" m.persist();print('Supporting transfers prepared',flush=True)\n\nif __name__=='__main__':main()\n"
 for a,b in [('old-po-late-receipts-discovery.json','supporting-transfer-discovery.json'),('standalone_source_receipts','supporting_source_transfers'),('PYSB-OLD-PO-SUPPLY','PYSB-SUPPORT-STOCK'),('pysb_standalone_supply','pysb_supporting_stock'),('REAL V14 LATE RECEIPT / RELATED RETURN FROM PRE-JULY PO; NO PO IMPORT','REAL V14 INTERNAL / RETURN / CONSIGNMENT FLOW; NO ORDER IMPORT')]:code=code.replace(a,b)
 exec(compile(code,'<supporting-transfer-preparation>','exec'),{'__name__':'__main__','__file__':str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/batch_pysb_old_po_receipts.py')})
if __name__=='__main__':main()
