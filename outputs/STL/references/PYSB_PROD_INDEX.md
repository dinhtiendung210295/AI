# PYSB production — điểm tiếp tục

Nguồn **`paoyeang_live`** → đích **`py19-main-33843450`**, công ty **1**. Ưu tiên XML-RPC, không áp dụng skill.

## Hồ sơ hiện hành

- Đọc [CHECKPOINT.md](../../../../outputs/po-move-migration-20261027/CHECKPOINT.md) để tiếp tục; không tìm lại hồ sơ đã mất.
- Tiến độ và cách xử lý ngoại lệ: [EXECPLAN.md](../EXECPLAN.md). Đọc cách xử lý đã có trước khi hỏi Bruce; bổ sung quyết định mới vào dòng tương ứng. Chỉ hỏi **từng ngoại lệ chưa đủ căn cứ**, không tạo thêm Excel.

## Công cụ

| Việc | Công cụ |
|---|---|
| Nhận diện phần đã done, tránh nhập trùng | [recover_done_bindings.py](../../../../outputs/po-move-migration-20261027/recover_done_bindings.py) |
| Receipt và backorder | [prepare_receipts.py](../../../../outputs/po-move-migration-20261027/prepare_receipts.py) → [execute_prepared_receipt.py](../../../../outputs/po-move-migration-20261027/execute_prepared_receipt.py) |
| Cất kho | [prepare_storage.py](../../../../outputs/po-move-migration-20261027/prepare_storage.py) → [execute_storage_queue.py](../../../../outputs/po-move-migration-20261027/execute_storage_queue.py) |
| Trả nhà cung cấp | [execute_supplier_return_chain.py](../../../../outputs/po-move-migration-20261027/execute_supplier_return_chain.py) — wizard native, Stock → Input → Vendors |
| Hợp nhất và đọc lại đủ 551 move | [refresh_bindings.py](../../../../outputs/po-move-migration-20261027/refresh_bindings.py) → [run_final_audit.py](../../../../outputs/po-move-migration-20261027/run_final_audit.py) |

Các script ghi đang giới hạn theo change set/ID cụ thể đã chạy; **đọc và cập nhật phạm vi trước khi dùng, không chạy lại mẫu hoặc queue cũ**. Audit mặc định không xuất Excel.

## Cách làm giữ lại từ lần chạy vừa rồi

- Chứng minh binding bằng External ID/liên kết native và dữ liệu chi tiết; xét cả move done không gắn dòng PO. Tên phiếu hoặc ID số riêng lẻ không đủ.
- Tách theo lần nhận/phiếu nguồn; dùng backorder native và kiểm tra lượng dư. Đọc lại backorder trước nhóm kế tiếp; nếu còn confirmed thì phân bổ đúng phiếu khi đủ tồn đúng lot. Dòng đủ điều kiện có thể chạy riêng, giữ chờ dòng còn ngoại lệ.
- Giữ riêng ngày phiếu, move và chi tiết; khôi phục theo thứ tự **phiếu → move → chi tiết**. UoM khác ID nhưng cùng hệ số quy đổi thì giữ UoM native và lưu bằng chứng, không tự sửa master.
- Dùng nguyên khóa production chung, journal bền vững và đọc lại sau mỗi RPC; mất phản hồi thì xác minh trước, không tự retry. Chỉ xử lý phạm vi đã duyệt; tạo lot/master, tồn tạm hoặc sửa lịch sử done cần quyết định cụ thể.
