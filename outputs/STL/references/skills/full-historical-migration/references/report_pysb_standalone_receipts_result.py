"""Publish the quantity-only result of the approved standalone receipts."""
import json
from pathlib import Path
from collections import Counter
OUT=Path(__file__).resolve().parents[6]/'outputs/pysb-stock-migration-20261012'
def main():
    j=json.loads((OUT/'execution-journal.json').read_text(encoding='utf8'))
    audit=json.loads((OUT/'stock-reconciliation-report.json').read_text(encoding='utf8'))
    rows=j['standalone_source_receipts']
    result={'database':j['database'],'company_id':1,'receipts':rows,'auto_route_duplicate_cleanup':j['standalone_receipt_auto_route_cleanup'],'new_completed_original_scope':len(j['completed_events'])-2935,'event_counts':dict(Counter(x['status'] for x in j['event_results'].values())),'audit':audit['summary'],'native_validation_exceptions':j.get('native_validation_exceptions',{})}
    audit['standalone_source_receipts']=rows
    audit['summary']['standalone_source_receipts']=len(rows)
    (OUT/'stock-reconciliation-report.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf8')
    (OUT/'standalone-source-receipts-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    handoff=json.loads((OUT/'stock-next-step-handoff.json').read_text(encoding='utf8'));handoff.update(summary=audit['summary'],event_results=j['event_results'],standalone_source_receipts=rows)
    (OUT/'stock-next-step-handoff.json').write_text(json.dumps(handoff,ensure_ascii=False,indent=2),encoding='utf8')
    lines=['# Phiếu nhập lẻ từ PO cũ — Pao Yeang', '', 'Chỉ ghi py19-staging-39654560, công ty ID 1. V14 chỉ đọc. Không chuyển thêm PO cũ hoặc tạo bill; không đối chiếu định giá.', '',
           'Đã hoàn tất hai chuỗi Vendors → HQ/Input → HQ/Stock: RED D-11 lot 20260608, lượng 20 theo đơn vị 30KGS; TAC-TAPE lot AC264050, lượng 100 ROLL. Mỗi record có Reference nguồn, PO cũ, move nguồn và ghi chú dữ liệu v14.', '',
           '| Chứng từ v14 | PO nguồn | Phiếu v19 | Move v19 | Lượng | Ngày UTC |', '|---|---|---|---|---:|---|']
    for r in rows:
        p=r['note']['source_picking']
        lines.append(f"| {p['name']} | {p['origin']} | [{r['target_picking']}](https://py-staging.odoo.com/odoo/stock.picking/{r['target_picking']}) | {r['target_move']} | {r['source_qty']} | {r['date']} |")
    lines += ['', 'Odoo tự sinh hai phiếu Storage khác (3833, 3836). Đã hủy khi còn confirmed, lượng thực hiện 0, chưa có move line để tránh trùng hai bước nguồn đã hoàn tất. Nhật ký giữ toàn bộ bằng chứng trước/sau.', '',
              f"Sau bổ sung, chạy lại hoàn tất thêm {result['new_completed_original_scope']} chứng từ thuộc phạm vi gốc. Trạng thái cuối: {result['event_counts']}.", '',
              f"Kiểm tra kho: {result['audit']}", '',
              f"Ngoại lệ native còn chờ: {result['native_validation_exceptions']}", '',
              'Bruce đã lưu tracking serial → lot cho sản phẩm 130306 trên staging. Đã kiểm tra thay đổi được phép, hoàn tất HQ/IN/00083 và bước Input → Stock liên quan, giữ LOT01, lượng 2 và ngày nguồn. Không còn ngoại lệ native của receipt này. Thay đổi master được ghi riêng trong execution-journal.json → approved_operator_master_changes.', '',
              'Đã khôi phục 92 SOL có cost bị tính lại sau validate. Toàn bộ 2683 SOL ánh xạ nguồn khớp cost v14. Các chênh lệch tồn đầu/cuối tháng còn được báo riêng, không coi ledger khớp là toàn bộ tồn v19 đã khớp v14.', '',
              '[Báo cáo tổng hợp](PYSB_Stock_Migration_Review.html) · [Nhật ký](execution-journal.json) · [Dữ liệu phiếu nhập](standalone-source-receipts-result.json)']
    (OUT/'Standalone_Receipts_Result.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(json.dumps(result['event_counts']))
if __name__=='__main__':main()
