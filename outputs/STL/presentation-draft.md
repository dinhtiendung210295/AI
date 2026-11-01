# Bản nháp nội dung thuyết trình: migration dữ liệu PYSB T7–T10/2026

> Bản nháp để Bruce rà nội dung trước khi làm slide. Số liệu là các mốc đã ghi trong hồ sơ, không tự động là kết quả nghiệm thu toàn kỳ. Lịch sử session nằm trong [session-history/](session-history/); các bài phân tích câu hỏi nằm trong [important-questions/](important-questions/).

## Phần 1 — Các bước thực hiện của toàn bộ quy trình

### Planning — cách migrate và thứ tự thực hiện

- Chốt phạm vi tháng 7–10/2026 theo ngày nghiệp vụ giờ Malaysia, db nguồn–đích;
- Dùng skill để chuẩn bị plan cho phiên dài
- Thứ tự theo phụ thuộc: **PO confirm → SO confirm → phiếu kho từ PO/SO và MO/DO → Invoice/Bill → Other move → audit từng nhóm và final verify**.
- Tiêu chí kiểm tra 

Nguồn: [skill SO/PO](references/skills/so-po-migration/SKILL.md), [skill full historical migration](references/skills/full-historical-migration/SKILL.md), [session lên kế hoạch](session-history/sessions/26-plan-01a1773d-638c-7dd0-816f-e7ff124aac1a.md), [ExecPlan](references/EXECPLAN.md).


### Ánh xạ

- Dùng External ID, trường ref , liên kết nghiệp vụ để tạo ánh xạ

Nguồn: [ExecPlan](references/EXECPLAN.md), [session đối chiếu PO move](session-history/sessions/26-stock-01a17770-d37c-75b0-b61f-bf4c93b53c11.md).


### Công cụ XML-RPC

- XML-RPC là kênh chính để đọc v14/v19, kiểm tra dữ liệu trước khi ghi và gọi phương thức nghiệp vụ native của Odoo trên v19, như confirm PO/SO hoặc validate phiếu kho.
- Công cụ theo từng nhóm tạo manifest, mapping, hàng đợi và journal. Trước mỗi đợt kiểm tra đúng database, công ty, phạm vi, dữ liệu nền và phụ thuộc; thử mẫu rồi mới mở rộng theo lô.
- Sau lệnh ghi, đọc lại bản ghi và liên kết phát sinh. Nếu RPC mất phản hồi, kiểm tra journal và trạng thái thực tế trước khi quyết định tiếp tục; không gửi lại ngay.
- Riêng bước Test/Import SO từng dùng JSON-RPC vì wizard không tương thích hoàn toàn với XML-RPC

Nguồn:  [session PO confirm](session-history/sessions/25-confirm-01a1733d-e280-7ac2-ad10-174de032ba69.md), [session PO move](session-history/sessions/26-stock-01a17770-d37c-75b0-b61f-bf4c93b53c11.md), [session import SO](session-history/sessions/23-orders-01a1695d-f0a0-7c11-9117-1e793ca11804.md).

### Audit từng nhóm và final verify


- Final verify toàn kỳ là bước riêng sau audit nhóm: chụp lại phạm vi nguồn–đích, đo toàn bộ tồn thực tại cutoff, rồi mới truy nguyên chênh lệch do tồn tạm, điều chỉnh và nguồn cung. Kết quả final verify chưa được gọi là đạt nếu vẫn còn chênh lệch hoặc ngoại lệ chưa đóng.

Nguồn: [kế hoạch final verify](references/FINAL_VERIFY_PLAN.md), [checkpoint final verify](references/FINAL_VERIFY_CHECKPOINT.md)


## Phần 2 — Lỗi sai và bài học

| Chủ đề | Lỗi sai | Bài học |
| --- | --- | --- |
| Đo tiến độ| Không phân biệt rõ **đã ghi**, **đã audit**  | Cần phân biệt rõ trạng thái vì lúc chạy dễ xảy ra lỗi
| Chốt phạm vi | Bỏ sót move liên quan đơn ngoài kỳ | Cần cover trước các move này |
| Ghép chứng từ | Ghép move lại vì nghĩ là đơn giản hơn, chỉ cần số received/delivered trên SO/PO đúng | Không nên messup ánh xạ, giữ ánh xạ 1-1 sẽ tốt hơn  |
| Ngoại lệ nghiệp vụ | Để file excel | Để cho AI tự quyết |
| writer| tiền kiểm, chạy, audit theo mẻ quá nhỏ | mẻ nên to max luôn |
| chọn model| chọn front tier model light level làm mặc định | suy nghĩ dùng front tier, thực thì dùng model ở giữa, thực thi task dễ đã làm nhiều lần rồi skill và plan đã iterate nhiều lần rồi dùng SLM . Đổi reasoning level dựa trên cảm giác khi làm cùng AI |
| xóa file| xóa file của AI vì nghĩ là rác | quản lý thư mục từ đầu, ko được xóa |
| phối hợp với AI| cho AI chạy rồi đi làm việc khác | nên side ask, deep reasearch hoặc nghỉ ngơi |


## Phần 3 — Các câu hỏi quan trọng Bruce đã chuẩn bị

> Nội dung là câu hỏi mở rộng về cách tổ chức AI cho công việc dài và phức tạp; không liên quan trực tiếp đến ERP/migration ; câu trả lời có tính assumption cao

### Role Agent, Task Agent và Skill khác nhau thế nào?

- Role Agent xác định trách nhiệm và góc nhìn chuyên môn; Task Agent được giao một kết quả cụ thể -> 2 thứ này ko cùng level
- Skill khá giống Task Agent nhưng task agent có thể có context và model riêng. Skill có thể nằm trong task agent và ngược lại -> đơn giản thì dùng skill trước rồi khi tối ưu chi phí thì nâng cấp lên Task Agent sau


Nguồn Bruce chuẩn bị: [role agent vs task agent.md](<important-questions/role agent vs task agent.md>), [skill with agent context 1.md](<important-questions/skill with agent context 1.md>).



### Khi đã có agent và skill, có cần ExecPlan không?

- Skill chỉ là một mảnh nhỏ và có tính chất mẫu
- Expec plan gom nhiều skill và có tính chất cụ thể

Nguồn Bruce chuẩn bị: [execplan with skill context.md](<important-questions/execplan with skill context.md>), [tối ưu exec plan.md](<important-questions/tối ưu exec plan.md>).



### AI học từ lỗi thế nào để lần sau làm tốt hơn?

- Phản hồi của người làm nghiệp vụ cần chỉ rõ lỗi, bằng chứng và điều kiện đúng; nếu để AI tự tóm tắt thất bại mà thiếu kiểm chứng dễ dẫn tới bài học sai.

Nguồn Bruce chuẩn bị: [reflextion.md](important-questions/reflextion.md), [skill template.md](<important-questions/skill template.md>).



