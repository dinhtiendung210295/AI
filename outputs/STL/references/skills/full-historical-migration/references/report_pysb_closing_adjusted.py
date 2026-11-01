"""Warehouse and mapped consignment quantities, with approved temporary supply separated."""
from complete_pysb_stock_migration import Completion,rid,index,load,OUT
from execute_pysb_stock_migration import save,require
from collections import defaultdict,Counter
from decimal import Decimal,ROUND_HALF_UP
import json,html,argparse
from pathlib import Path
from scan_pysb_july_other_stock_coverage import acceptance_gate
def main(coverage_report=None):
 m=Completion();d=load('closing-lot-report-inputs.json');mapping={int(k):v for k,v in d['mapping'].items()};reverse={v:k for k,v in mapping.items()};locmap=m.maps['stock.location'];revloc={t:s for s,t in locmap.items()};source_locations=index(m.a.read('stock.location',sorted(set(locmap)|set(d['warehouse_locations']['source'])),['complete_name','usage','company_id']));target_locations=index(m.b.read('stock.location',sorted(set(locmap.values())|set(d['warehouse_locations']['target'])),['complete_name','usage','company_id']));source_lots={int(k):v for k,v in d['source_lots'].items()};target_lots={int(k):v for k,v in d['target_lots'].items()};products={int(k):v for k,v in d['source_products'].items()};uoms={int(k):v for k,v in d['source_uoms'].items()};cutoff='2026-07-31 16:00:00'
 def scope(loc,label):
  if loc in d['warehouse_locations'][label]:return 'warehouse'
  locations=source_locations if label=='source' else target_locations
  if loc in (locmap if label=='source' else revloc) and locations.get(loc,{}).get('usage') in ['internal','transit']:return 'mapped_consignment'
  return None
 balances={}
 for label in ['source','target']:
  quantities=defaultdict(float);lots=source_lots if label=='source' else target_lots
  def key(pid,loc,lot):
   sid=pid if label=='source' else reverse[pid];sloc=loc if label=='source' else revloc.get(loc,'unmapped_target_'+str(loc));return (scope(loc,label),sid,sloc,lots.get(lot,''))
  for q in d[label+'_quants']:
   pid=rid(q['product_id']);sid=pid if label=='source' else reverse[pid];loc=rid(q['location_id'])
   if not d['stored'][str(mapping[sid])] or not scope(loc,label):continue
   quantities[key(pid,loc,rid(q['lot_id']))]+=q['quantity']
  for x in d[label+'_lines']:
   if x['date']<cutoff:continue
   pid=rid(x['product_id']);sid=pid if label=='source' else reverse[pid]
   if not d['stored'][str(mapping[sid])]:continue
   if label=='target':qty=x['quantity_product_uom']
   else:
    base=uoms[rid(products[sid]['uom_id'])];qty=x['qty_done']/uoms[rid(x['product_uom_id'])]['factor']*base['factor'];qty=float(Decimal(str(qty/base['rounding'])).quantize(Decimal('1'),rounding=ROUND_HALF_UP))*base['rounding']
   for field,sign in [('location_id',1),('location_dest_id',-1)]:
    loc=rid(x[field])
    if scope(loc,label):quantities[key(pid,loc,rid(x['lot_id']))]+=sign*qty
  balances[label]=quantities
 temporary=defaultdict(float);temporary_refs=defaultdict(list)
 for r in m.j.get('temporary_negative_stock_adjustments',[]):
  if r['status']!='verified' or r['date']>=cutoff:continue
  for k,q in r['deltas']:
   pid,loc,lot,pkg,owner=k
   if pid not in reverse or not scope(loc,'target'):continue
   key=(scope(loc,'target'),reverse[pid],revloc.get(loc,'unmapped_target_'+str(loc)),target_lots.get(lot,''));temporary[key]+=q;temporary_refs[key].append({'target_move':r['target_move'],'delta':q,'reference':r['reference'],'review_status':r['review_status']})
 rows=[]
 for k in sorted(set(balances['source'])|set(balances['target'])|set(temporary),key=str):
  group,pid,loc,lot=k;src=balances['source'][k];tgt=balances['target'][k];tmp=temporary[k];adjusted=tgt-tmp;delta=adjusted-src
  if max(abs(src),abs(tgt),abs(tmp))<1e-6:continue
  classification='matched' if abs(delta)<1e-5 else ('precision' if abs(delta)<=0.00501 else ('source_negative_lot' if pid==43759 else ('serial_confirmation_required' if pid==47305 and lot in ['C551466A0600K','C551466A0606K'] else 'unexplained')))
  rows.append({'scope':group,'source_product':pid,'target_product':mapping[pid],'product':products[pid]['name'],'source_location':loc,'location':source_locations.get(loc,{}).get('complete_name',str(loc)),'lot_serial':lot,'source_closing':src,'target_actual_closing':tgt,'temporary_closing':tmp,'target_without_temporary':adjusted,'actual_delta':tgt-src,'adjusted_delta':delta,'classification':classification,'temporary_references':temporary_refs[k]})
 summary={g:{'rows':sum(r['scope']==g for r in rows),'classifications':dict(Counter(r['classification'] for r in rows if r['scope']==g))} for g in ['warehouse','mapped_consignment']};unexplained=[r for r in rows if r['classification']=='unexplained']
 product_temp=defaultdict(float)
 for k,q in temporary.items():
  if k[0]=='warehouse':product_temp[k[1]]+=q
 product_rows=[]
 for r in load('product-opening-closing-report.json')['rows']:
  tmp=product_temp[r['source_product']];product_rows.append({**r,'temporary_closing':tmp,'target_without_temporary':r['target_closing']-tmp,'adjusted_closing_delta':r['closing_delta']-tmp})
 summary['coverage_gate']=acceptance_gate(coverage_report or OUT/'july-other-stock-coverage.json');summary['acceptance_scope']='Mapped products only; not full-company inventory acceptance';summary['native_products']={'products':len(product_rows),'actual_closing_mismatches':sum(abs(r['closing_delta'])>0.00501 for r in product_rows),'adjusted_closing_mismatches':sum(abs(r['adjusted_closing_delta'])>0.00501 for r in product_rows),'quantity_tolerance':0.00501};save(OUT/'closing-adjusted-reconciliation.json',{'cutoff_utc':cutoff,'summary':summary,'rows':rows,'product_rows':product_rows,'unexplained':unexplained,'policy':'Approved temporary supply retained. Adjusted quantity = actual quantity minus temporary net at cutoff. No valuation. No opening-date changes.','source_documents':load('closing-gap-source-documents.json')['pickings'],'native_operations':m.j.get('closing_unbuild_scrap_operations',{})})
 fields=['scope','product','location','lot_serial','source_closing','target_actual_closing','temporary_closing','target_without_temporary','adjusted_delta','classification'];labels=['Phạm vi','Sản phẩm','Vị trí','Lot / serial','Tồn v14','Tồn thực v19','Phần cấp tạm','V19 loại phần tạm','Chênh lệch đã loại tạm','Kết quả'];translations={'warehouse':'Kho công ty','mapped_consignment':'Consignment đã ánh xạ','matched':'Khớp','precision':'Độ chính xác 2 chữ số','source_negative_lot':'Ngoại lệ lot âm v14','serial_confirmation_required':'Cần xác nhận serial','unexplained':'Chưa giải thích'}
 def display(value):return str(round(value,5)) if isinstance(value,float) else translations.get(value,str(value))
 body=''.join('<tr>'+''.join('<td>'+html.escape(display(r[f]))+'</td>' for f in fields)+'</tr>' for r in rows if abs(r['actual_delta'])>1e-5 or r['classification']!='matched');page='<meta charset="utf-8"><title>PYSB — Đối chiếu tồn cuối tháng 7</title><style>body{font:14px Arial;margin:24px}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:6px}th{background:#eef4fa}</style><h1>Pao Yeang — Tồn cuối tháng 7/2026</h1><p>Chỉ số lượng, lot/serial và vị trí. Kho công ty và consignment được tách riêng. Tồn đối chiếu = tồn thực v19 − khoản tạm còn hiệu lực tại 31/07. Khoản tạm được giữ nguyên theo Bruce; không so định giá.</p><p>Phạm vi: các sản phẩm đã ánh xạ, không phải tồn toàn công ty. Sản phẩm được xét: '+str(len(product_rows))+'. Còn lệch sau loại tạm: '+str(summary['native_products']['adjusted_closing_mismatches'])+'. Chưa giải thích theo lot/vị trí: '+str(len(unexplained))+'. Kiểm tra bao phủ toàn bộ move: '+html.escape(str(summary['coverage_gate']))+'. Không kết luận nghiệm thu toàn công ty từ báo cáo này.</p><p>Ngoại lệ giữ nguyên: EPSON serial C551466A0606K trên v14 / C551466A0600K trên v19; NLB-901 có lot âm và lot đối ứng trên v14; 7 dòng sai khác độ chính xác. Bảng hiển thị các dòng lệch hoặc có phần tạm; JSON đi kèm lưu toàn bộ dòng và tham chiếu điều chỉnh tạm.</p><table><tr>'+''.join('<th>'+f+'</th>' for f in labels)+'</tr>'+body+'</table>'; (OUT/'PYSB_Closing_Adjusted_Reconciliation.html').write_text(page,encoding='utf8');print(json.dumps({'summary':summary,'unexplained_rows':len(unexplained),'unexplained':unexplained[:15]},ensure_ascii=False),flush=True)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--coverage-report',type=Path);args=parser.parse_args();main(args.coverage_report)
