# Giới hạn cần review trước khi dùng

## Phạm vi và cách ghi dữ liệu

- Công ty ID `1`, kỳ `[2026-07-01, 2026-08-01)` và tên file tháng 7 đặt cố định; CLI chưa có tham số công ty/kỳ.
- Chỉ lấy SO trạng thái `sale/done`, PO `purchase/done`; loại quotation template. Không chuyển báo giá chưa xác nhận, DO, INV, Repack/MO hoặc trạng thái hoàn tất.
- Script chuẩn bị tìm `x_studio_v14_reference_studio` trên đích rồi **bỏ qua** đơn đã tồn tại. Đây là công cụ chuẩn bị các đơn còn thiếu, không phải công cụ cập nhật/ghi đè đơn cũ.
- File có External ID `pysb_v14.*` cho đơn và dòng để dùng với Import Odoo. Hành vi cập nhật của Import không thay đổi thực tế rằng script đang loại đơn đã có trước khi xuất.
- Script đối chiếu kỳ vọng SO/PO đích ở `draft`. Không bảo đảm lịch sử giao hàng, lập hóa đơn, tồn kho hoặc kế toán.
- Chưa có runner tự động gọi wizard Import trong gói này. Luồng yêu cầu mới: Excel một chứng từ → API Test/Import → đối chiếu; MCP điều tra ngoại lệ và báo cáo kèm link record. Cần triển khai/kiểm chứng runner trên staging; không dùng nhập thủ công làm luồng mặc định và không báo tự động hóa đã hoàn thành.

## Ánh xạ và dữ liệu nền

- Đối tác được dò ứng viên theo tên/ref/VAT và thông tin liên hệ; không phải ánh xạ ID nguồn được chứng minh. Nhánh khác tên không còn tự ghép bằng VAT đơn lẻ; trả ngoại lệ `name_mismatch_vat_only`. Script chưa tự xác minh External ID đối tác; xem quy tắc đối tác khác tên trong `SKILL.md`. Sản phẩm dò barcode/mã/tên cùng một số quy tắc riêng. Phải review các kết quả trước khi dùng cho dữ liệu đã làm sạch.
- Có quy tắc alias, đơn vị, trường Studio và dữ liệu phụ thuộc riêng cho PYSB. Không coi đây là quy tắc chung cho mọi công ty.
- File phụ thuộc có thể gồm sản phẩm, điều khoản thanh toán, vị trí và route. Script chỉ tạo file; việc nhập chúng có thể thay đổi dữ liệu nền và cần nằm trong phạm vi đã cho phép.
- File SO có trường tham chiếu Woo cũ; đây chỉ là dữ liệu trường trên đơn, không có thao tác kết nối hoặc đồng bộ Woo/LHDN.

## Độ bao phủ của đối chiếu

- Có kiểm tra thiếu đơn/dòng qua External ID, tham chiếu, trạng thái nháp, số dòng, kho/điểm nhận, tổng tiền; kiểm tra một số dữ liệu dòng như mô tả, lượng, đơn vị, giá, chiết khấu SO và route SO.
- Chưa kiểm tra đầy đủ danh tính sản phẩm/đối tác, thuế từng dòng, quan hệ dòng–đơn hoặc chứng từ thừa. Việc đọc một trường không có nghĩa trường đó được so sánh.
- Quy tắc ngày SO cộng cố định 7 giờ; ngưỡng số tiền cố định 0,01 và quy đổi `UNIT` → `Units`. Cần xác minh thay vì mặc định đúng cho dữ liệu hiện tại.
- Ngày lịch sử PO được chuẩn bị từ `date_approve` hoặc `date_order`, nhưng bộ lọc kỳ dùng `date_order`; chưa có kiểm tra tương đương đầy đủ ngày PO ở báo cáo sau nhập.
- Đây là báo cáo đối chiếu một phần; không phải bằng chứng đáp ứng toàn bộ tiêu chí của kế hoạch Full historical data migration.

## Hướng mở rộng sau review

Ưu tiên làm rõ: tạo mới/cập nhật/không đổi; bảng ánh xạ tin cậy; tham số môi trường/công ty/kỳ; kiểm tra đầy đủ đơn và dòng; rồi bổ sung các loại chứng từ cùng trạng thái, quan hệ, ngày lịch sử và tác động tồn kho/kế toán. Chưa triển khai các phần này trong bản cơ sở.
