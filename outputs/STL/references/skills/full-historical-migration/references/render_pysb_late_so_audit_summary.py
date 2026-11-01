"""Bản kết luận dễ đọc từ kết quả kiểm tra DB đã lưu, không kết nối ERP."""
import json
from pathlib import Path
from html import escape
P=Path('outputs/pysb-stock-migration-20261012/late-so-supply-audit-20261014')
r=json.loads((P/'late-so-supply-report.json').read_text(encoding='utf8'))
assert r['summary']['delivery_move_checks']=={'verified':71}
assert len(r['cases'])==1 and r['cases'][0]['so']==['SO-53765']
assert r['cases'][0]['status']=='verified' and r['cases'][0]['net_later_receipt_dependency']
assert all(x['classification']=='source_negative' for x in r['late_temporary_review'])
text='''# Pao Yeang — kiểm tra SO tháng 7 và nguồn nhập tháng sau

Đã đọc trực tiếp v14 prod và v19 staging ngày 14/10/2026, công ty ID 1. Không thay đổi dữ liệu Odoo.

## Kết luận

Trong danh sách 953 SO tháng 7 đã chuyển, có 38 phiếu PICK/PACK/DO hoàn tất từ tháng 8 trở đi, gồm 71 stock move. Cả 71 move trên v19 đã hoàn tất và khớp nguồn về ngày, lượng, sản phẩm, đơn vị, lot, vị trí và kiện. Phiếu chưa hoàn tất trên nguồn không thuộc kết luận này.

Tìm được **1 SO có hàng nhập tháng sau trước khi giao**, và **2 SO đã dùng khoản tạm vì nguồn v14 xuất âm theo lot**. Đây là ba tình huống khác nhau, không được gom thành thiếu receipt.

| Trường hợp | Bằng chứng v14 | Cách xử lý v19 | Đánh giá |
|---|---|---|---|
| SO-53765 — LANYARD 25MM × 100M | PO-04439 ngày 14/07; nhập 500 UNIT ngày 05/08, vào Stock lúc 09:47 Malaysia; DO HQ/DO/54489 xuất 100 UNIT lúc 16:15 cùng ngày | Receipt HQ/IN/00039, phiếu vào kho HQ/INT/00044 và DO HQ/OUT/00789 đều done, đúng lượng và ngày | Đúng: nhập trước, xuất sau; không dùng tồn tạm thay receipt này |
| SO-53894 — PTP013B, lot 27082025 | HQ/PICK/56595 ngày 01/08: đúng lot/vị trí chỉ có 12 ROLL, cần xuất 19, nguồn âm 7 | Đã cấp tạm +6 rồi +1, tổng +7 ROLL; PICK v19 HQ/PICK/00912 done, đúng dòng nguồn | Đúng theo quyền xử lý nguồn âm đã duyệt. Khoản tạm vẫn phải theo dõi riêng; không kết luận tồn thực khớp nguồn |
| SO-53682 — JETCOL TA, lot 0988785 | HQ/PICK/56404 ngày 04/08: đúng lot/vị trí có 1 ROLL, cần 2, nguồn âm 1 | Cấp tạm +1 ROLL; PICK v19 HQ/PICK/00728 done, đúng dòng nguồn | Đúng theo quyền xử lý nguồn âm đã duyệt. Khoản tạm vẫn còn trong sổ theo dõi |
| UV WHITE — PO-04604 | Nhập 60 UNIT ngày 24/09; điều chỉnh tồn ngày 10/10 có ba move −4, +2, +1 | Đã cấp tạm +4 rồi tái hiện ba move điều chỉnh; khoản tạm có reference riêng | Đây là điều chỉnh tồn tháng 10, không phải chứng cứ về SO tháng 7 xuất tháng 10. Đúng theo quyết định cấp tạm; khi chuyển nguồn nhập thật phải xử lý đối ứng khoản +4 |

## Phạm vi và cách hiểu

- Phiếu đã hoàn tất trong nhóm SO đã chuyển có ngày tháng 8–9; không thấy phiếu done tháng 10 trong nhóm này tại lần đọc DB.
- Đã xem 18.517 dòng lịch sử nguồn của 20 sản phẩm trên các phiếu tháng sau. Chỉ 1 dòng giao khách có nguồn nhập cùng sản phẩm/lot từ tháng 8 trở đi trước khi giao: SO-53765. Điều này không chứng minh phân bổ duy nhất receipt cho SO; nó cho thấy chuỗi cung ứng có nguồn nhập thật đã được chuyển đúng.
- Với LANYARD, tồn ở các vị trí nội bộ trước giao là 310 UNIT. Nếu loại 500 UNIT nhập tháng 8 thì số dư tính lại là −190; vì vậy không thể tái hiện chuỗi xuất mà bỏ lần nhập đó. Phiếu vào Stock đã được kiểm tra riêng.
- Hai trường hợp tồn tạm tháng 8 được kiểm chứng bằng đúng sản phẩm/lot/vị trí/kiện trên v14 trước khi xuất: 12 → xuất 19 và 1 → xuất 2. Không phải chỉ thiếu do staging chưa chuyển receipt trước thời điểm xuất.
- Có 13 move nhập tháng sau chưa ánh xạ trong truy vấn rộng cho 20 sản phẩm. Chúng không phải receipt cùng lot cấp trước các DO giao khách đã chọn; không mặc định cần nhập toàn bộ các move này. Việc kiểm tra này không phải rà toàn bộ DO tháng 7 hoặc mọi giao dịch tháng 8–10 của công ty.
- Chưa đối chiếu toàn bộ tồn cuối tháng 8/9/10. Kết luận “đúng” là đúng chứng từ nguồn và đúng phương án ngoại lệ Bruce đã duyệt; không có nghĩa tồn thực mọi kỳ đã khớp sau các khoản tạm.
- Các ngày ở bảng trên dùng Malaysia UTC+8; dữ liệu JSON và báo cáo kỹ thuật ghi UTC. Cùng timestamp được sắp theo ID dòng; không suy đoán thứ tự thực tế trong cùng giây.

## Hồ sơ

- [Chi tiết truy nguồn và đối chiếu DB](PYSB_Late_SO_Supply_Review.html)
- [Kết quả có cấu trúc](late-so-supply-report.json)
- [Dữ liệu nguồn vừa đọc](live-source-snapshot.json)
- [Dữ liệu staging vừa đọc](live-target-snapshot.json)
'''
(P/'PYSB_Late_SO_Supply_Conclusion.md').write_text(text,encoding='utf8')
# Render the short report without adding a dependency.
lines=text.splitlines();parts=[];table=False
for line in lines:
    if line.startswith('|'):
        cells=[c.strip() for c in line.strip('|').split('|')]
        if all(set(c)<=set('-: ') for c in cells):continue
        if not table:parts.append('<table>');table=True;tag='th'
        else:tag='td'
        parts.append('<tr>'+''.join(f'<{tag}>{escape(c)}</{tag}>' for c in cells)+'</tr>');continue
    if table:parts.append('</table>');table=False
    if line.startswith('# '):parts.append('<h1>'+escape(line[2:])+'</h1>')
    elif line.startswith('## '):parts.append('<h2>'+escape(line[3:])+'</h2>')
    elif line:parts.append('<p>'+escape(line.removeprefix('- '))+'</p>')
html='''<!doctype html><html lang="vi"><meta charset="utf-8"><title>Kiểm tra nguồn nhập cho SO tháng 7</title><style>body{font:16px/1.6 Arial;color:#183047;max-width:1250px;margin:30px auto;padding:20px}h1{font-size:27px}h2{font-size:21px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd9e2;padding:12px;vertical-align:top}th{background:#e7f2f6;text-align:left}a{color:#12648b}@media print{body{margin:0;font-size:12px}}</style>'''+''.join(parts)+ '<p><a href="PYSB_Late_SO_Supply_Review.html">Mở chi tiết DB</a> · <a href="late-so-supply-report.json">Mở dữ liệu JSON</a></p></html>'
(P/'PYSB_Late_SO_Supply_Conclusion.html').write_text(html,encoding='utf8')
print('Đã xuất báo cáo kết luận; 71/71 move khớp, 1 SO có receipt tháng sau, 2 SO nguồn âm đã cấp tạm.')
