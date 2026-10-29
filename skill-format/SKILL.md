---
name: skill-format
description: Chuẩn hóa cấu trúc và định dạng skill FC+TC khi được yêu cầu; cho phép nén ý nhưng giữ nguyên ý nghĩa và yêu cầu gốc.
---

# Skill Format

## Purpose

Sắp xếp và định dạng skill theo một cấu trúc chính phù hợp, giúp nội dung ngắn gọn, dễ đọc và tra cứu. Bản thân skill này dùng Reference/Guidelines.

## Input

- File hoặc nội dung skill người dùng chỉ định.
- Yêu cầu riêng về cấu trúc, mức nén ý và cách bàn giao, nếu có.

## Structure Guidelines

Chọn một dạng chính theo quan hệ giữa các phần nội dung. Ưu tiên dạng người dùng chỉ định; nếu chưa chỉ định, tự chọn và giải thích ngắn lý do. Có thể lồng nhóm phụ khi cần.

| Dạng | Khi phù hợp | Bố cục gợi ý |
| --- | --- | --- |
| Workflow-Based | Các bước có trình tự hoặc phụ thuộc đầu vào, đầu ra | Tổng quan luồng → các bước theo thứ tự |
| Task-Based | Các tác vụ độc lập, có thể thực hiện riêng | Danh sách tác vụ → hướng dẫn từng tác vụ |
| Reference/Guidelines | Quy chuẩn, quy tắc hoặc hướng dẫn tra cứu | Các nhóm hướng dẫn theo chủ đề |
| Capabilities-Based | Các nhóm năng lực hoặc chế độ hỗ trợ, không có trình tự cố định | Tổng quan năng lực → hướng dẫn từng nhóm năng lực |

Đây là bố cục gợi ý, không phải danh sách mục bắt buộc. Giữ bảng Task | Input | Output của FC+TC khi bảng giúp nhìn rõ luồng hoặc chọn tác vụ mà không lặp nội dung dài.

## Formatting Guidelines

### Frontmatter

- Có `name` và `description`; giữ metadata và chính sách gọi skill hiện có nếu có.
- `description` nêu chức năng và tình huống sử dụng; không tạo mục When to Use riêng.
- Không đổi tên skill, thư mục hoặc chính sách kích hoạt chỉ để định dạng.

### Sections

Dùng tiêu đề mục bằng tiếng Anh, nội dung hướng dẫn bằng tiếng Việt. Giữ nguyên mã, định danh, tên giao diện và trích dẫn khi dịch có thể đổi nghĩa.

Chỉ dùng các mục bổ sung dưới đây khi có ý tương ứng trong nội dung gốc; không tạo mục rỗng hoặc tự thêm yêu cầu để đủ khung.

| Mục | Nội dung | Cách đặt |
| --- | --- | --- |
| Purpose | Mục đích của skill | Ngắn gọn, tránh lặp description |
| Input | Đầu vào cần có | Ở cấp skill, bước hoặc tác vụ tùy nơi áp dụng |
| Output | Kết quả cần tạo, định dạng và nơi lưu nếu đã quy định | Ở cấp phù hợp, tránh lặp; dùng Output thay cho Output Requirements |
| Rules | Điều phải làm, không được làm và giới hạn | Gom quy tắc chung; giữ điều kiện riêng cạnh nội dung áp dụng |

Không mặc định thêm Tool Usage Rules, Failure Strategy, Quality Checklist hoặc Examples. Giữ các quy tắc và hướng dẫn gốc trong nhóm phù hợp hoặc Rules; chuyển nội dung ví dụ theo Resource Guidelines và giữ liên kết cạnh phần cần minh họa.

### Markdown

- Dùng một tiêu đề cấp 1 cho tên skill, phân cấp tiêu đề liên tục theo quan hệ nội dung.
- Dùng danh sách đánh số khi thứ tự có ý nghĩa; bullet cho ý độc lập; bảng cho thông tin cần đối chiếu.
- Tách đoạn và bảng bằng dòng trống; dùng code span cho đường dẫn, định danh và lệnh ngắn; đóng đủ code fence.
- Giữ liên kết cạnh nội dung liên quan hoặc ở nhóm nguồn cuối file. Kiểm tra lại đường dẫn tương đối khi chuyển vị trí nội dung.

