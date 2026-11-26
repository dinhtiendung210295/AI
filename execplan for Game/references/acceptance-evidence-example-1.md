# Ví dụ Acceptance evidence

- Nguồn ví dụ từ một project migration dữ liệu đã done, toàn bộ project đó không được đưa kèm ví dụ , ví dụ này không phản ánh trạng thái công việc hiện tại


## Tiêu chí nghiệm thu

- Các Sale order lines có trường "deliverd qty" và "invoiced qty" giống như hệ thống cũ
- Các Sale Order, Stock move, Invoice có ngày giống như thế thống cũ

## Output

| Trạng thái | Số SO |
|---|---:|
| pending — chưa ghi trong nhóm225, gồm gate held hiện tại | 219 |
| interrupted — ghi một phần chưa giải quyết | 0 |
| held — UoM 5KGS archived, chưa ghi | 3 |
| operator-handled — ba SO trả hàng Bruce tự xử lý | 3 |
| success — đã xử lý thành công và hậu kiểm | 10 |

- Chi tiết trong project nguồn: `so-production.json`.


## Decision log

| Câu hỏi | Câu trả lời |
|---|---|
| confirm SO tự sinh chuỗi PICK → PACK → DELIVERY đang mở trên V19 không? | Không, trên v19 confirm SO chỉ sinh PICK thôi |
| sử dụng tài khoản native của sản phẩm v19 hay sử dụng tài khoản giống v14 | Native |
| không tìm thấy saleperson và saleteam đích | tìm saleperson theo tên login, ignore saleteam |
| nên lưu ánh xạ sale order, sale order line, stock move,stock move line riêng lẻ hay trong cùng một file? | cùng một file cho mỗi SO/change-set |
| không tìm thấy ánh xạ delivery address? | dùng khách hàng chính |
| không tìm external ID của lot đích | dùng tên lot |
| cảnh báo lot hết hạn | ignore |
| thiếu tồn để xuất | cấp tồn tạm |
| UoM của sản phẩm nguồn và đích khác nhau | ignore |
| Nghi ngờ valuation giá vốn và accounting thày đổi bất thường | ignore |
| Held: reservation method khác gate. | ignore |
| không tìm thấy ánh xạ product | check `.agents\long-workflow\py-oct-26-31\planning\master-mapping-evidence.md`, nếu vẫn ko thấy thì tạo trên v19 |
| base-price rule không cho phép base_price ≤ 0 và is_free = False | đổi cờ is_free |
| không tìm thấy ánh xạ invoice address hoặc delivery address | dùng contact cha chính |

## Checkpoint

| Thời điểm/mốc | Thông tin chính | File chi tiết trong project nguồn |
|---|---|---|
| 15/11/2026 | Tiến độ, quyết định Bruce, master change và STOP/no_retry | `so-production-checkpoint-20261115.md` |
| 13/11/2026 — tổng 10/235 SO | Thêm 66419 → 9653, 66477 → 9654, 66478 → 9655 verified độc lập; tổng 11 dòng; nhóm225 đã hoàn tất 6 SO | `../../../../outputs/so-remaining-preflight-2026-11-13T042128.403544_0000/batch225-continuation-2026-11-13T060942.270885_0000/execution/independent-2026-11-13T061917.460449_0000.json` |
| 13/11/2026 — SO thử 66312 / SO-56569 | Verified 1/235 | `so-production-checkpoint-66312-20261113.md` |
| 13/11/2026 — SO thử 66179 / SO-56608 | Có delivered và invoiced, verified 2/235 | `so-production-checkpoint-66179-20261113.md` |
| 13/11/2026 — SO thử 66189 / SO-56544 | Ba chặng done + invoice, verified 3/235 | `so-production-checkpoint-66189-20261113.md` |
| 13/11/2026 — bắt đầu phần còn lại | SO-56571 verified, 4/235; ba SO held do UoM archived | `../../../../outputs/so-remaining-preflight-2026-11-13T042128.403544_0000/RESULT-PROGRESS.md` |
| 13/11/2026 — batch225 | Thêm 2 SO verified, tổng 6/235; SO-56707 → 9652 dừng vì lot hết hạn, chờ quyết định Bruce | `../../../../outputs/so-remaining-preflight-2026-11-13T042128.403544_0000/BATCH225-STOP-EXPIRY.md` |
| 13/11/2026 — recovery SO-56707 → 9652 | Verified độc lập, invoice 88000; tổng 7/235. Áp dụng quyết định expiry ignore đã có, không cần duyệt lại | `../../../../outputs/so-remaining-preflight-2026-11-13T042128.403544_0000/batch225-plan-2026-11-13T053822.733544_0000/execution/66382/recovery-expiry/execution/independent-2026-11-13T060855.328623_0000.json` |
