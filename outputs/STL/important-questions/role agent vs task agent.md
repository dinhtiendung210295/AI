# So sánh Role-based Agent và Task-based Agent trong quy trình ERP

## Tóm tắt

Role-based Agent và Task-based Agent giải quyết hai lớp khác nhau. Role đại diện cho phạm vi trách nhiệm cần theo dõi xuyên suốt; Task đại diện cho một năng lực hẹp có đầu vào, đầu ra và tiêu chí hoàn thành rõ ràng. Có thể kết hợp hai kiểu: người phụ trách nghiệp vụ điều phối các tác vụ chuyên biệt, sau đó kiểm tra kết quả và chịu trách nhiệm với kết luận.

> Người giao việc mô tả mục tiêu → Role Agent phân rã và điều phối → Task Agent hoặc công cụ xử lý từng phần → bước kiểm chứng độc lập đánh giá kết quả.

Ví dụ trong migration ERP: một Agent phụ trách điều phối đợt migration giữ phạm vi, quyết định đã duyệt và các phụ thuộc; các tác vụ riêng có thể đọc dữ liệu nguồn, kiểm tra ánh xạ, đối chiếu chứng từ hoặc tạo báo cáo sai lệch. Lệnh ghi dữ liệu vẫn phải theo cổng phê duyệt và quy trình đã định.

## Hai kiểu Agent

### Role-based Agent

Role Agent đại diện cho một phạm vi trách nhiệm rộng, tồn tại qua nhiều bước. Nó cần bối cảnh dự án, quy tắc nghiệp vụ, giới hạn quyền hạn và khả năng tổng hợp kết quả.

Ví dụ: **điều phối viên migration** theo dõi phạm vi SO/PO, tồn kho và hóa đơn; dùng ExecPlan để biết thứ tự phụ thuộc; ghi lại ngoại lệ; yêu cầu chuyên môn phù hợp khi có chênh lệch; và chỉ báo hoàn thành khi có kiểm chứng.

Role Agent trả lời câu hỏi: **“Ai chịu trách nhiệm đưa công việc này tới kết quả được kiểm chứng?”**

### Task-based Agent

Task Agent xử lý một năng lực giới hạn với hợp đồng đầu vào/đầu ra cụ thể. Có thể thay Agent bằng script deterministic nếu quy tắc đã rõ và không cần suy luận ngôn ngữ.

Ví dụ:

```text
read_source_orders(scope) -> SourceOrderSnapshot
check_partner_mapping(source_id, target_id, evidence) -> MappingReview
compare_stock_balances(source_snapshot, target_snapshot) -> VarianceReport
classify_exception(record, rules) -> ExceptionCategory
```

Task Agent trả lời: **“Cần thực hiện thao tác nào, với dữ liệu nào, và kết quả được đánh giá ra sao?”**

### Khác biệt chính

| Tiêu chí | Role-based | Task-based |
|---|---|---|
| Trọng tâm | Trách nhiệm và điều phối | Năng lực hoặc thao tác cụ thể |
| Thời gian sống | Nhiều bước, nhiều lượt | Một tác vụ hoặc một nhóm nhỏ |
| Bối cảnh | Dự án và quy tắc nghiệp vụ | Đầu vào cần cho tác vụ |
| Công cụ | Có thể rộng nhưng cần giới hạn theo vai trò | Tối thiểu cho thao tác |
| Kết quả | Tổng hợp, quyết định hoặc chuyển bước | Dữ liệu có cấu trúc, báo cáo, đề xuất |
| Kiểm thử | Đánh giá quyết định và điều phối | Kiểm tra hợp đồng và tiêu chí đầu ra |

Không phải thao tác nào cũng cần một Agent. Truy vấn có quy tắc ổn định, phép tính, kiểm tra schema và so sánh chính xác thường nên chạy bằng công cụ hoặc mã deterministic. Chỉ dùng LLM khi cần diễn giải, phân loại chưa hoàn toàn cố định hoặc tổng hợp thông tin.

## Mô hình kết hợp

