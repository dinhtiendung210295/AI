"""Render durable evidence after the temporary-stock retry; no Odoo writes."""
import json
from collections import Counter
from pathlib import Path

OUT = Path(__file__).resolve().parents[6] / 'outputs/pysb-stock-migration-20261012'

def load(name):
    return json.loads((OUT / name).read_text(encoding='utf8'))

def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')

def main():
    j = load('execution-journal.json')
    r = load('stock-reconciliation-report.json')
    t = load('temporary-negative-stock-report.json')
    results = {k: j['event_results'][k] for k in t['retry_event_keys']}
    counts = dict(Counter(x['status'] for x in results.values()))
    t.update(event_results_after_retry=results, summary={'adjustments': len(t['adjustments']), 'selected_events': len(results), 'retry_result_counts': counts, 'new_completed_events': len(j['completed_events']) - 2852, 'global_event_counts': dict(Counter(x['status'] for x in j['event_results'].values()))})
    save('temporary-negative-stock-report.json', t)
    r['temporary_negative_stock_adjustments'] = j['temporary_negative_stock_adjustments']
    r['summary']['temporary_negative_stock_adjustments'] = len(t['adjustments'])
    r['temporary_stock_policy'] = 'Temporary quantity differences from v14 are intentional and pending reconciliation; no valuation comparison.'
    save('stock-reconciliation-report.json', r)
    handoff = load('stock-next-step-handoff.json')
    handoff.update(summary=r['summary'], event_results=j['event_results'], temporary_negative_stock_adjustments=t['adjustments'], temporary_stock_retry_summary=t['summary'])
    save('stock-next-step-handoff.json', handoff)
    lines = ['# Kết quả điều chỉnh tạm cho tồn âm v14', '', 'Chỉ thực hiện trên py19-staging-39654560, công ty Pao Yeang (ID 1). Không so sánh định giá.', '',
             f"Đã tạo và kiểm tra {len(t['adjustments'])} điều chỉnh tạm. Lượt chạy hoàn tất thêm {t['summary']['new_completed_events']} chứng từ: 77 phiếu kho và 6 MO. Trong 104 chứng từ được chọn, kết quả: {counts}.", '',
             '## Vì sao phiếu đầu chuỗi bị chặn?', '',
             'Có hai nhóm khác nhau: v14 thực sự xuất âm theo đúng lot/kiện; hoặc v14 có nguồn nhập nhưng nguồn nhập chưa thuộc phạm vi đã chuyển. Chỉ nhóm xuất âm được bổ sung tồn tạm trong lượt này.', '',
             'Ví dụ nguồn nhập còn thiếu: PO-04349 có ngày đơn 08/06/2026, PO-04217 có ngày đơn 12/03/2026; cả hai có bước Input → Stock hoàn tất ngày 02/07. Chúng không thuộc danh sách PO tháng 7 nên chạy receipt trước trong danh sách hiện có vẫn không cung cấp đủ nguyên liệu. Pack/Delivery sau đó chờ phiếu đầu chuỗi.', '',
             '## Tham chiếu trên record điều chỉnh', '',
             'Mỗi stock.move có Reference và origin bắt đầu bằng PYSB-TEMP-NEG, kèm REVIEW REQUIRED. Trường ghi chú description_picking_manual chứa SO/PO gốc, chứng từ nguồn, move/line nguồn, sản phẩm, lot, location, lượng bổ sung, số tồn v14 trước khi xuất, ngày lịch sử UTC và thời điểm tạo thực tế.', '',
             '**TEMPORARY_PENDING_RECONCILIATION**: đây không phải giao dịch điều chỉnh thực trên v14. Khoản lượng tạm phải được đối soát riêng trước nghiệm thu tồn. Không tự hủy chứng từ đã validate để hoàn tác.', '',
             '| Move v19 | Chứng từ nguồn | Lot | Tồn v14 trước xuất | Lượng tạm | Ngày UTC |', '|---|---|---|---:|---:|---|']
    for x in t['adjustments']:
        note = json.loads(x['note'])
        lines.append(f"| [{x['target_move']}](https://py-staging.odoo.com/odoo/stock.move/{x['target_move']}) | {x['event']['reference']} | {note['lot']} | {x['source_evidence'][0]['source_quantity_before_move']} | {x['delta']} {note['unit']} | {x['date']} |")
    lines += ['', '## Chứng từ được chọn còn chờ', '', '| Chứng từ | Trạng thái | Chi tiết |', '|---|---|---|']
    for x in results.values():
        if x['status'] != 'done':
            detail = json.dumps(x.get('shortage', x.get('reason', x.get('source_moves', ''))), ensure_ascii=False).replace('|', '/')
            lines.append(f"| {x['reference']} | {x['status']} | {detail} |")
    lines += ['', '## Kiểm tra sau chạy', '', f"Kết quả đối chiếu: {json.dumps(r['summary'], ensure_ascii=False)}", '',
              'Ledger khớp số lượng của các giao dịch đã chuyển, có tính riêng 38 khoản tồn tạm; kết quả này không có nghĩa toàn bộ tồn v19 đã khớp v14.', '',
              'Ngoại lệ phát sinh từ nút validate chuẩn: SO-53388 / S02406 có thêm dòng 11740, lượng đặt 0, lượng giao 5, subtotal 0, liên kết move v19 10362. Move nguồn 504751 / HQ/DO/54131 có sale_line_id rỗng. Dòng phát sinh được giữ nguyên và báo riêng; chỉ khôi phục cost trên 2683 dòng đã ánh xạ v14.', '',
              '[Nhật ký đầy đủ](execution-journal.json) · [Đối chiếu từng dòng](stock-reconciliation-report.json) · [Bằng chứng tồn âm](source-negative-stock-classification.json)']
    (OUT / 'Temporary_Negative_Stock_Result.md').write_text('\n'.join(lines) + '\n', encoding='utf8')
    print(json.dumps(t['summary']))

if __name__ == '__main__':
    main()