## Resource Guidelines

Khi chuẩn hóa skill, đánh giá nội dung theo ba nhóm dưới đây. Chỉ tách tài nguyên khi có nội dung phù hợp; không tạo thư mục rỗng hoặc ép nội dung thành script hay asset.

### References

- Chuyển nội dung ví dụ minh họa sang `references/`; trong `SKILL.md` giữ liên kết tương đối và chỉ dẫn khi nào cần đọc.
- Nếu ví dụ đã ở file riêng, tái sử dụng và liên kết tới file hiện có, không sao chép trùng. Giữ các quy tắc bắt buộc ngoài ví dụ trong phần hướng dẫn chính.
- Khi di chuyển ví dụ, giữ nội dung và kiểm tra lại liên kết, đường dẫn tài nguyên liên quan.

### Scripts

- Kiểm tra thao tác lặp, logic xác định hoặc đoạn mã thực thi nào phù hợp để tách thành script trong `scripts/`.
- Chỉ tách khi giúp tái sử dụng hoặc thực hiện đáng tin cậy hơn; giữ nguyên hành vi, đầu vào, đầu ra và điều kiện áp dụng. Trong `SKILL.md`, nêu khi nào dùng và cách gọi script.
- Kiểm chứng script sau khi tách bằng tình huống đại diện trong môi trường được phép. Việc đánh giá hoặc tách script không tự cho phép chạy nghiệp vụ hay thay đổi dữ liệu; nếu chưa thể kiểm chứng an toàn, báo rõ giới hạn.

### Assets

- Kiểm tra mẫu, hình ảnh hoặc tài nguyên được sao chép hay sử dụng trong đầu ra để đặt vào `assets/` khi phù hợp.
- Mẫu dùng tạo đầu ra là asset; ví dụ chỉ dùng để đọc tham khảo thuộc `references/`. Không biến ví dụ nghiệp vụ cụ thể thành mẫu mặc định.
- Giữ liên kết và chỉ dẫn cách sử dụng asset trong phần liên quan; kiểm tra file còn mở hoặc sử dụng được sau khi di chuyển.

## Rules

- Chỉ sửa trong phạm vi người dùng chỉ định; không tự áp dụng hàng loạt lên FC+TC.
- Cho phép đổi vị trí, chia hoặc gộp mục, gộp ý trùng và rút ngắn câu. Giữ đủ điều kiện, ngoại lệ, mức bắt buộc, thứ tự có ý nghĩa, đầu vào, đầu ra và liên kết tham khảo.
- Không biến ví dụ thành quy tắc chung; không tự thêm yêu cầu nghiệp vụ, công cụ, đầu ra hoặc quyền thực hiện.
- Khi nội dung mâu thuẫn hoặc mơ hồ, giữ ý và hỏi nếu việc sắp xếp hoặc nén có thể đổi nghĩa; không tự bỏ một ý để giải quyết.
- Các nguồn trong `references/sources.md` chỉ dùng tham khảo cấu trúc, không nhập quy tắc nghiệp vụ hoặc yêu cầu tạo file của nguồn vào skill đích.
- Trước khi bàn giao, đối chiếu trước/sau để bảo đảm không mất hoặc thêm ý; kiểm tra frontmatter, Markdown và liên kết trong phạm vi chỉnh sửa.

## Output

- Chỉnh trực tiếp khi người dùng yêu cầu sửa file. Khi được yêu cầu đề xuất hoặc chưa rõ cách bàn giao, tạo bản đề xuất và giữ nguyên file gốc.
- Báo ngắn gọn dạng cấu trúc đã chọn, phần đã sắp xếp hoặc nén, kết quả kiểm tra và nội dung còn cần làm rõ nếu có.
- Báo kết quả đánh giá references, scripts và assets: đã tách hoặc tái sử dụng gì, hoặc vì sao chưa cần tách.

## Sources

Chỉ đọc [sources.md](references/sources.md) khi cần tham khảo thêm cách tổ chức skill; các ví dụ không phải mẫu bắt buộc.