```text
AI Operator / người phụ trách
            │
            ▼
Role Agent: điều phối migration
  ├─ đọc ExecPlan và phạm vi được duyệt
  ├─ chia việc theo phụ thuộc
  ├─ gọi tác vụ đọc/đối chiếu phù hợp
  ├─ giữ nhật ký quyết định và ngoại lệ
  └─ tổng hợp bằng chứng, báo trạng thái
            │
      ┌─────┴──────────┐
      ▼                ▼
Task Agent          Công cụ deterministic
rà mapping          đọc XML-RPC, kiểm schema,
phân loại ngoại lệ   tính tổng, kiểm tra trạng thái
      └─────┬──────────┘
            ▼
Kiểm chứng độc lập và cổng phê duyệt
```

Role Agent có thể gọi specialist như một công cụ rồi tiếp tục giữ quyền điều phối; hoặc chuyển quyền xử lý cho specialist khi công việc cần một vai trò riêng. Hai cách tương ứng với các pattern manager/agent-as-tool và handoff được mô tả trong tài liệu OpenAI Agents SDK. citeturn10view5turn0search2

## Chọn Role, Task hay Tool

| Nhu cầu | Lựa chọn phù hợp | Ví dụ migration |
|---|---|---|
| Theo dõi mục tiêu qua nhiều chặng | Role Agent | Điều phối tiến độ và phụ thuộc theo ExecPlan |
| Đọc và tổng hợp hồ sơ có nhiều ngoại lệ | Task Agent | Rà nguồn chứng từ và lập danh sách cần review |
| Áp dụng quy tắc xác định | Tool/script | Kiểm tra trạng thái, ngày, số lượng, khóa định danh |
| Ghi dữ liệu có tác động nghiệp vụ | Quy trình native có cổng duyệt | Chỉ thực hiện theo phạm vi và phê duyệt đã ghi nhận |
| Xác nhận kết quả | Kiểm chứng độc lập | Đọc lại dữ liệu đích và so với snapshot nguồn |

Một task nhỏ không tự động trở thành Agent. Nếu script xác định được kết quả, hãy dùng script. Nếu cần diễn giải ngoại lệ, Agent có thể đưa ra phân loại kèm lý do và bằng chứng; người có thẩm quyền quyết định cách xử lý.

## Quyền hạn, trạng thái và kiểm chứng

- Cấp cho mỗi vai trò và tác vụ quyền tối thiểu cần thiết; tác vụ đọc không cần quyền ghi.
- Giữ dữ liệu chuẩn, ánh xạ đã duyệt, trạng thái journal và quyết định bên ngoài lịch sử hội thoại tự do.
- Ghi nhận đầu vào, phiên bản quy tắc, đầu ra, trạng thái và liên kết evidence để có thể truy nguyên.
- Không xem phản hồi “đã ghi” hoặc trạng thái queue là nghiệm thu; cần kiểm tra độc lập ở đích.
- Với phản hồi RPC không rõ kết quả, đọc lại trạng thái và journal trước khi cân nhắc thử lại để tránh ghi trùng.
- Đặt bước duyệt trước hành động có side effect; không suy diễn phê duyệt từ việc chuẩn bị xong hoặc có khóa thực thi.

Các nguyên tắc này phù hợp với khuyến nghị về least privilege và kiểm soát công cụ trong MCP Security guidance. citeturn11view0turn11view2

## Khuyến nghị

Dùng Role Agent để giữ trách nhiệm và điều phối công việc phức tạp; dùng Task Agent cho năng lực hẹp cần suy luận; dùng công cụ deterministic cho quy tắc rõ ràng. Tách model khỏi vai trò để có thể thay model mà không làm thay đổi ranh giới trách nhiệm. Bắt đầu bằng cấu trúc đơn giản, chỉ tách thêm Agent khi có khác biệt thật về bối cảnh, quyền hạn, công cụ hoặc tiêu chí kiểm thử. citeturn1search5turn5view2turn5view5

> **Role quyết định ai chịu trách nhiệm. Task xác định việc gì cần thực hiện. Tool thực hiện thao tác xác định. Kiểm chứng xác nhận kết quả có đúng hay không.**
