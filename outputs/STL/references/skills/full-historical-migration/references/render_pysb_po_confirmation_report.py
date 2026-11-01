"""Render the final PO-only handoff from fresh verification; no ERP connection."""
import argparse
from collections import Counter
import json
from pathlib import Path


def load(path):
    return json.loads(path.read_text(encoding='utf8'))


def render(directory):
    out = Path(directory)
    phase = out / 'phases'
    gate = load(phase / 'confirm-po-gate.json')
    verification = load(phase / 'confirm-po-verification.json')
    journal = load(phase / 'order-confirmation-journal.json')
    stop = load(phase / 'operator-stop-after-confirm-po.json')
    if not stop.get('completed') or gate['eligible_unattempted'] or not gate['live_verification_complete']:
        raise RuntimeError('Cannot render a completed PO handoff before verification and stop')
    rows = verification['rows']
    new = [x for x in journal['orders'].values() if x.get('status') == 'verified_confirmed']
    held = [x for x in rows if x['status'] == 'held']
    states = Counter(x['target_state'] or 'thiếu đích' for x in rows)
    reasons = Counter(i['reason'] for row in held for i in row['reasons'])
    text = ['# Kết quả xác nhận PO và điểm dừng', '',
            '**Đã dừng sau bước xác nhận PO theo chỉ dẫn của Bruce.**', '',
            'Thời điểm kiểm chứng UTC: ' + gate['completed_utc'] + '.',
            'Không có writer đang chạy; khóa writer đã được kiểm tra sau cùng. Không thực hiện pha SO, hoàn tất kho hoặc kế toán trong lượt này.', '',
            '| Chỉ tiêu | Kết quả |', '|---|---:|',
            '| PO nguồn thuộc phạm vi đã khóa | ' + str(len(rows)) + ' |',
            '| PO xác nhận mới và đã đọc lại trong lượt này | ' + str(len(new)) + ' |',
            '| PO đã xác nhận đạt kiểm chứng bước PO, gồm cả có sẵn | ' + str(gate['completed_count']) + ' |',
            '| PO giữ chờ/cần rà soát | ' + str(gate['held_count']) + ' |',
            '| PO đủ điều kiện chưa xử lý | ' + str(gate['eligible_unattempted']) + ' |',
            '| PO đích ở trạng thái purchase | ' + str(states.get('purchase', 0)) + ' |',
            '| PO đích còn draft/sent | ' + str(states.get('draft', 0) + states.get('sent', 0)) + ' |',
            '| PO thiếu đích | ' + str(states.get('thiếu đích', 0)) + ' |', '',
            'Gate: `' + gate['status'] + '`. Đây là “đã rà hết, còn ngoại lệ”, không phải mọi PO đều đã xác nhận.', '',
            'Phạm vi 206 PO được truy trực tiếp từ move và dòng hóa đơn nguồn đã chốt; 36 PO trong baseline 242 không có phụ thuộc trực tiếp trong phạm vi này nên không được tác động. Danh sách và cơ sở chênh nằm trong phase-readiness.json.', '',
            'Đã dùng cùng phương thức của action Confirm RFQ trên v19: `purchase.order.button_confirm()` với danh sách PO. Có mẫu hai PO/một lời gọi và nhóm 25 PO/một lời gọi; ngày lịch sử và kết quả được kiểm tra riêng từng PO. Chỉ các PO qua kiểm tra mới được chọn.', '',
            'Ánh xạ CNH → CNY tái sử dụng quyết định migration đã có; không đổi currency master hoặc tỷ giá. Các PO có nguy cơ tạo supplier master, sai đối tác/sản phẩm/loại phiếu hoặc thiếu đích vẫn giữ nguyên.', '',
            'Mẫu PO nguồn 5275 bị lỗi lưu kết quả local sau khi confirm đã commit. Đã đọc lại chứng minh trạng thái, chuỗi phiếu và không phát sinh hóa đơn/MO/PO mới; phục hồi journal và ngày lịch sử, không confirm lại. Chi tiết trong confirm-po-recovery-5275.json và operations.jsonl.', '',
            'Chưa có thao tác validate receipt, tạo bill, thanh toán, đối soát hay chuyển pha SO. Các phiếu native được sinh do xác nhận PO là đầu ra của bước này, chưa được coi là kho đã chuyển xong.', '',
            '## PO cần xử lý ngoại lệ', '',
            'Một PO có thể có nhiều nguyên nhân; số lượt nguyên nhân không phải số PO.', '',
            '| Nguyên nhân | Số PO/lượt |', '|---|---:|']
    for reason, count in reasons.most_common():
        text.append('| ' + reason + ' | ' + str(count) + ' |')
    text += ['', '| PO nguồn | PO đích | Trạng thái đích | Lý do và thông tin đối chiếu |', '|---|---|---|---|']
    for row in held:
        detail = json.dumps(row['reasons'], ensure_ascii=False).replace('|', '/')
        line_issues = [x for x in row['line_results'] if x.get('issues')]
        if line_issues:
            detail += '; dòng: ' + json.dumps(line_issues, ensure_ascii=False).replace('|', '/')
        text.append('| ' + row['source_name'] + ' (ID ' + str(row['source_id']) + ') | ' + (row['target_name'] or 'thiếu') + ' (ID ' + str(row['target_id']) + ') | ' + str(row['target_state']) + ' | ' + detail + ' |')
    text += ['', 'Bằng chứng: [kiểm chứng toàn bộ PO](phases/confirm-po-verification.json), [gate PO](phases/confirm-po-gate.json), [nhật ký xác nhận](phases/order-confirmation-journal.json), [chuỗi native](phases/native-chain-index.json), [ánh xạ tiền tệ](phases/order-currency-map-evidence.json).', '',
             'Không tự nhập PO còn thiếu, sửa master, đổi partner/sản phẩm trên đơn hoặc sửa chứng từ đã xác nhận để giải quyết ngoại lệ. Các pha sau chưa được thực hiện theo chỉ dẫn dừng của Bruce.']
    (out / 'BAO_CAO_CONFIRM_PO_VA_DIEM_DUNG.md').write_text('\n'.join(text) + '\n', encoding='utf8')
    print(json.dumps(dict(new_confirmed=len(new), verified_confirmed=gate['completed_count'], held=gate['held_count'], target_states=dict(states), stopped=True), ensure_ascii=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence-dir', required=True)
    render(parser.parse_args().evidence_dir)
