# Hướng dẫn lập và thực thi ExecPlan cho Codex

> **Mục đích:** Tài liệu quy định cách Codex lập, thực hiện và duy trì kế hoạch cho những công việc lập trình phức tạp, kéo dài hoặc có nhiều bước phụ thuộc. Đây là bản hướng dẫn **biên soạn bằng tiếng Việt**, dựa trên các nguyên tắc của bài *Using PLANS.md for multi-hour problem solving* trong OpenAI Cookbook; **không phải bản dịch nguyên văn**.
>
> **Nguồn tham khảo:** https://developers.openai.com/cookbook/articles/codex_exec_plans

## 1. ExecPlan là gì?

**ExecPlan** (Execution Plan) là một tài liệu Markdown mô tả đầy đủ cách biến một yêu cầu thành một thay đổi phần mềm **hoạt động được và kiểm chứng được**. ExecPlan vừa là kế hoạch triển khai, vừa là nhật ký tiến độ và quyết định kỹ thuật.

Độc giả của mỗi ExecPlan có thể là một phiên Codex hoàn toàn mới: chỉ có mã nguồn hiện tại và tệp kế hoạch, không có ký ức về những cuộc trò chuyện trước. Vì vậy, kế hoạch phải tự giải thích được mọi thông tin quan trọng để người hoặc agent khác có thể tiếp tục công việc.

`PLANS.md` là **quy tắc viết và thực hiện kế hoạch**. Mỗi **ExecPlan** là một tệp kế hoạch cụ thể cho một tính năng hoặc đợt thay đổi. Không dùng `PLANS.md` làm nơi ghi tiến độ của tất cả công việc.

## 2. Khi nào phải dùng ExecPlan?

Nên tạo ExecPlan khi công việc có một hoặc nhiều đặc điểm sau:

- Phải thay đổi nhiều mô-đun, nhiều hệ thống hoặc nhiều tầng ứng dụng.
- Yêu cầu chưa rõ phương án kỹ thuật, cần khám phá mã nguồn hoặc thử nghiệm trước khi chọn giải pháp.
- Thực hiện qua nhiều mốc, có khả năng bị ngắt hoặc tiếp tục ở phiên Codex khác.
- Có rủi ro làm hỏng dữ liệu, ảnh hưởng hành vi đang chạy hoặc khó khôi phục.
- Là một tính năng lớn, một cuộc tái cấu trúc đáng kể hoặc một đợt chuyển đổi kiến trúc.

Với chỉnh sửa nhỏ, rõ ràng và dễ kiểm chứng, không cần tạo ExecPlan chỉ để tăng thủ tục.

## 3. Nguyên tắc bắt buộc

### 3.1. Tự chứa đầy đủ bối cảnh

ExecPlan phải nêu mục tiêu, hiện trạng, đường dẫn tệp liên quan, thuật ngữ cần hiểu, ràng buộc, hướng triển khai, thao tác và cách kiểm thử. Không viện dẫn chung chung kiểu “như đã trao đổi”, “làm theo kế hoạch trước” hoặc “xem tài liệu ở đâu đó” mà không chỉ ra được thông tin cần thiết.

Khi nhắc tới tệp, ghi đường dẫn **tính từ thư mục gốc repository**. Khi nhắc tới hàm, lớp hoặc mô-đun, sử dụng tên chính xác nếu đã xác minh trong mã nguồn. Không bịa đường dẫn hay lệnh kiểm thử.

### 3.2. Đi từ giá trị người dùng tới hành vi quan sát được

Mở đầu bằng câu trả lời cho ba câu hỏi:

1. Người dùng hiện chưa làm được điều gì?
2. Sau thay đổi, người dùng làm được điều gì?
3. Bằng thao tác nào có thể chứng minh kết quả đó?

Không coi “đã sửa code” hoặc “build thành công” là đủ nếu chưa chứng minh hành vi mong muốn thực sự hoạt động.

### 3.3. Là tài liệu sống

Trong quá trình thực thi, Codex phải cập nhật ExecPlan để phản ánh **thực tế**, không chỉ trạng thái dự kiến. Ít nhất phải duy trì bốn mục:

- `Progress`: việc đã xong, đang làm và chưa làm.
- `Surprises & Discoveries`: phát hiện mới, lỗi bất ngờ hoặc giả định sai.
- `Decision Log`: các quyết định quan trọng cùng lý do.
- `Outcomes & Retrospective`: kết quả đạt được, phần còn lại và bài học.

Sau một phiên làm việc, người đọc chỉ cần mở ExecPlan và repository là biết cách tiếp tục.

### 3.4. Tiến hành chủ động nhưng không mạo hiểm

