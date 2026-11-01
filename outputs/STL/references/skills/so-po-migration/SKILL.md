---
name: so-po-migration
description: Chuẩn bị Excel nhập SO/PO từ Odoo v14 sang v19 và đối chiếu sau nhập bằng bộ công cụ PYSB tháng 7/2026 hiện có. Dùng để review hoặc thực hiện phạm vi SO/PO dạng nháp; chưa hỗ trợ cập nhật chứng từ đã tồn tại hoặc chuyển đầy đủ lịch sử giao dịch.
---

# Chuyển dữ liệu SO/PO

Bản cơ sở để Bruce review trước khi mở rộng thành “Full historical data migration”. Hai script trong `scripts/` có nguồn từ `test_script/` của workspace; bản trong skill đã bổ sung chặn ghép đối tác khác tên chỉ dựa trên VAT.

## Khả năng hiện có

| Bước | Công cụ | Kết quả |
|---|---|---|
| Chuẩn bị | [test_prepare_july_2026_so_po_migration.py](scripts/test_prepare_july_2026_so_po_migration.py) | Đọc v14/v19, ánh xạ, tạo Excel SO/PO, file phụ thuộc và báo cáo preflight |
| Nhập | Tính năng Import gốc của Odoo, do người dùng thao tác | Đưa file đã kiểm tra vào v19; bộ script chưa có phần tự động nhập |
| Đối chiếu | [test_validate_july_2026_so_po_migration.py](scripts/test_validate_july_2026_so_po_migration.py) | Đọc v14/v19, xuất tổng hợp và danh sách sai lệch |

Hai script kết nối trực tiếp XML-RPC qua `/xmlrpc/2/common` và `/xmlrpc/2/object`, dùng tài khoản/API key hoặc mật khẩu từ file môi trường. Chúng không gọi MCP, browser use, SQL hoặc API ghi dữ liệu. `OdooReader.call` là hàm gọi phương thức tổng quát; các luồng hiện có chỉ dùng thao tác đọc, không phải lớp bảo vệ kỹ thuật cấm ghi.

## Cách sử dụng

1. Xác định nguồn/đích và công ty. Đọc [giới hạn hiện tại](references/current-limitations.md) trước khi chạy; kiểm tra trường tùy chỉnh và quy tắc ngày trên đúng môi trường.
2. Từ thư mục gốc workspace, chạy script chuẩn bị với đường dẫn môi trường và thư mục kết quả riêng cho lần chạy. Không dùng mặc định môi trường cũ hoặc ghi đè báo cáo lần trước.
3. Review sheet Exceptions, ánh xạ đối tác/sản phẩm và file SO/PO. Script vẫn có thể xuất file khi còn ngoại lệ; xuất file thành công chưa có nghĩa đủ điều kiện nhập. Trước khi ghi, xác minh danh tính đối tác độc lập với bảng ánh xạ đã chuẩn bị; đối chiếu PO với chính bảng ánh xạ không phát hiện được bảng ánh xạ sai.
4. Với phạm vi đã được cho phép, dùng Import gốc của Odoo để tải file, kiểm tra mapping và chạy Test trước Import. Giữ External ID của đầu chứng từ và dòng. File phụ thuộc phải được review riêng vì có thể tạo/cập nhật dữ liệu nền đã làm sạch.
5. Chạy script đối chiếu trên đúng đích vừa nhập; xem từng ngoại lệ và kiểm tra bổ sung các mục script chưa bao phủ. Không dùng “0 ngoại lệ” làm bằng chứng đối chiếu toàn bộ lịch sử.
6. Nếu update một số SO/PO đã tồn tại, thì nên ko nên dùng file excel, nên dùng XML-RPC để update từng chứng từ

```powershell
python '.agents/skills/FC+TC/6-Data migration/so-po-migration/scripts/test_prepare_july_2026_so_po_migration.py' --v14-env '<file môi trường nguồn>' --v19-env '<file môi trường đích>' --output-dir '<thư mục kết quả mới>'
python '.agents/skills/FC+TC/6-Data migration/so-po-migration/scripts/test_validate_july_2026_so_po_migration.py' --v14-env '<file môi trường nguồn>' --v19-env '<file môi trường đích>' --output '<file đối chiếu mới.xlsx>'
```

Cần Python và `openpyxl`. Hai script phải ở cùng thư mục vì script đối chiếu nạp script chuẩn bị. Giữ bí mật nội dung file môi trường.

## Đối tác khác tên nhưng trùng VAT

VAT có thể là mã dùng chung cho đối tác ngoại quốc, ví dụ `EI00000000030`; không coi VAT là định danh duy nhất. Khi tên nguồn/đích khác nhau, không tự ghép chỉ vì VAT khớp, kể cả chỉ tìm được một ứng viên. Cần xác minh thêm External ID nguồn–đích cùng model `res.partner` và bản ghi thực tế, hoặc đưa vào review khi chưa đủ chứng cứ; không tự tạo đối tác thay thế.

Script chuẩn bị giữ VAT để tìm ứng viên nhưng không dùng VAT làm căn cứ duy nhất cho nhánh khác tên; trường hợp này vào Exceptions với lý do `name_mismatch_vat_only`. Script cơ sở chưa tự xác minh External ID đối tác. Quy tắc áp dụng cả nhà cung cấp PO, khách hàng SO và địa chỉ liên quan. Trường hợp đã gặp: SUPERLINK và BEST PRINTING cùng VAT nhưng là hai nhà cung cấp khác nhau.

Nếu yêu cầu là cập nhật SO/PO đã có, đổi công ty/kỳ, giữ trạng thái hoàn tất hoặc chuyển thêm QUO/DO/INV/Repack/MO: báo rõ phần chưa hỗ trợ và thiết kế bổ sung trước khi thực thi. Không tự xác nhận đơn để làm giống v14 vì có thể sinh thêm chứng từ và tác động tồn kho.

Trong nhiệm vụ PYSB đang trao đổi: staging trước; AI đối chiếu → Bruce duyệt → Sue duyệt trước live. Skill này chưa triển khai đầy đủ yêu cầu đó và chưa phải skill “Full historical data migration”.
