# Final verify migration PYSB tháng 7–10/2026

Ngày lập: 30/10/2026. Trạng thái: **đã lập kế hoạch, chưa chạy final verify**.

## 1. Mục tiêu và phạm vi

Nguồn **v14 production `paoyeang_live`**; đích **v19 production `py19-main-33843450`**; công ty 1. Tham khảo [mục 5 Verify của skill full-historical-migration](skills/full-historical-migration/SKILL.md#5-verify), áp dụng các điều chỉnh đã chốt dưới đây; không sửa skill dùng chung.

- Đối chiếu số lượng SO, PO, MO/unbuild, Invoice/Bill tháng 7–10/2026 và tồn cuối toàn kỳ.
- Theo chỉ đạo Bruce ngày 30/10/2026, so và báo cáo mỗi nhóm trên **một tập chung từ đầu tháng 7 đến hết cutoff 25/10**, không chia kết quả theo tháng. Vẫn lưu ngày gốc và các baseline của từng phiên để truy vết, phát hiện phát sinh và tránh đếm trùng; chứng từ trong kỳ không bị loại chỉ vì nằm ngoài baseline tháng 9–10.
- SO/PO chọn theo ngày đơn; MO/unbuild theo ngày hoàn tất; Invoice/Bill theo ngày hóa đơn và baseline của phiên chuyển tương ứng. Giữ tập ID nguồn đã chốt; nếu baseline dùng tiêu chí khác thì ghi rõ trước khi so, không âm thầm đổi tập nguồn.
- Kỳ tháng 7–10 theo giờ Malaysia: `2026-06-30 16:00:00 UTC <= ngày < 2026-10-25 16:00:00 UTC`. Mốc tồn duy nhất là **hết 25/10/2026 giờ Malaysia**; không thêm kiểm tra tồn đầu kỳ hoặc cuối từng tháng.
- Không verify Transfer/Other move. Không kiểm tra giá, chiết khấu, tỷ giá, salesperson hoặc định giá tồn trong đợt này. **Điều chỉnh theo chỉ đạo Bruce:** nghiệm thu Invoice/Bill theo tổng tiền gồm thuế trong toàn kỳ, phân biệt loại tiền chứng từ; chưa cần khớp từng dòng hoặc hạch toán. Không mặc định các loại tiền khác nhau tương đương. Chỉ đạo này không mở rộng thành kiểm tra toàn bộ kế toán hoặc tỷ giá.
- Không đối chiếu riêng tám cột [EXECPLAN.md](EXECPLAN.md); kết quả giao dịch dưới đây là căn cứ cập nhật tiến độ. Không suy kết quả kho hoặc giao dịch từ tổng số chứng từ đơn thuần.

## 2. Hồ sơ đầu vào và tái sử dụng ánh xạ

Đọc các điểm bắt đầu sau, rồi lần theo liên kết tới baseline, mapping, capture, quyết định, journal và kết quả phục hồi của từng phiên. Đây là hồ sơ tham chiếu, không phải hàng đợi để chạy lại writer.

| Hồ sơ | Nội dung cần kế thừa |
| --- | --- |
| [ExecPlan](EXECPLAN.md) và [lịch sử ExecPlan](EXECPLAN_HISTORY_20261028.md) | Phạm vi, các quyết định chung, ngoại lệ đã xử lý/chưa xử lý và bằng chứng các pha. |
| [Plan SO delivered](SO_DELIVERED_T7_T10_PLAN.md), [checkpoint SO](../../../outputs/so-delivered-20261028/CHECKPOINT.md) | Định danh SO/dòng/move, sản phẩm dịch vụ, UOM, lot, tracking và journal phục hồi mới nhất. |
| [Plan MO/unbuild](MO_DONE_T7_T10_PLAN.md), [checkpoint MO](../../../outputs/mo-done-20261028/CHECKPOINT.md) | MO/unbuild, nguyên liệu/thành phẩm, mapping được bổ sung sau baseline và quyết định thay thế đã duyệt. |
| [Index PO/kho](../../../outputs/po-move-migration-20261027/INDEX.md) | Mapping PO/dòng PO, bằng chứng nguồn–đích, quyết định UOM/lot/vị trí và phụ thuộc khác kỳ. |
| [Plan Bill tháng 9–10](BILL_T9_T10_PLAN.md), [checkpoint Bill](../../../outputs/bill-sep-oct-20261028/CHECKPOINT.md) | Baseline, source scope, binding chứng từ/dòng và các khác biệt số lượng đã được duyệt. |
| [Hồ sơ production tháng 8–10](pysb-aug-oct-2026-prod/INDEX.md) và các liên kết Invoice/Bill trong ExecPlan | Capture và mapping lịch sử cho các phần còn lại; phân biệt đúng hồ sơ production với staging. |

### Quy tắc hợp nhất

- Tái sử dụng quy tắc và lịch sử ánh xạ từ các phiên ExecPlan: chứng từ, dòng, sản phẩm, UOM, kho/vị trí, lot/serial và ngoại lệ tracking. Không bắt đầu lại bằng ghép tên khi đã có định danh được xác minh.
- Mỗi ánh xạ lưu loại đối tượng, ID nguồn/đích, hồ sơ bằng chứng, quyết định áp dụng và trạng thái xác minh. Nếu nhiều nguồn chứng cứ xung đột, giữ các ứng viên và báo chưa đủ bằng chứng; không tự chọn bản mới nhất chỉ theo ngày file.
- External ID, mapping và journal phải có nguồn gốc rõ ràng. Tên, số chứng từ và `origin` chỉ hỗ trợ tra cứu. Không dùng ID số giống nhau làm bằng chứng hai phiên bản tương ứng.
- Tái sử dụng mapping đã chứng minh nhưng đọc lại dữ liệu đích mới cho final verify. Baseline/mapping trước ghi không thay bằng chứng trạng thái sau lượt ghi cuối.
- UOM dùng hệ số và độ chính xác hợp lệ đã xác minh; ngoại lệ thay sản phẩm, đổi tracking hoặc bỏ lot chỉ áp dụng đúng trường hợp được duyệt. Thiếu mapping không được làm giảm mẫu số hoặc loại sản phẩm khỏi so tồn.
- **Điều chỉnh theo xác nhận Bruce ngày 30/10/2026:** khi một sản phẩm có nhiều ánh xạ sản phẩm nguồn–đích, coi tất cả sản phẩm được nối qua các ánh xạ đó là tương đương cho phép so tồn; cộng lượng tồn của mỗi sản phẩm trong nhóm một lần, sau quy đổi UOM hợp lệ. Vẫn xuất ID từng sản phẩm và đối chiếu theo vị trí/lot; không tự gộp vị trí hoặc lot. Sản phẩm hoàn toàn chưa có ánh xạ vẫn báo riêng.

## 3. Chốt dữ liệu và đối chiếu giao dịch

### Điều kiện bắt đầu lượt nghiệm thu

- Xác minh mọi writer liên quan đã kết thúc bằng trạng thái tiến trình, phase và journal hiện hành; mất PID/session không đủ chứng minh writer đã dừng. Các RPC chưa rõ phải được xác minh trước khi chụp dữ liệu nghiệm thu.
- Dùng XML-RPC chỉ đọc, kiểm tra URL/database/công ty thực tế trước khi đọc nghiệp vụ. Không gọi script/action ghi, không thay cấu hình Odoo, không lấy khóa ghi để thực hiện verify.
- Chụp mới hai phía; lưu thời gian bắt đầu/kết thúc, domain, danh sách ID, số bản ghi và bằng chứng phân trang đầy đủ. Nếu có thay đổi liên quan trong cửa sổ chụp, đánh dấu dữ liệu chưa ổn định và chụp lại phần bị ảnh hưởng trước kết luận.
- Giữ baseline nguồn và tập ID theo từng nhóm. Phát sinh thêm trong kỳ được ghi riêng cùng ảnh hưởng tới kết luận phạm vi; không âm thầm đổi mẫu số, bỏ sót hoặc nhập vào baseline cũ.

### Tiêu chí theo nhóm

| Nhóm | Phép đối chiếu |
| --- | --- |
| SO/PO | Số đơn confirmed và trạng thái tương ứng; sản phẩm và lượng đặt, giao/nhận, invoiced trên từng dòng sau quy đổi hợp lệ. Gồm dịch vụ, nhận/giao từng phần và trả hàng. Theo chỉ đạo Bruce, so thêm tổng tiền đơn gồm thuế theo từng loại tiền. Đơn chỉ đạt khi mọi dòng thuộc phạm vi đạt hoặc có khác biệt đã được duyệt rõ ràng. |
| MO/unbuild | Số chứng từ hoàn tất và đích done tương ứng; lượng kế hoạch/thực tế, demand/done nguyên liệu và thành phẩm. Unbuild kiểm tra lượng tháo dỡ/thu hồi và liên kết MO gốc khi có. **MO trong phạm vi không có phụ phẩm: không đưa phụ phẩm thành hạng mục kiểm tra.** |
| Invoice/Bill | Theo quyết định mới của Bruce, so tổng tiền gồm thuế của các chứng từ posted theo từng loại tiền trong toàn kỳ; chưa yêu cầu khớp từng dòng hay hạch toán. Giữ riêng trường hợp khác loại tiền và chứng từ hoàn tiền; không tự cộng các loại tiền khác nhau. |

Một đích dùng cho nhiều nguồn hoặc nhiều đích cho một nguồn phải có bằng chứng tách/gộp và bảo toàn lượng; không đếm trùng. Chứng từ thiếu, dư, sai trạng thái, sai lượng hoặc chưa rõ định danh đều phải xuất dòng kết quả. Đọc move phục vụ MO, trả hàng hoặc truy nguyên lượng không tạo một đợt verify Transfer/Other move.

Bruce xác nhận ngày 30/10/2026: việc tách/gộp phiếu nhận vẫn bảo đảm `qty_received` trên PO đúng. Ghi nhận đây là xác nhận nghiệp vụ; final verify đọc và so `qty_received` trên dòng PO theo tiêu chí trên, không suy từ số phiếu nhận.

Điều chỉnh theo Bruce: khi so lượng đã giao/nhận và đã lập Invoice/Bill, phải phân biệt phát sinh trước và sau cutoff; một chứng từ nguồn phát sinh sau cutoff không được coi là thiếu trong phạm vi cutoff chỉ vì lượng hiện tại của đơn đã tăng. Dựng lượng theo move done và Invoice/Bill posted liên kết, xử lý trả hàng/hoàn tiền, ngày, đơn vị tính và bằng chứng liên kết; báo riêng trường hợp chưa đủ dữ liệu. Việc so tại cutoff không đồng nghĩa tự xác thực hoặc ghi sổ phiếu trên production.

**Điều chỉnh ngày 01/11 theo Bruce:** mục tiêu xử lý bổ sung là để các số `delivered`, `received`, `invoiced`/`billed` hiện tại trên v19 bằng v14, bao gồm các chứng từ phát sinh sau cutoff. Vẫn lưu riêng số tại cutoff để nghiệm thu lịch sử; phần ngoài cutoff được kiểm tra trùng và triển khai theo chứng từ nguồn, không chỉnh trực tiếp số tổng.

## 4. Tồn cuối kỳ: đo chênh lệch trước, giải thích sau

### Bước A — Xác định đầy đủ chênh lệch

- Lấy toàn bộ sản phẩm có tồn hoặc phát sinh ảnh hưởng tồn trong công ty ở hai phía, gồm sản phẩm archived, tồn âm và sản phẩm chưa có mapping. Không giới hạn theo manifest, nhật ký migration hoặc danh sách sản phẩm đã ánh xạ.
- Tính tồn thực lịch sử tại cùng cutoff, bao gồm mọi dòng done ảnh hưởng tồn trước mốc. Không so quant hiện tại nếu có phát sinh sau cutoff. Nếu dựng từ quant và đảo phát sinh sau cutoff thì phải chứng minh phạm vi sổ đầy đủ và hai lần đọc quant ổn định.
- So tổng từng sản phẩm toàn công ty trước; sau đó so theo kho/vị trí và lot/serial, gồm vị trí nội bộ và consignment thuộc phạm vi tồn của công ty. Báo riêng vị trí/quyền sở hữu chưa đủ bằng chứng tương ứng; không tự gộp vào kho chính để làm khớp.
- Không yêu cầu nghiệm thu riêng theo kiện/chủ sở hữu; khi tổng hợp không được làm mất hoặc tính trùng lượng do các chiều này. Áp dụng ngoại lệ tracking đã duyệt khi đối chiếu lot, giữ giá trị gốc trong bằng chứng.
- Bảng lệch gồm định danh hai phía, sản phẩm, UOM quy đổi, kho/vị trí, lot, lượng v14/v19, chênh lệch và tình trạng mapping. Dòng chưa ghép được vẫn hiện trong kết quả.
- **Tồn tạm, đối ứng và inventory adjustment vẫn nằm trong tồn thực. Bước A chưa phân tích nguyên nhân, chưa quy chênh lệch cho các khoản này và không loại tác động của chúng khỏi phép tính.**

### Bước B — Truy nguyên và đề xuất xử lý

Chỉ bắt đầu sau khi có bảng lệch đầy đủ. Truy từng nhóm chênh lệch qua nguồn–đích, lịch sử mapping và phát sinh liên quan; xem xét cả thiếu/thừa giao dịch, đầu kỳ, UOM, lot/vị trí, ngày lịch sử, tracking, tồn tạm, đối ứng, inventory adjustment và các nguyên nhân khác có bằng chứng.

Liệt kê lượng đóng góp của từng nguyên nhân, chứng từ/journal liên quan và phần còn chưa giải thích; không tính trùng khoản tạm với khoản đã đối ứng. Việc đọc Transfer/Other move để truy nguyên không mở lại phạm vi nghiệm thu nhóm này. Đề xuất sửa lập riêng, nêu tác động dự kiến và cách kiểm chứng; final verify không sửa production.

## 5. Kết quả, kiểm chứng và điều kiện nghiệm thu

Khi bắt đầu chạy, tạo hồ sơ mới `outputs/final-verify-<timestamp>/`, không ghi đè evidence lịch sử. Tối thiểu có:

- `INDEX.md` và `CHECKPOINT.md`: danh tính môi trường, trạng thái từng bước, giới hạn, điểm tiếp tục và liên kết bằng chứng.
- `scope.json`, `mapping-register.json`, thư mục snapshot hai phía: baseline/ngoài baseline, mapping kèm nguồn gốc, tiêu chí đọc và mức đầy đủ/ổn định của dữ liệu.
- Kết quả SO/PO, MO/unbuild, Invoice/Bill; bảng tồn tổng và chi tiết, bảng lệch; hồ sơ nguyên nhân/phương án bổ sung sau Bước A.
- Báo cáo tiếng Việt UTF-8 và `summary.json`: tách **đạt**, **khác biệt giao dịch đã duyệt**, **chưa đạt**, **chưa đủ bằng chứng**. Chưa chạy hoặc đọc lỗi không được hiện là đạt.

### Kiểm chứng công cụ trước khi chạy đầy đủ

Kiểm tra trên evidence lịch sử hoặc fixture các trường hợp: mapping cũ có quyết định thay thế, mapping xung đột, chứng từ/dòng thiếu hoặc trùng, trả hàng và dịch vụ, UOM khác hệ số/rounding, ngoại lệ tracking/lot, MO/unbuild không có phụ phẩm, phát sinh sau cutoff và đọc thiếu trang. Kiểm tra tồn có sản phẩm chưa mapping, tồn âm, lệch bị triệt tiêu ở tổng nhưng khác lot/vị trí, khoản tạm đã có đối ứng và quant thay đổi trong lúc chụp. Đọc lỗi phải làm kết quả chưa hoàn tất, không trở thành số 0.

### Điều kiện kết luận

- Giao dịch chỉ được chấp nhận khi mọi phần trong phạm vi đạt hoặc có khác biệt đã duyệt, dẫn đúng quyết định và giới hạn. Thiếu bằng chứng hoặc phát sinh mới chưa xử lý phải được thể hiện trong kết luận.
- **Tồn thực phải khớp sau quy đổi UOM và làm tròn hợp lệ ở cả tổng sản phẩm và kho/vị trí/lot. Mọi chênh lệch còn lại chặn nghiệm thu tồn, kể cả đã giải thích được hoặc liên quan khoản tạm được duyệt.** Không đặt một ngưỡng bỏ qua tùy ý.
- Sau mỗi lần sửa dữ liệu, đọc lại nhóm giao dịch bị ảnh hưởng và toàn bộ tồn cuối kỳ; kết quả trước sửa chỉ còn là lịch sử.
- Bruce xác nhận ngày 30/10/2026: Invoice v19 khác ngày v14 cần được sửa theo v14. Chuẩn bị và xác minh từng cặp, phương án an toàn cho chứng từ posted và tác động liên quan trong hồ sơ sửa riêng; final verify vẫn là bước chỉ đọc và chạy lại sau sửa.
- Cập nhật ExecPlan từ kết quả giao dịch có thời điểm và bằng chứng, giữ baseline/lịch sử quyết định và sửa đổi của phiên khác. Không tạo bước kiểm tra riêng tám cột, không đổi số Other move bằng kết quả của đợt này.
- Kết luận cuối chỉ bao phủ các nhóm đã chọn; không gọi đây là nghiệm thu Transfer/Other move, dữ liệu tiền hoặc toàn bộ chức năng kế toán.

### Tiến độ ban đầu

- [x] Chốt phạm vi, tiêu chí và lập plan riêng.
- [ ] Hợp nhất hồ sơ và quy tắc ánh xạ có nguồn gốc.
- [ ] Xác minh điều kiện kết thúc writer/RPC và chụp mới dữ liệu.
- [ ] Đối chiếu giao dịch và hoàn tất Bước A tồn cuối kỳ.
- [ ] Hoàn tất Bước B nguyên nhân/phương án cho các chênh lệch.
- [ ] Công bố kết quả và cập nhật ExecPlan theo bằng chứng.
