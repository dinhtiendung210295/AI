"""Render a concise Vietnamese review report from completed reconciliation evidence."""
import json,html
from pathlib import Path
OUT=Path(__file__).resolve().parents[6]/'outputs/pysb-stock-migration-20261012'
def load(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def esc(v):return html.escape(str(v))
def table(headers,rows):return '<table><thead><tr>'+''.join('<th>'+esc(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table>'
def main():
 r=load('stock-reconciliation-report.json');p=load('execution-manifest.json');j=load('execution-journal.json');s=r['summary'];products={x['id']:x['name'] for x in p['target_products']};locations={x['id']:x['complete_name'] for x in load('v19-staging-snapshot.json')['locations']};lots={j['maps']['stock.lot'].get(str(x['source_id'])):x['name'] for x in p['lot_plan']}
 units={x['id']:x['name'] for x in load('v19-staging-dependencies.json')['uoms']};packages={j['maps'].get('stock.package',{}).get(str(x['id'])):x['name'] for x in load('v14-prod-dependencies.json')['packages']}
 statuses={'done':'Đã hoàn tất','blocked_stock':'Thiếu tồn đúng lot/vị trí','blocked_predecessor':'Chờ bước kho trước','blocked_auto_invoice':'Có automation tạo invoice','blocked_native_validation':'B? quy t?c validate Odoo ch?n','blocked_precision':'Chờ xử lý độ chính xác'}
 summary=[['Phiếu đã chuẩn bị',s['pickings_prepared']],['Trạng thái phiếu',esc(s['picking_states'])],['MO đã chuẩn bị',s['MO_prepared']],['Trạng thái MO',esc(s['MO_states'])],['Stock move khớp chi tiết',s['moves_details_match']],['Chênh lệch làm tròn đã duyệt',s['approved_rounding_differences']],['Lệch ngày ở move đã hoàn tất',s['done_move_date_mismatches']],['Reference No khớp',s['references_match']],['Chênh lệch sổ số lượng của lượt chuyển',s['ledger_differences']],['Sản phẩm được bảo toàn',s['product_masters_preserved']],['Không tạo invoice/bill',s['no_invoice_or_bill_created']]]
 events=[]
 for e in r['event_results'].values():
  if e['status']=='done':continue
  details=[esc(e['reason'])] if e.get('reason') else []
  for item in e.get('shortage',[]):
   k=item['key'];pack=f" | kiện: {packages.get(k[3],k[3])}" if k[3] else '';details.append(esc(f"{products.get(k[0],k[0])} | {locations.get(k[1],k[1])} | lot: {lots.get(k[2],k[2]) or 'không theo lot'}{pack} | có {item['available']}, cần {item['required']}"))
  if e.get('source_moves'):details.append('Move nguồn đang chờ: '+esc(e['source_moves']))
  url='https://py-staging.odoo.com/odoo/'+('stock.picking' if e['kind']=='picking' else 'mrp.production')+'/'+str(e['target'])
  events.append([esc(e['reference']),'<a href="'+url+'">Mở v19</a>',esc(e['date']),esc(statuses.get(e['status'],e['status'])),'<br>'.join(details)])
 rounding=[]
 for m in r['moves']:
  if m.get('approved_rounding_difference'):
   key=m['expected'][0]['key'];sq=sum(x['qty'] for x in m['expected']);tq=sum(x['qty'] for x in m['actual'])
   rounding.append([m['source_move'],m['target_move'],esc(products.get(key[0],key[0])),esc(units.get(key[1],key[1])),sq,tq,round(tq-sq,5)])
 docs=[['Phiếu chưa chuyển do ngoại lệ ánh xạ/lot',esc(r['excluded_pickings'])],['MO chưa chuyển do thiếu lot nguồn',esc(r['excluded_MO'])]]
 content='<h1>Pao Yeang — chuyển kho lịch sử v14 → v19 staging</h1><p>Phạm vi: phiếu của SO/PO tháng 7 đã chọn, gồm phiếu hoàn tất tháng 8–9; MO hoàn tất tháng 7. Company ID 1. Valuation không dùng làm tiêu chí khớp.</p>'+table(['Kiểm tra','Kết quả'],summary)+'<h2>Chứng từ còn chờ xử lý</h2>'+table(['Chứng từ v14','Liên kết','Ngày UTC','Nguyên nhân','Chi tiết'],events)+'<h2>Ngoại lệ chưa chuyển</h2>'+table(['Nhóm','ID v14'],docs)+'<h2>Làm tròn theo cấu hình v19 đã được duyệt</h2>'+table(['Move v14','Move v19','Sản phẩm','Đơn vị','Số lượng v14','Số lượng v19','Chênh lệch'],rounding)
 content+='<h2>Kiểm tra độ bao phủ toàn bộ giao dịch</h2><p>Báo cáo chứng từ đã ánh xạ không thay thế đối chiếu tồn toàn công ty. Cần kết quả rà move mới sau migration; thiếu hoặc còn vấn đề thì chưa đủ điều kiện nghiệm thu đầy đủ.</p><pre>'+esc(r.get('coverage_gate',{'full_acceptance_ready':False,'reason':'missing_full_move_coverage'}))+'</pre>'
 if (OUT/'order-fulfillment-report.json').exists():
  f=load('order-fulfillment-report.json');content+='<h2>Lượng giao/nhận trên SO/PO</h2>'+table(['Nhóm','Kết quả'],[[esc(k),esc(v)] for k,v in f['summary'].items()]);content+=table(['Đơn v14','Sản phẩm','Đã giao/nhận v14','Đã giao/nhận v19','Chênh lệch'],[[esc(x['source_order']),esc(x['product']),x['fulfilled_source'],x['fulfilled_target'],x['delta']] for x in f['rows'] if not x['match']])
 if (OUT/'product-opening-closing-report.json').exists():content+='<h2>Đối chiếu tồn đầu/cuối tháng 7</h2><p><a href="product-opening-closing-report.html">Mở báo cáo số lượng theo ngày chuẩn Odoo</a>. Báo cáo này bao gồm chênh lệch đầu kỳ và giao dịch ngoài phạm vi; không so sánh valuation.</p>'
 if (OUT/'lot-opening-closing-report.json').exists():
  lot=load('lot-opening-closing-report.json');content+='<h2>T?n ??u/cu?i th?ng theo lot / serial</h2><p>Ch? so s? l??ng, kh?ng so ??nh gi?. <a href="lot-opening-closing-report.html">M? b?o c?o chi ti?t s?n ph?m v? lot</a></p><pre>'+esc(lot['summary'])+'</pre><p>T?ng l??ng theo lot ?? ??i chi?u v?i b?o c?o s?n ph?m chu?n: '+esc(lot.get('native_product_crosscheck',{}).get('totals_match'))+'</p>'
 if j.get('supplementary_inventory_adjustments'):
  content+='<h2>Điều chỉnh tồn nguồn bổ sung</h2><p>Đã chạy lại các phiếu chờ sau khi bổ sung điều chỉnh và sửa kiện đầu kỳ. Danh sách chờ phía trên là kết quả cập nhật của lượt chạy lại.</p>'+table(['Move v14','Move v19','Ngày UTC','Lượng nguồn','Lượng đích'],[[x['source_move'],x['target_move'],esc(x['date']),x['source_qty'],x['target_qty']] for x in j['supplementary_inventory_adjustments']])
 if (OUT/'opening-package-correction-report.json').exists():
  opening=load('opening-package-correction-report.json');content+='<h2>Sửa kiện tồn đầu kỳ</h2><p><a href="Opening_Package_Correction_Result.md">Kết quả và bằng chứng</a></p><pre>'+esc(opening['summary'])+'</pre>'+table(['Sản phẩm v14','Kiện','Tồn đầu v14','Tồn đầu v19','Khớp'],[[x['product'],esc(x['package']),x['source_opening'],x['target_opening'],x['match']] for x in opening['opening_crosscheck']])
 if (OUT/'Pending_Transfer_Retry_Findings.md').exists():
  content+='<h2>Retry pending transfers</h2><p><a href="Pending_Transfer_Retry_Findings.md">Results and source-negative-lot evidence</a></p>'
 if j.get('MO_recovery'):content+='<h2>Nhật ký xử lý ba MO đầu lượt</h2><p>Ba MO đã tiêu hao nguyên liệu trước khi dòng thành phẩm hoàn tất. Đã khôi phục dòng thành phẩm, giữ nguyên raw move đã done, không tiêu hao lần hai. Extra Cost phục vụ tính giá thành được bù theo giá trị nguyên liệu đã ghi nhận trên v19. Chi tiết trước/sau nằm trong execution-journal.json → MO_recovery.</p>'
 if j.get('temporary_negative_stock_adjustments'):
  content+='<h2>Điều chỉnh tạm cho tồn âm v14</h2><p>Đây là tồn tạm được Bruce cho phép, không phải giao dịch điều chỉnh thực trên v14. Chênh lệch số lượng do tồn tạm phải được theo dõi riêng. <a href="Temporary_Negative_Stock_Result.md">Kết quả và danh sách tham chiếu</a></p>'+table(['Move v19','Reference','Ngày UTC','Lượng bổ sung','Trạng thái đối soát'],[[x['target_move'],esc(x['reference']),esc(x['date']),x['delta'],esc(x['review_status'])] for x in j['temporary_negative_stock_adjustments']])
 if j.get('standalone_source_receipts'):
  if (OUT/'All_Old_PO_Late_Receipts_Result.md').exists():content+='<p><a href="All_Old_PO_Late_Receipts_Result.md">Kết quả mới nhất: toàn bộ PO cũ nhập muộn và điều chỉnh tồn tạm bổ sung</a></p>'
  content+='<h2>Phiếu nhập lẻ từ PO cũ</h2><p>Giữ tuyến Vendors → Input → Stock, lượng, lot và ngày nguồn. Không tạo PO cũ trên v19.</p>'+table(['Move v14','Phiếu v19','Reference','Ngày UTC','Lượng','Trạng thái'],[[x['source_move'],x['target_picking'],esc(x['reference']),esc(x['date']),x['source_qty'],esc(x['status'])] for x in j['standalone_source_receipts']])
 source_mo={x['id']:x for x in load('mo-details.json')['mo']}
 source_snapshot=load('v14-prod-snapshot.json');source_p={x['id']:x for x in source_snapshot['pickings']+source_snapshot['chain_pickings']}
 content+='<h2>Chi ti?t ch?ng t? ch?a chuy?n</h2>'+table(['Lo?i','Ch?ng t? ngu?n','ID ngu?n'],[['MO',esc(source_mo[i]['name']),i] for i in r['excluded_MO']]+[['Phi?u kho',esc(source_p.get(i,{}).get('name',i)),i] for i in r['excluded_pickings']])
 content+='<h2>Ngo?i l? ?nh x? chi ti?t</h2><pre>'+esc(json.dumps(r['mapping_exceptions'],ensure_ascii=False,indent=2))+'</pre>'
 content+='<p><a href="stock-reconciliation-report.json">Chi tiết đối chiếu từng move, lot và ngày</a> · <a href="execution-journal.json">Nhật ký toàn bộ thao tác</a></p>'
 (OUT/'PYSB_Stock_Migration_Review.html').write_text('<!doctype html><meta charset="utf-8"><title>Pao Yeang — báo cáo chuyển kho</title><style>body{font:15px Arial;margin:32px;color:#23313e}table{border-collapse:collapse;width:100%;margin:16px 0}th,td{border:1px solid #dce3e8;padding:8px;text-align:left;vertical-align:top}th{background:#eef4f8}h2{margin-top:32px}a{color:#087ca7}</style>'+content,encoding='utf8')
 print('PYSB_Stock_Migration_Review.html')
if __name__=='__main__':main()