Khi kế hoạch đủ rõ và môi trường cho phép, Codex chủ động triển khai mốc tiếp theo thay vì dừng ở mỗi mốc để hỏi “tiếp theo làm gì?”. Với bất định có thể xử lý bằng kiểm tra mã nguồn hoặc thử nghiệm nhỏ, hãy tự tìm bằng chứng, quyết định và ghi lý do.

**Ngoại lệ:** Không tự ý thực hiện thao tác xóa dữ liệu thật, thay đổi production, phát sinh chi phí, lộ bí mật hoặc hành động cần quyền chưa được cấp. Ghi rõ điểm chặn, phương án an toàn và yêu cầu phê duyệt khi thực sự cần.

### 3.5. Mọi mốc đều kiểm chứng độc lập

Mỗi milestone phải có kết quả trung gian rõ ràng và ít nhất một cách kiểm chứng: test, lệnh chạy, giao diện có thể quan sát, kết quả API hoặc một thử nghiệm có đầu ra cụ thể. Tránh các mốc mơ hồ như “hoàn thiện backend”.

## 4. Quy trình Codex phải thực hiện

### Bước 1 — Khảo sát

Đọc các quy tắc của dự án, danh sách tệp, mã nguồn liên quan, cách chạy chương trình và bộ kiểm thử hiện có. Ghi nhận những gì **đã xác minh**; đánh dấu giả định chưa kiểm chứng.

### Bước 2 — Lập ExecPlan

Tạo một tệp Markdown riêng, ví dụ `.agent/plans/ten-tinh-nang.md`. Viết đầy đủ các mục trong khuôn mẫu ở phần 6. Nếu công việc có rủi ro cao, nêu trước cách sao lưu, phục hồi và kiểm thử an toàn.

### Bước 3 — Chia milestone

Mỗi mốc theo logic: **mục tiêu → thay đổi → cách chạy → dấu hiệu đạt**. Nếu chưa chắc giải pháp khả thi, thêm mốc làm nguyên mẫu (prototype / proof of concept) và xác định điều kiện giữ hoặc bỏ nguyên mẫu.

### Bước 4 — Thực thi và cập nhật liên tục

Sau mỗi bước có ý nghĩa:

- Đánh dấu trạng thái thực tế trong `Progress`.
- Ghi phát hiện ảnh hưởng tới kế hoạch trong `Surprises & Discoveries`.
- Ghi quyết định đổi phương án trong `Decision Log`.
- Điều chỉnh các mốc chưa thực hiện nếu kiến thức mới làm kế hoạch thay đổi.

Không ghi hoàn thành nếu chưa có bằng chứng. Không ghi kết quả kiểm thử là đạt nếu chưa thực sự chạy.

### Bước 5 — Kiểm chứng và bàn giao

Chạy các bước xác thực phù hợp với dự án: unit test, integration test, build, lint, khởi động hệ thống và thử một luồng sử dụng thật khi có thể. Ghi chính xác lệnh đã chạy, kết quả, lỗi còn tồn tại và giới hạn chưa kiểm tra được. Tổng kết trong `Outcomes & Retrospective`.

## 5. Quy tắc về chất lượng kế hoạch

**Viết cụ thể:** Thay vì “sửa lớp xử lý đơn hàng”, hãy nêu tệp, hàm, đầu vào, đầu ra và trường hợp cần xử lý. Nếu chưa biết chính xác đường dẫn, đặt nhiệm vụ khảo sát để xác định trước khi sửa, không phỏng đoán.

**Giải thích từ chuyên môn:** Những thuật ngữ không quen thuộc phải được định nghĩa đơn giản ngay lần đầu xuất hiện. Nêu chúng liên quan tới thành phần nào của dự án.

**Có khả năng chạy lại:** Các lệnh nên chạy lại được mà không gây nhân đôi dữ liệu hoặc phá trạng thái. Với migration hay thao tác nguy hiểm, phải có sao lưu và cách rollback phù hợp.

**Giữ thay đổi nhỏ và có thể xác minh:** Ưu tiên triển khai tăng dần, kiểm thử từng mốc. Khi thay hệ thống cũ, có thể tạm duy trì đường chạy cũ và mới để kiểm chứng, rồi gỡ đường cũ sau khi đã an toàn.

**Không ép một công nghệ khi chưa có bằng chứng:** Nếu lựa chọn phụ thuộc vào thư viện, hiệu năng hoặc hành vi khó đoán, thực hiện thí nghiệm tối thiểu trước khi cam kết thiết kế lớn.

**Ghi bằng chứng vừa đủ:** Lưu trích đoạn lệnh, kết quả test, log hoặc diff ngắn có giá trị xác nhận. Không đổ toàn bộ log dài vào kế hoạch.

