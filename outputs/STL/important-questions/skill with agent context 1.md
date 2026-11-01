# Skill có cần thiết khi đã có Role-based Agent và Task-based Agent?

## Tóm tắt

Role, Task và Skill giải quyết ba vấn đề khác nhau:

- **Role** xác định trách nhiệm, phạm vi và cách phối hợp.
- **Task** xác định một đơn vị công việc cần hoàn thành.
- **Skill** đóng gói năng lực và quy trình có thể tái sử dụng.

Skill hữu ích khi nhiều vai trò hoặc tác vụ cần cùng một bộ hướng dẫn, quy tắc, script và tài liệu tham khảo. Không cần biến mọi hướng dẫn thành Skill: chỉ tách khi có nhu cầu tái sử dụng hoặc cần quản lý phiên bản và kiểm thử riêng.

> Người dùng giao mục tiêu → Role Agent điều phối → Task Agent/công cụ thực hiện → Skill cung cấp quy trình dùng lại → người hoặc bước kiểm chứng xác nhận kết quả.

Ví dụ migration ERP: Role Agent điều phối đợt migration; Task Agent rà ánh xạ một nhóm đối tác; Skill cung cấp quy trình kiểm tra định danh, External ID, bằng chứng và cách ghi nhận ngoại lệ.

## Phân biệt Role, Task và Skill

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Role Agent | Ai chịu trách nhiệm và điều phối? | Điều phối viên migration theo dõi phạm vi, phụ thuộc và quyết định |
| Task Agent | Năng lực nào cần thực hiện? | Phân loại ngoại lệ SO theo bộ quy tắc đã duyệt |
| Skill | Quy trình hoặc kiến thức nào dùng lại? | Hướng dẫn đối chiếu SO/PO, kèm script và tiêu chí kiểm tra |
| Tool | Thao tác nào chạy theo quy tắc xác định? | Đọc XML-RPC, tính chênh lệch, xác nhận schema |

Skill không phải một Agent. Nó có thể chỉ gồm hướng dẫn; cũng có thể kèm script, tài liệu tham khảo, biểu mẫu hoặc dữ liệu mẫu. Đặc tả Agent Skills dùng `SKILL.md` làm điểm vào và hỗ trợ tài nguyên bổ sung cùng cơ chế nạp dần theo nhu cầu. citeturn4view0turn4view1

## Ví dụ cấu trúc Skill

```text
check-order-mapping/
├── SKILL.md
├── references/
│   ├── identity-rules.md
│   └── exception-categories.md
├── scripts/
│   └── compare_order_keys.py
└── assets/
    └── review-template.xlsx
```

`SKILL.md` nêu khi nào dùng, các bước thực hiện, yêu cầu đầu vào, cách xử lý ngoại lệ và cách kiểm tra kết quả. Script hỗ trợ phần có thể tự động hóa; quyết định nghiệp vụ chưa được duyệt vẫn phải đưa ra review.

Một quy trình kiểm tra ánh xạ có thể dùng chung bởi Role Agent điều phối SO/PO, Task Agent rà một chứng từ hoặc người review thủ công. Skill giữ quy tắc nhất quán, còn mỗi lần chạy lưu input, kết quả và evidence riêng.

## Khi nào nên tạo Skill?

Nên tạo Skill khi một hoặc nhiều điều sau đúng:

- Cùng quy trình được dùng lặp lại bởi nhiều người, Agent hoặc tác vụ.
- Các bước có thứ tự, điều kiện dừng hoặc kiểm soát rủi ro cần được áp dụng nhất quán.
- Có script, biểu mẫu hoặc nguồn tham khảo đi kèm cần phiên bản hóa.
- Có thể viết tiêu chí để kiểm thử chất lượng đầu ra.

Chưa cần tạo Skill nếu hướng dẫn ngắn, chỉ dùng một lần, còn thay đổi liên tục hoặc chưa có người chịu trách nhiệm duy trì. Bắt đầu bằng checklist đơn giản rồi tách thành Skill khi nhu cầu tái sử dụng được xác nhận. citeturn5view5turn4view3

## Kết hợp trong một quy trình

```text
Role Agent: điều phối migration
  ├─ đọc phạm vi và trạng thái trong ExecPlan
  ├─ gọi Task: rà ánh xạ SO/PO
  │     └─ dùng Skill kiểm tra định danh và External ID
  ├─ gọi Tool: so sánh số lượng và trạng thái
  ├─ chuyển ngoại lệ chưa đủ bằng chứng cho người review
  └─ tổng hợp kết quả sau kiểm chứng độc lập
```

Skill có thể hướng dẫn Agent gọi một công cụ hoặc thực hiện các bước đọc/đánh giá. Skill không tự cấp quyền, không thay thế phê duyệt, và không biến một đầu ra dự kiến thành kết quả đã được xác nhận.

## Quản lý trạng thái và an toàn

- Để dữ liệu chuẩn, mapping đã duyệt, journal và trạng thái thực thi trong nguồn có thể truy nguyên; không dựa vào trí nhớ hội thoại làm hồ sơ duy nhất.
- Giới hạn quyền theo tác vụ: bước đọc không cần quyền ghi; ghi dữ liệu phải qua cổng phê duyệt phù hợp.
- Lưu phiên bản Skill và quy tắc áp dụng cùng evidence của mỗi lượt.
- Khi kết quả thực thi không rõ, đọc lại trạng thái đích và journal trước khi chạy lại.
- Gỡ hoặc thay Skill cần kiểm tra nơi đang dùng, chuyển đổi phiên bản và chạy lại bộ đánh giá liên quan.

Security guidance cho công cụ cũng nhấn mạnh xác thực đầu vào, kiểm soát quyền, giới hạn truy cập và audit. citeturn4view5

## Đánh giá và duy trì

Kiểm thử Skill theo nhiều lớp:

1. **Kiểm tra cấu trúc:** file vào, liên kết, script và mẫu đều tồn tại.
2. **Kiểm tra bước xử lý:** ví dụ đạt, thiếu dữ liệu, mapping mơ hồ và dữ liệu không hợp lệ.
3. **Kiểm tra quyền:** quy trình đọc không phát sinh ghi; quy trình ghi dừng khi chưa có điều kiện cần thiết.
4. **Kiểm tra kết quả:** người hoặc bước độc lập đối chiếu đầu ra với nguồn dữ liệu.

Theo dõi tỷ lệ hoàn thành, ngoại lệ bị phân loại sai, kết quả cần sửa, thời gian xử lý và lỗi do phiên bản thay đổi. Khi sửa Skill, dùng cùng bộ tình huống trước/sau để phát hiện hồi quy.

## Kết luận

Role-based Agent và Task-based Agent tổ chức trách nhiệm và công việc; Skill tổ chức năng lực được dùng lại. Hãy thêm Skill khi quy trình lặp lại và có thể duy trì, không phải chỉ vì hệ thống đã có Agent. Cấu trúc nên bắt đầu đơn giản và tăng mô-đun theo bằng chứng về nhu cầu tái sử dụng. citeturn4view3turn5view5

> **Role chịu trách nhiệm. Task hoàn thành một mục tiêu giới hạn. Skill hướng dẫn cách làm có thể tái sử dụng. Tool thực hiện thao tác xác định.**
