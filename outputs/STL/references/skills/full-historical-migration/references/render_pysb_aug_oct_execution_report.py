"""Render Vietnamese current execution evidence without contacting Odoo."""
import json
import runpy
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
I=runpy.run_path(str(Path(__file__).with_name('inspect_pysb_aug_oct_prod.py')))
OUT=I['OUT']
def load(n,default=None):return json.loads((OUT/n).read_text(encoding='utf8')) if (OUT/n).exists() else default

def main():
    scope=load('scope.json');r=load('independent-receipts-journal.json',{'groups':{}});m=load('independent-mo-journal.json',{'mos':{}});a=load('independent-invoice-journal.json',{'documents':{}})
    receipts=[x for x in r['groups'].values() if x.get('phase')=='completed'];mos=[x for x in m['mos'].values() if x.get('status')=='verified_done'];invoices=[x for x in a['documents'].values() if x.get('status')=='verified_posted']
    d=load('independent-delivery-journal.json',{'groups':{}})
    deliveries=[x for x in d['groups'].values() if x.get('phase')=='completed']
    inventory=load('independent-inventory-journal.json',{'groups':{}})
    inventory_done=[x for x in inventory['groups'].values() if x.get('status')=='verified_done']
    coverage=load('after-run-stock-coverage.json');opening=load('detailed-opening-comparison.json');existing=load('existing-invoice-financial-audit.json')
    manifest=load('independent-invoice-manifest.json');remaining=[x for x in manifest['documents'] if not x['target_existing'] and str(x['source_id']) not in a['documents']]
    holds=Counter(e['reason'] for x in remaining for e in x['errors'])
    uncertain=[{'journal':name,'model':o['model'],'method':o['method']} for name,j in [('receipts',r),('deliveries',d),('mos',m),('invoices',a),('inventory',inventory)] for o in j.get('operations',[]) if o['status'] in ['intent','uncertain']]
    lines=['# Tiến độ chuyển lịch sử PYSB tháng 8–10/2026','',f"Cập nhật từ hồ sơ lúc {datetime.now(timezone.utc).isoformat()}. Đây là báo cáo tiến độ, **chưa nghiệm thu đầy đủ**.",'',
        f"Nguồn v14 prod `paoyeang_live` → đích v19 prod `py19-main-33843450`, công ty PYSB (1). Move từ `{scope['start_utc']}` UTC đến trước `{scope['end_utc_exclusive']}` UTC. **Tháng 10 chỉ đến mốc chụp này**, tương ứng 24/10/2026 08:50:44 Malaysia.",'',
        '| Phần thực thi mới | Đã hoàn tất và đọc lại đạt |','|---|---:|',f'| PO/chuỗi nhập | {len(receipts)} |',f"| Move trong các chuỗi nhập | {sum(len(x.get('verified_moves',[])) for x in receipts)} |",f'| MO | {len(mos)} |',f"| Move MO | {sum(len(x.get('verified_moves',[])) for x in mos)} |",f'| Invoice/Bill/Credit Note | {len(invoices)} |','',
        'Loại kế toán mới: '+', '.join(f'{k}: {v}' for k,v in Counter(x['move_type'] for x in invoices).items())+'. Dùng sequence v19, giữ số v14 để truy vết. Không chuyển thanh toán/đối soát và không gọi gửi E-Invoice.','',
        '## Đối chiếu độc lập','',f"Báo cáo move mới nhất: `{coverage['summary']}`. Chỉ số này có cả baseline đã kiểm chứng và phần mới; không cộng hai lần số thực thi mới. Các move còn lại chưa đạt, không đổi nhãn thành đã chuyển.",'',
        f"Tồn đầu kỳ chi tiết trong tập sản phẩm đã ánh xạ: `{opening['summary']}`. Các khóa thiếu ánh xạ vẫn được giữ trong báo cáo. Chưa thay thế đối chiếu tồn toàn công ty ở đầu kỳ, cuối tháng 8, cuối tháng 9 và mốc tháng 10.",'',
        f"47 chứng từ kế toán có sẵn trước đợt chạy: `{existing['summary']}`. 40 chứng từ lệch trường tỷ giá quy đổi bổ sung, gồm 7 lệch salesperson và 3 lệch tỷ giá native; tổng tiền được kiểm tra khớp. Không reset draft hoặc sửa chứng từ posted. Đạt phần tiền/định danh chưa thay thế nghiệm thu từng dòng và liên kết.",'',
        '## Nhóm chờ và công việc còn lại','',
        '- Giữ nhóm sai/thiếu tồn đầu kỳ, tracking, đơn vị PC không tương đương, master ED42 chưa xác minh, tài khoản archive/khác nhóm và điều kiện thanh toán chưa khớp. Không tự đổi master hoặc cấp tồn tạm.',
        '- PO khác cách tách/gộp phiếu vẫn chờ. Đơn vị khác tên chỉ được chuẩn hóa trên move native chưa picked/done khi đã chứng minh cùng quy đổi và cùng lượng.',
        '- Tiếp tục phần DO/MO và chuỗi kho độc lập sau kiểm tra nguồn theo thời gian; không lấy receipt ngày sau bù giao dịch ngày trước.',
        '- Chạy lại Verify từng dòng SO/PO, MO, quét đầy đủ move nguồn và tồn toàn công ty sau các lượt ghi; nghiệm thu giao dịch và mức khớp đơn hàng là hai kết quả riêng.',
        f"- Chứng từ kế toán chưa tạo theo manifest hiện tại: {len(remaining)}; lý do chặn có thể trùng trên một chứng từ: `{dict(holds)}`.",
        f'- Thao tác còn chờ xác minh phản hồi: {len(uncertain)}.','',
        '## Hồ sơ','',
        '- [Phạm vi chốt](scope.json), [quyết định Operator](operator-decisions.json).',
        '- [Nhật ký nhập PO](independent-receipts-journal.json), [nhật ký MO](independent-mo-journal.json), [nhật ký kế toán](independent-invoice-journal.json).',
        '- [Ánh xạ sau chạy](after-run-stock-mapping.json), [quét move sau chạy](after-run-stock-coverage.json).',
        '- [Tồn đầu kỳ chi tiết](detailed-opening-comparison.json), [lot đầu kỳ](opening-lot-resolution.json), [kế toán có sẵn](existing-invoice-financial-audit.json).',
        '- Báo cáo `BAO_CAO_PREFLIGHT.md` là tình trạng trước đợt ghi, không phải trạng thái hiện tại.','']
    table_end=next(i for i,line in enumerate(lines) if line.startswith('| Invoice/Bill/Credit Note'))
    lines[table_end:table_end]=[f'| SO/chuỗi giao hàng | {len(deliveries)} |',f"| Move giao hàng | {sum(len(x.get('verified_moves',[])) for x in deliveries)} |"]
    lines[table_end:table_end]=[f'| Phiếu kiểm kê lịch sử | {len(inventory_done)} |',f"| Move kiểm kê | {sum(len(x.get('verified_moves',[])) for x in inventory_done)} |"]
    lines.extend(['[Nhật ký kiểm kê và bằng chứng delta thực tế](independent-inventory-journal.json). Không ghi trực tiếp số tồn; sử dụng quy trình kiểm kê chuẩn.', ''])
    approval=load('operator-mo-demand-rounding-approval.json',{})
    lines.extend(['Quyền làm tròn demand nguyên liệu chỉ áp dụng đúng '+str(len(approval.get('approved_source_mos',[])))+' MO đã duyệt; giữ nguyên lượng kế hoạch thành phẩm và qty_producing.',
                  '[Phê duyệt 13 MO](operator-mo-demand-rounding-approval.json), [nhật ký giao hàng](independent-delivery-journal.json).',''])
    company=load('full-company-balances.json')
    if company:
        lines.extend(['## Tồn toàn công ty tại bốn mốc','',f"Mốc chụp nguồn: {company.get('source_captured_utc','chưa ghi')}; đích: {company.get('target_captured_utc','chưa ghi')}. Cơ sở ngày: {company.get('source_date_basis','chưa xác minh')} / {company.get('target_date_basis','chưa xác minh')}. Đây là số liệu tại mốc chụp, cần chụp lại sau lượt ghi mới; chưa dùng để nghiệm thu cuối đợt.",'',
                      '| Mốc UTC, không bao gồm giao dịch tại mốc | Khóa khớp | Ngoại lệ đã duyệt | Khác | Thiếu ánh xạ nguồn |',
                      '|---|---:|---:|---:|---:|'])
        for cutoff,record in company['cutoffs_exclusive'].items():
            counts=record['summary']
            lines.append(f"| {cutoff} | {counts['matched']} | {counts.get('approved_exceptions',0)} | {counts['different']} | {counts['unmapped_source_keys']} |")
        lines.extend(['','[Chi tiết tồn toàn công ty](full-company-balances.json). Các chênh lệch và khóa thiếu ánh xạ vẫn chặn nghiệm thu.',''])
        if company.get('target_unavailable_extra_product_metadata_ids'):lines.extend([f"Metadata bổ sung của {len(company['target_unavailable_extra_product_metadata_ids'])} product không có/không truy cập được trong company 1; giữ ID trong báo cáo, không mở quyền sang công ty khác. Mọi product có quant/move thực tế vẫn bắt buộc đọc đủ.",''])
    demand_audit=load('mo-demand-exception-audit.json')
    if demand_audit:
        lines.extend([f"Kiểm chứng độc lập quyền làm tròn demand 13 MO: `{demand_audit['summary']}`. [Chi tiết nguồn, đích và chênh lệch](mo-demand-exception-audit.json).",''])
    orders=load('order-quantity-verification.json')
    if orders:
        lines.extend(['## Chỉ tiêu SO/PO theo dòng kinh doanh','', '| Loại | Dòng kinh doanh | Lượng đặt khớp | Delivered/Received khớp | Invoiced khớp | Khớp đầy đủ |','|---|---:|---:|---:|---:|---:|'])
        for model in orders['models']:
            business=[x for x in model['rows'] if x.get('quantity_applicable',bool(x.get('metrics')))];delivery='delivered' if model['model']=='sale.order.line' else 'received'
            count=lambda key:sum(x.get('metrics',{}).get(key,{}).get('match',False) for x in business)
            lines.append(f"| {'SO' if delivery=='delivered' else 'PO'} | {len(business)} | {count('ordered')} | {count(delivery)} | {count('invoiced')} | {sum(x['match'] for x in business)} |")
        lines.extend(['','Các số trên là số dòng **đối chiếu khớp**, có thể gồm source=target=0; không phải số dòng/chứng từ đã chuyển. Ghi chú và tiêu đề không tính vào dòng kinh doanh. Dòng thiếu ánh xạ vẫn giữ nguồn/đích/delta/kết quả riêng. [Chi tiết từng dòng và chứng từ phụ thuộc](order-quantity-verification.json).',''])
    source_rescan=load('source-frozen-rescan-comparison.json')
    if source_rescan:
        lines.extend([f"Quét nguồn độc lập: {source_rescan['current_moves']} move hiện tại / {source_rescan['frozen_moves']} move đã chốt; thêm {len(source_rescan['added_since_snapshot'])}, thay đổi {len(source_rescan['changed_frozen_moves'])}. Thời điểm kết thúc: {source_rescan.get('completed_utc','xem mốc tệp')}. [Chi tiết quét lại nguồn](source-frozen-rescan-comparison.json). Không tự mở rộng phạm vi ghi.",''])
    unit_aliases=[row for group in inventory_done for row in group.get('before',[]) if row.get('target_unit_alias_proof')]
    if unit_aliases:
        lines.extend([f"Kiểm kê có {len(unit_aliases)} move dùng đơn vị gốc tương đương 1:1; cùng gốc, cùng hệ số và cùng độ chính xác, không đổi lượng lịch sử hoặc master. Bằng chứng theo move ở [nhật ký kiểm kê](independent-inventory-journal.json), phạm vi xác minh ở [hồ sơ alias](inventory-unit-alias-validation.json).",''])
    inventory_rounding=load('inventory-approved-rounding-audit.json')
    if inventory_rounding:
        lines.extend([f"Kiểm kê có {len(inventory_rounding['verified_rounding_records'])} dòng làm tròn đã được kiểm chứng độc lập trong quyền 22 dòng của Operator. [Nguồn, đích và delta](inventory-approved-rounding-audit.json).",''])
    return_origins=load('return-origin-verification.json')
    if return_origins:
        lines.extend(['## Phụ thuộc trả hàng đang rà soát','',f"Chứng từ gốc đã kiểm tra vật lý: `{return_origins['summary']}`. Đây chưa phải số trả hàng đã chuyển.",'[Truy nguyên chứng từ gốc](return-origin-dependency-review.json), [đối chiếu chi tiết](return-origin-verification.json), [cấu hình và liên kết native](return-native-dependency-evidence.json).',''])
    expiry=load('operator-expiry-confirmation-approval.json')
    if expiry:
        lines.extend(['[Quyền xác nhận hạn lot cho MO lịch sử](operator-expiry-confirmation-approval.json). Xác nhận wizard native trong phạm vi đã duyệt; giữ nguyên metadata hạn lot.',''])
    (OUT/'BAO_CAO_THUC_THI.md').write_text('\n'.join(lines),encoding='utf8');print('BAO_CAO_THUC_THI.md',flush=True)

if __name__=='__main__':main()