**Tách yêu cầu và thiết kế:** Phân biệt rõ điều người dùng cần đạt được với cách kỹ thuật được chọn để đáp ứng điều đó. Khi chọn phương án, ghi cả các phương án đáng cân nhắc đã loại bỏ.

## 6. Khuôn mẫu ExecPlan cho từng công việc

Khi tạo ExecPlan mới, dùng bố cục dưới đây. Các nội dung trong dấu ngoặc vuông là chỗ cần điền bằng thông tin thực tế. **Không để chỗ trống ở các phần quyết định trực tiếp khả năng triển khai.** Giữ tên mục tiếng Anh trong ngoặc để tương thích với cách gọi thông dụng.

---

# [Tên công việc: ngắn, dùng động từ và nêu rõ kết quả]

**Trạng thái:** Chưa bắt đầu  
**Cập nhật gần nhất:** [YYYY-MM-DD HH:mm, múi giờ]  
**Quy tắc áp dụng:** `.agent/PLANS.md`  
**Phạm vi:** [Các hệ thống / mô-đun có liên quan]

Đây là ExecPlan đang được cập nhật trong quá trình triển khai. Một phiên làm việc mới phải có thể tiếp tục công việc từ tài liệu này và repository hiện tại, không cần lịch sử chat.

## Purpose / Big Picture — Mục tiêu và bức tranh tổng thể

[Giải thích vấn đề từ góc nhìn người sử dụng. Mô tả hành vi trước và sau thay đổi, lợi ích đạt được và cách người dùng tự quan sát kết quả.]

## Progress — Tiến độ

- [ ] [Mốc hoặc nhiệm vụ cụ thể; kèm điều kiện hoàn thành].
- [ ] [Mốc hoặc nhiệm vụ tiếp theo].
- [ ] [Kiểm thử và nghiệm thu cuối].

Cập nhật trạng thái ngay khi có bằng chứng. Nếu một mục chỉ hoàn thành một phần, hãy tách mục đó và ghi rõ phần còn lại.

## Surprises & Discoveries — Phát hiện và bất ngờ

- [Ngày giờ] **Phát hiện:** [Điều gì khác dự kiến?] **Bằng chứng:** [Lệnh, log, tệp hoặc kết quả test]. **Ảnh hưởng:** [Điều chỉnh gì?].

Nếu chưa có phát hiện, ghi “Chưa có”.

## Decision Log — Nhật ký quyết định

- [Ngày giờ] **Quyết định:** [Chọn phương án gì?] **Lý do:** [Bằng chứng và cân nhắc]. **Phương án khác:** [Đã xem xét gì?] **Hệ quả:** [Ảnh hưởng tới mã nguồn, kiểm thử hoặc tiến độ].

Nếu chưa có quyết định đáng kể, ghi “Chưa có”.

## Outcomes & Retrospective — Kết quả và tổng kết

[Trong lúc triển khai, để trạng thái “Chưa hoàn tất” và bổ sung khi đóng từng mốc lớn. Khi kết thúc, đối chiếu kết quả với mục tiêu ban đầu; ghi điều đã đạt, chưa đạt, kiểm thử đã chạy, nợ kỹ thuật và bài học.]

## Context and Orientation — Bối cảnh và định hướng mã nguồn

[Mô tả hiện trạng như đang giải thích cho người chưa biết dự án. Ghi chính xác những đường dẫn liên quan, vai trò của từng mô-đun, cách các thành phần tương tác, những ràng buộc đã xác nhận và thuật ngữ cần biết.]

**Các đường dẫn liên quan:**

- `[duong/dan/tep-1]`: [vai trò].
- `[duong/dan/tep-2]`: [vai trò].

**Giả định / điều kiện môi trường:** [Phiên bản runtime, công cụ, quyền cần có, dữ liệu thử nghiệm, nếu đã được xác minh].

## Plan of Work — Kế hoạch thực hiện

**Milestone 1 — [Tên mốc].** [Mục tiêu, thay đổi trong các tệp/hàm cụ thể, kết quả nhìn thấy được và cách kiểm chứng độc lập.]

**Milestone 2 — [Tên mốc].** [Tiếp nối từ milestone trước, mô tả công việc và bằng chứng hoàn tất.]

**Milestone 3 — [Tên mốc].** [Tích hợp, kiểm thử hoặc chuyển đổi an toàn; có thể thêm/bớt mốc tùy độ phức tạp.]

Nếu có một giả định kỹ thuật rủi ro cao, đặt milestone nguyên mẫu trước công việc lớn và ghi rõ điều kiện **chấp nhận / loại bỏ** kết quả nguyên mẫu.

