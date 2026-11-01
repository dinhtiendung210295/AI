# Bản nháp chia sẻ: kinh nghiệm migration dữ liệu ERP

Tài liệu đã ẩn danh để chia sẻ phương pháp và bài học. Các ví dụ được khái quát hóa; nội dung không thay thế hồ sơ dự án hay bằng chứng nghiệm thu.

## Phần 1 — Các bước thực hiện

### Lập kế hoạch và xác định phạm vi

- Chốt hệ thống nguồn, hệ thống đích, đơn vị phụ trách, kỳ dữ liệu và thời điểm chốt số liệu.
- Xác định thứ tự công việc theo phụ thuộc giữa dữ liệu nền, đơn hàng, giao dịch kho, sản xuất và kế toán.
- Ghi tiêu chí hoàn thành, điểm cần người duyệt, cách lưu nhật ký và cách tiếp tục an toàn khi một bước bị gián đoạn.

### Ánh xạ và chuẩn bị dữ liệu

- Dùng định danh ổn định và bằng chứng truy nguyên để nối bản ghi nguồn với đích; không ghép chỉ dựa trên tên gọi.
- Kiểm tra các quan hệ giữa chứng từ, dòng chi tiết, đơn vị tính, theo dõi lô/serial và trạng thái trước khi ghi.
- Lập danh sách ngoại lệ riêng; không để hệ thống tự chọn cách xử lý khi thiếu căn cứ nghiệp vụ.

### Thực hiện và kiểm tra

- Ưu tiên giao diện/API nghiệp vụ gốc của hệ thống đích; đọc lại trạng thái sau mỗi thao tác ghi.
- Thử trên phạm vi nhỏ, kiểm tra độc lập rồi mới mở rộng theo đợt có kiểm soát.
- Khi phản hồi của hệ thống không rõ, kiểm tra nhật ký và dữ liệu thực tế trước khi cân nhắc chạy lại.
- Tách tiến độ thực hiện khỏi kết quả audit và nghiệm thu toàn phạm vi.

### Đối chiếu cuối kỳ

- Chụp lại phạm vi nguồn và đích theo cùng thời điểm chốt.
- Đo đầy đủ chênh lệch trước khi giải thích nguyên nhân.
- Kiểm tra theo nhiều cấp phù hợp, chẳng hạn tổng thể, vị trí lưu trữ và lô/serial.
- Chỉ kết luận nghiệm thu khi tiêu chí đã thống nhất được đáp ứng và các ngoại lệ còn lại được xử lý đúng thẩm quyền.

## Phần 2 — Lỗi sai và bài học

| Chủ đề | Lỗi sai | Bài học |
| --- | --- | --- |
| Đo tiến độ | Coi trạng thái đã ghi dữ liệu là bằng chứng migration đạt. | Phân biệt đã ghi, đã đọc lại, audit độc lập và nghiệm thu; nêu rõ phạm vi cùng tiêu chí cho mỗi kết luận. |
| Chốt phạm vi | Bỏ sót dữ liệu liên quan hoặc thay đổi tập nguồn mà không lưu căn cứ. | Định nghĩa phạm vi theo thời gian, đơn vị và quan hệ nghiệp vụ; lưu baseline cùng lịch sử điều chỉnh. |
| Ghép bản ghi | Ghép dữ liệu chỉ theo tên hoặc một trường tham chiếu. | Dùng định danh, nguồn gốc ánh xạ và các quan hệ chứng từ; kiểm tra lại các trường nghiệp vụ quan trọng. |
| Xử lý ngoại lệ | Để bảng dữ liệu hoặc AI tự quyết cách sửa ngoại lệ. | Ghi rõ bằng chứng và phương án; người có thẩm quyền quyết định khi quy tắc hiện có chưa bao phủ. |
| Quy mô đợt xử lý | Chọn đợt quá nhỏ hoặc quá lớn mà không cân nhắc khả năng kiểm soát và phục hồi. | Chọn kích thước theo rủi ro, tốc độ kiểm tra và khả năng khôi phục; mở rộng sau khi pilot đạt. |
| Chọn mô hình AI | Dùng một mức mô hình và suy luận cho mọi loại công việc. | Chọn theo độ khó, rủi ro và mức độ lặp lại; đánh giá bằng kết quả và kiểm tra hồi quy. |
| Quản lý tệp | Xóa tệp được tạo trong quá trình làm việc khi chưa xác định vai trò của chúng. | Quy định cấu trúc thư mục, nơi lưu bằng chứng và cách dọn dẹp trước khi bắt đầu. |
| Phối hợp với AI | Giao việc rồi bỏ qua việc theo dõi các điểm cần quyết định. | Duy trì nhịp kiểm tra phù hợp; giao việc độc lập trong lúc chờ nhưng quay lại xử lý các cổng duyệt và ngoại lệ. |

## Phần 3 — Câu hỏi mở rộng về AI

### Role Agent, Task Agent và Skill khác nhau thế nào?

- Role Agent giữ trách nhiệm và điều phối; Task Agent thực hiện một mục tiêu giới hạn; Skill đóng gói cách làm có thể dùng lại.
- Các khái niệm này ở những lớp khác nhau và có thể phối hợp trong cùng quy trình.

Đọc thêm: [Role Agent và Task Agent](important-questions/role%20agent%20vs%20task%20agent.md), [Skill trong kiến trúc Agent](important-questions/skill%20with%20agent%20context%201.md).

### Khi đã có Agent và Skill, có cần ExecPlan không?

- Skill hướng dẫn cách làm cho một nhóm công việc; ExecPlan giữ mục tiêu, phụ thuộc, trạng thái và quyết định của một công việc dài.
- Với công việc phức tạp, kế hoạch cần đủ ngắn để cập nhật và đủ rõ để tiếp tục an toàn.

Đọc thêm: [ExecPlan và Skill](important-questions/execplan%20with%20skill%20context.md), [Tối ưu ExecPlan](important-questions/t%E1%BB%91i%20%C6%B0u%20exec%20plan.md).

### AI học từ lỗi thế nào?

- Phản hồi hữu ích nêu lỗi, bằng chứng và điều kiện đúng; bài học cần được kiểm tra trước khi trở thành quy tắc dùng lại.
- Giữ rõ đâu là quyết định đã duyệt và đâu mới là giả thuyết.

Đọc thêm: [Reflection](important-questions/reflextion.md), [Cấu trúc Skill](important-questions/skill%20template.md).
