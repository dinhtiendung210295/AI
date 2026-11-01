# Tự động Test/Import

Kiểm tra chữ ký phương thức trên đúng Odoo đích. Mã nguồn v19 trong workspace: `community/addons/base_import/models/base_import.py`, `parse_preview(options, count=10)` và `execute_import(fields, columns, options, dryrun=False)`.

1. Qua API được đích hỗ trợ, tạo wizard `base_import.import` với model SO/PO, file Excel base64, tên/loại file. Dùng preview xác minh mapping cột → trường và options.
2. Gọi `execute_import(..., dryrun=True)` cho một chứng từ đầy đủ dòng. Xem cả lỗi trả về và exception. Test rollback thay đổi database; cần kiểm tra riêng tác động ngoài database của tích hợp tùy chỉnh trên staging.
3. Test đạt và phạm vi staging được phép thì gọi `dryrun=False`, dùng cùng file/mapping/options. Lưu phản hồi, tìm ID đích qua External ID và đọc lại để đối chiếu đầu/dòng, đối tác, sản phẩm, thuế, lượng, đơn vị, giá, tiền, ngày và trạng thái. Mẫu đạt mới Test/Import lô; mẫu không chứng minh cả lô đạt.
4. Timeout/mất kết nối: kiểm tra record đã tạo/cập nhật trước khi thử ghi lại. Lưu nhật ký môi trường/công ty/model, dấu vân tay file, mapping/options, kết quả Test/Import và ID nguồn/đích; không lưu bí mật kết nối.

## Ngoại lệ

Dùng MCP đọc record và đối tác/sản phẩm/thuế/đơn vị liên quan. Sửa mapping/file hoặc dữ liệu trong phạm vi được phép, rồi Test lại. Thiếu quyết định nghiệp vụ hoặc cần sửa dữ liệu nền ngoài phạm vi thì giữ chứng từ lại và báo duyệt; không tự tạo đối tác/sản phẩm để vượt lỗi. Cùng lỗi không có thông tin mới thì dừng chứng từ đó.

Báo cáo: mã/loại chứng từ, External ID, môi trường, lỗi, nguyên nhân, xử lý, kết quả Test/đối chiếu, quyết định cần duyệt và link nguồn/đích. Lấy URL/action đang hoạt động hoặc kiểm tra link dựng từ model/ID mở đúng record; phân biệt staging/live. Chưa tạo record đích thì ghi rõ và dẫn nguồn. PYSB: AI đối chiếu → Bruce duyệt → Sue duyệt trước live.

## Chọn Excel và API

SO/PO nháp: ưu tiên Excel để review + API gọi Import gốc để tự động thực thi. File đã review phải trùng file nhập; thay dữ liệu thì đánh giá lại phần thay đổi.

Lịch sử đầy đủ/trạng thái/quan hệ DO–INV–Repack/MO: thiết kế API gọi phương thức nghiệp vụ phù hợp; Excel có thể chỉ là báo cáo review. `create/write` không tự thay thế xác nhận/hoàn tất hoặc bảo đảm tồn kho/kế toán đúng. Chọn theo kết quả staging, không chỉ tốc độ.

Gói hiện chưa có runner tự động nhập. Triển khai và kiểm chứng trước khi thực thi luồng này; không coi cập nhật hướng dẫn là đã hoàn thành mã tự động hóa.