## Concrete Steps — Các bước và câu lệnh chính xác

**Thư mục làm việc:** `[đường dẫn từ gốc repo]`

**Lệnh khảo sát / chạy / kiểm thử:**

    [Lệnh chính xác đã xác minh trong dự án]

**Kết quả kỳ vọng:**

    [Mẫu đầu ra ngắn hoặc dấu hiệu có thể quan sát]

[Mô tả các thao tác sửa mã nguồn, thứ tự chạy lệnh, điều kiện tiên quyết và cách xác định bước nào đã thành công. Sau khi thực hiện, cập nhật lệnh thực tế nếu khác dự kiến.]

## Validation and Acceptance — Kiểm chứng và nghiệm thu

**Kịch bản nghiệm thu 1:** [Trạng thái ban đầu → thao tác người dùng hoặc yêu cầu API → kết quả nhìn thấy được].

**Kịch bản nghiệm thu 2:** [Trường hợp lỗi, dữ liệu biên hoặc nguy cơ hồi quy → kết quả mong đợi].

**Các lệnh kiểm thử:**

    [Lệnh chạy test/build/lint có thật]

**Bằng chứng:** [Kết quả chạy thực tế, số bài test đạt/trượt, ngày chạy, lý do nếu chưa kiểm chứng được].

Tiêu chí hoàn thành phải phản ánh **hành vi đúng**, không chỉ sự hiện diện của tệp/hàm mới.

## Idempotence and Recovery — Chạy lại và khôi phục

[Nêu bước nào chạy lại an toàn. Nếu thay đổi dữ liệu, schema hoặc cấu hình, mô tả cách sao lưu, phục hồi, kiểm tra dữ liệu và điều kiện cần xin phê duyệt. Nếu thất bại giữa chừng, giải thích cách xác định trạng thái và tiếp tục an toàn.]

## Artifacts and Notes — Bằng chứng và ghi chú

[Lưu các trích đoạn ngắn có ý nghĩa: diff quan trọng, kết quả chạy lệnh, ảnh chụp khi phù hợp, log hoặc liên kết tới tệp sinh ra trong repo. Bỏ thông tin bí mật.]

## Interfaces and Dependencies — Giao diện và phụ thuộc

[Chỉ rõ API, kiểu dữ liệu, contract, hàm, module, phiên bản thư viện hoặc cấu hình được dùng. Nêu tác động ngược tới thành phần cũ; nếu chưa xác minh thì ghi là một việc cần khảo sát.]

---

## 7. Hướng dẫn tích hợp vào dự án Codex

1. Đặt tệp hướng dẫn này tại `.agent/PLANS.md` trong repository.
2. Tạo hoặc cập nhật `AGENTS.md` ở thư mục gốc với đoạn sau:

   ```md
   ## Kế hoạch thực thi (ExecPlan)

   Khi triển khai tính năng phức tạp, thay đổi nhiều thành phần hoặc
   tái cấu trúc đáng kể, hãy đọc toàn bộ `.agent/PLANS.md` và tạo
   một ExecPlan riêng trong `.agent/plans/`.

   Thực hiện từ khảo sát, thiết kế tới kiểm chứng theo ExecPlan.
   Liên tục cập nhật tiến độ, phát hiện, quyết định và kết quả vào
   chính tệp ExecPlan. Không xem việc sửa code là hoàn thành nếu
   chưa kiểm chứng được hành vi mong muốn.
   ```

3. Khi giao việc cho Codex, có thể dùng yêu cầu:

   > Hãy làm [mô tả yêu cầu]. Nếu thuộc loại công việc phức tạp, hãy đọc `.agent/PLANS.md`, tạo một ExecPlan trong `.agent/plans/`, sau đó triển khai và kiểm thử theo từng milestone. Ghi toàn bộ tiến độ và kết quả kiểm chứng vào ExecPlan.

4. Nếu chuyển phiên Codex, dùng yêu cầu:

   > Đọc `AGENTS.md`, `.agent/PLANS.md` và ExecPlan tại `[đường dẫn]`. Đối chiếu kế hoạch với repository hiện tại, xác minh trạng thái thực tế và tiếp tục từ milestone chưa hoàn thành tiếp theo.

**Lưu ý:** Tệp này chỉ là tài liệu chỉ dẫn. Codex không tự động áp dụng nó cho mọi yêu cầu nếu `AGENTS.md` hoặc prompt không yêu cầu đọc. Các tiêu chí và lệnh kiểm thử phải được điều chỉnh theo từng repository; không dùng nguyên các mục ví dụ trong khuôn mẫu làm bằng chứng hoàn thành.
