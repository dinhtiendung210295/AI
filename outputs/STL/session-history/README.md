# Lịch sử session migration PYSB T7–T10/2026

**Trạng thái: bản để rà soát, CHƯA ĐƯỢC PHÉP CÔNG BỐ PUBLIC.** Các file trong [sessions/](sessions/) chứa lời trao đổi hiển thị với Codex và dấu thời gian gọi công cụ. Công cụ xuất đã che một số dạng thông tin đăng nhập, nhưng bản hội thoại vẫn có thể chứa dữ liệu nghiệp vụ production, tên đối tác hoặc nội dung nhạy cảm trong văn bản tự do. Không commit/push thư mục này vào GitHub public trước khi rà soát từng file và chốt phạm vi công bố.

## Cách đọc

Đọc [manifest.json](manifest.json) để tìm mã session và chủ đề. `exported` nghĩa là tìm được nội dung hội thoại; `metadata_only` nghĩa là file log tương ứng không có lượt trao đổi để xuất.

| Chặng | Session nên đọc |
| --- | --- |
| Tháng 7 và rà soát ban đầu | [Migration tháng 7](sessions/07-staging-01a12ef6-780c-7721-ac81-856586854d36.md) |
| Master data | [Contact](sessions/21-master-01a15d6d-88f7-7502-841c-4a3d332aad70.md), [product](sessions/21-master-01a15d76-3c77-7a00-8ceb-41011f63f549.md) |
| SO/PO | [SO](sessions/23-orders-01a1695d-f0a0-7c11-9117-1e793ca11804.md), [PO](sessions/23-orders-01a16b3e-7d6a-70f2-92a9-1a8c75d4af5b.md), [PO confirm](sessions/25-confirm-01a1733d-e280-7ac2-ad10-174de032ba69.md), [SO confirm](sessions/25-confirm-01a17366-5771-71a1-b3c1-2dec51dd4e09.md) |
| Kho và sản xuất | [PO move](sessions/26-stock-01a17770-d37c-75b0-b61f-bf4c93b53c11.md), [MO/unbuild](sessions/27-manufacturing-01a17d70-a4ef-76a1-b004-6086a729545a.md), [SO delivered](sessions/28-delivery-01a181f9-b11e-74e0-9e74-25c0eb94696d.md), [Other move](sessions/28-other-move-01a181fb-67d1-75b0-b80f-3dbd17be24e5.md) |
| Hóa đơn và đối chiếu | [Bill](sessions/28-accounting-01a17ff4-3a2f-7ab2-8eba-7a7ad1bfe157.md), [kế hoạch final verify](sessions/30-verify-01a18a93-c0e0-78c3-8108-9907589424de.md), [thực hiện đối chiếu](sessions/30-verify-01a18aba-a430-7311-8506-d6b6b05ab9c6.md) |



