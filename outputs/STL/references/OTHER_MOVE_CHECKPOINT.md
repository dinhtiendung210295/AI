# Checkpoint Other move — chuẩn bị, chưa ghi production

**C?p nh?t scrap 29/10:** Theo ch? ??o Bruce, chuy?n sang scrap d? 38 move chuy?n kho ti?p t?c gi? ch?. ?? ch?y c?c ??t 718?730: 47 move c? ?ng vi?n ??ch v? 9 phi?u scrap m?i, t?ng 56 move trong queue. Kh?ng ti?n ki?m ho?c audit. S? n?y ch? l? k?t qu? queue, ch?a kh?ng ??nh ho?n th?nh to?n b? 118 move scrap; c?n x? l? ph?n ngo?i queue v? c?c ngo?i l? c?n gi?. Chi ti?t theo `active-completed-718.json` ??n `active-completed-730.json`.


**C?p nh?t m?i nh?t 29/10:** Bruce ch?n gi? ch? 38 move thu?c c?c phi?u c? ghi nh?n thi?u t?n ho?c thi?u lot trong snapshot c?. Theo y?u c?u, ?? ghi li?n k?t tr? h?ng c?a move ??ch 17478 v? move g?c 17477 t??ng ?ng ngu?n 505141 ? 505140; RPC tr? th?nh c?ng, kh?ng audit. [K?t qu?](independent-return-505141-result.json). Li?n k?t ?? ???c ghi; ch?a k?t lu?n ri?ng vi?c g?n ??nh danh ngu?n???ch cho move n?y. Ch?a chuy?n sang scrap v? nh?m chuy?n kho c?n 38 move gi? ch?.


**C?p nh?t m?i nh?t 29/10:** Bruce ch?p thu?n ti?p t?c nh?m chuy?n kho ??c l?p theo t?ng ??t. ??t 709 v? 710 g?n ??nh danh cho 4 move ?? c?; ??t 713 t?o phi?u ??ch 10670 cho 18 move; ??t 717 t?o phi?u ??ch 10671 cho 1 move. T?ng nh?m ?? x? l? 56/95, c?n 39: 38 move thu?c c?c phi?u c? ghi nh?n thi?u t?n ho?c thi?u lot trong snapshot c?, 1 move 505141 c?n ho?n thi?n li?n k?t tr? h?ng t? ?ng vi?n ?? ghi nh?n. C?c s? thi?u t?n l? snapshot, c? th? ?? thay ??i. Ch?a ch?y scrap, ch?a audit theo ch? ??o. [K?t qu? ??t 713](batch-713-20261029T041453432409Z/state.json), [??t 717](batch-717-20261029T041619104201Z/state.json). T?m kh?a ch?nh s?ch ch?y queue trong khi x? l? ph?n c?n l?i; kh?ng d?ng kh?a chung v?i SO delivered.


**Điểm dừng mới nhất 29/10:** nhóm SO/PO ngoài kỳ đã xử lý **499/499 định danh**, không audit; hai liên kết ngày ngược đã ghi theo quyết định Bruce. [Kết quả hai liên kết](outside-two-links-result.json). Nhóm chuyển kho độc lập đã có 33/95 move được xử lý từ trước; còn 62 move trong [danh sách review](independent-transfer-remaining-review.json). Scrap chưa chạy. Không xem 499/499 định danh là audit hoặc nghiệm thu toàn bộ lịch sử.

Sau khi hoàn tất nhóm SO/PO, lệnh `run_active_queue.py --execute` để chạy toàn bộ hai nhóm tiếp theo bị **xét duyệt tự động từ chối** vì lệnh không giới hạn đợt và bao gồm chuyển kho lẫn scrap trên production. Không chạy vòng qua quyết định này. Cần xét duyệt lại phạm vi hẹp theo từng nhóm/đợt và giữ các trường hợp còn cần quyết định; journal Other move không có RPC chưa rõ tại điểm dừng.

**Nhóm SO/PO ngoài kỳ — cập nhật 29/10:** toàn bộ **499/499 source move có định danh** theo journal kết quả và mapping snapshot; trong đó các move đã có được gắn External ID, các move thiếu đã chuyển bằng phiếu native. Không tạo SO/PO trước tháng 7. Không audit theo chỉ đạo; 499/499 là độ phủ định danh, không phải xác nhận tương đương toàn bộ chứng từ. [Độ phủ](outside-order-binding-status-20261029.json), [journal](other-move-journal.jsonl).

Bruce chọn Operation Type Consignment 135 hiện có trên v19 và duyệt tạo bảy lot đúng nguồn; các quyết định đã áp dụng, không sửa hạn lot. Wizard hết hạn của phiếu 10566 đã được tiếp tục trên chính phiếu, không tạo lại: [kết quả](recover-consignment-790-20261029T005353222708Z/result.json). Đã bổ sung 8 liên kết trả hàng theo nguồn từ hồ sơ; [kết quả RPC](outside-return-links-result.json). Còn hai liên kết move trước/sau trong nguồn có ngày chặng trước muộn hơn chặng sau; giữ để giải thích, không tự sửa: [chi tiết](outside-chain-held.json). Do đó **chưa kết luận nhóm SO/PO ngoài kỳ hoàn tất hoàn toàn**; không chuyển tiếp các nhóm sau khi còn hai liên kết này.

**Quyết định Consignment:** Bruce chọn dùng Operation Type Consignment hiện có trên v19 (`stock.picking.type` 135), dù Type of Operation là Receipt (`incoming`), cho các move consignment ngoài kỳ; giữ vị trí đi–đến theo nguồn. Không đổi cấu hình operation type. Áp dụng cho nhóm Consignment cùng bản chất; thiếu lot hoặc phụ thuộc chưa xử lý tiếp tục được ghi nhận riêng.

**Chỉ đạo bổ sung của Bruce:** hạn dùng lot không quan trọng trong session này; không giữ move chỉ vì hạn dùng khác và không sửa hạn lot để xử lý move. SO/PO trước tháng 7 không tồn tại trên v19; không yêu cầu tạo đơn cũ hay nối vào đơn không tồn tại, lưu tham chiếu nguồn. Mã lot, sản phẩm và lượng vẫn được giữ theo phạm vi xử lý. Chỉ đạo này thay các yêu cầu lịch sử về đối chiếu/sửa hạn lot và liên kết SO/PO cũ.

**Đính chính thứ tự nhóm:** Bruce chỉ rõ SO/PO ngoài kỳ có 499 move, không phải chỉ 91 move trong queue. Writer đã chuyển sang nhóm chuyển kho độc lập khi mới xử lý 91/499; đây là hiểu sai thứ tự yêu cầu. Đã tắt quyền chạy queue trước đợt tiếp theo, xác minh tiến trình runner đã dừng và journal Other move không có thao tác chưa rõ. Tại điểm dừng, nhóm SO/PO ngoài kỳ có **91 move đã xử lý/đã có, còn 408**; nhóm chuyển kho độc lập đã xử lý **33 move**, **22 move trong các đợt đã thử giữ chờ**, và còn một move trong queue chưa xử lý. Chưa chạy scrap. Không audit theo chỉ đạo Bruce. Không tự đảo/xóa các chứng từ đã ghi.

**Thứ tự mới để tiếp tục:** xử lý trọn 408 move còn lại của nhóm SO/PO ngoài kỳ, rồi mới tiếp tục chuyển kho độc lập; hoàn tất chuyển kho trước scrap. Không tự bật lại queue cũ: [execution-policy.json](execution-policy.json) đang chặn. Phân loại từ hồ sơ cũ, không phải kết luận live: 245 move chưa xác định được đích, 163 có ứng viên nhưng còn vướng quan hệ dòng SO/PO, move trước/sau hoặc return; chi tiết [outside-order-exceptions.json](outside-order-exceptions.json). Không giả định 408 move chưa tồn tại trên đích.

**Dừng ngày 29/10 — xét duyệt tự động:** queue mới gồm 203 move; đợt 701 xác định một binding đã có và đợt 702 đã ghi 20 External ID, không audit. Tổng 21 move đã xử lý/đã có; không ghi nhận tạo 21 stock.move. [Kết quả đợt 702](batch-702-20261029T002929905100Z/state.json), [journal](other-move-journal.jsonl). Kiểm tra journal Other move sau đợt không có RPC chưa rõ.

Lệnh chạy **toàn bộ queue còn lại** đã bị xét duyệt tự động từ chối: ghi production không giới hạn đợt, không tiền kiểm/audit và không khóa chung có phạm vi ảnh hưởng lớn hơn nhiều so với các đợt trước; chỉ đạo chạy song song chưa được hệ thống coi là đủ phê duyệt rõ cho toàn queue. Còn 28 đợt/182 move trong queue: 70 SO/PO ngoài kỳ, 56 chuyển kho độc lập, 56 scrap. Ngoài queue còn các trường hợp giữ chờ; không coi 182 move là toàn bộ phần còn lại của mốc 712. Không chạy vòng qua quyết định từ chối; cần xử lý yêu cầu xét duyệt trước khi tiếp tục phần bị chặn.

**Diễn biến mới nhất 29/10:** Bruce chỉ đạo chạy đồng thời với SO delivered, không đợi khóa giữa hai phiên, không tiền kiểm, không audit và không cần đối chiếu trùng giữa hai phạm vi. Đợt 701 gọi tạo External ID cho source `500292` nhưng Odoo trả lỗi khóa duy nhất; lệnh tạo bị từ chối. Đọc lại đúng trường hợp RPC lỗi cho thấy External ID đã tồn tại và trỏ đúng đích `17738`; không gọi lại thao tác tạo. [Bằng chứng](recover-701-20261029T002854112724Z/resolution.json). Journal op-1 đã được đóng theo kết quả đọc lại, không còn kết quả mơ hồ cho thao tác này. Đây là binding đã có, không phải một move mới được tạo.

**Chỉ đạo mới nhất:** Other move và SO delivered được ghi song song, **không đợi khóa của nhau**; Bruce xác nhận phạm vi khác nhau, không cần thêm đối chiếu trùng giữa hai session. Không audit mẫu/từng đợt/cuối mốc; giữ tiền kiểm và xử lý RPC chưa rõ. Plan có ba nhóm 499 SO/PO ngoài kỳ → 95 chuyển kho độc lập → 118 scrap, không chia theo tháng. Chỉ đạo này thay các yêu cầu “chờ khóa”, “luân phiên khóa chung” và audit lịch sử ở phần dưới.

**Bổ sung cách chia đợt:** trong mỗi nhóm nghiệp vụ chạy xuyên suốt toàn kỳ, theo ngày nguồn và phụ thuộc; không chia nhóm nhỏ theo tháng. Một đợt có thể chứa chứng từ nhiều tháng. Audit từng đợt và toàn nhóm; tháng dùng để báo cáo/nghiệm thu kết quả sau audit toàn tập.

**Chỉ đạo mới nhất 29/10/2026:** SO/PO ngoài kỳ → chuyển kho độc lập → scrap; **không migrate inventory adjustment**. Phạm vi hiện hành là **712 move**, loại 235 adjustment từ tập 947 cũ. Snapshot audit 28/10 sau khi lọc đạt 90/321, 68/190, 6/135, 3/66; tổng 167/712. [ID nguồn hiện hành](active-source-scope-20261029.json).

**Queue 72 đợt bên dưới là hồ sơ lịch sử, ngưng hiệu lực để rebuild theo phạm vi/thứ tự mới.** Writer đã được chặn bằng [execution-policy.json](execution-policy.json); không dùng kết quả tiền kiểm cũ để bật ghi. Lọc cả binding/sửa lot của adjustment, không chỉ đợt `create_adjustment`. Nếu việc loại adjustment làm thiếu nguồn cung cho move còn lại thì giữ chờ, không tự cấp tồn hoặc migrate adjustment trở lại. Session tiếp tục chờ khóa; thay đổi kế hoạch này không ghi ERP.

Các mốc 947/72 đợt ở các phần dưới mô tả trạng thái **trước quyết định 29/10**, phục vụ truy lịch sử.

Ngày 28/10/2026, múi giờ Bangkok. Nguồn `paoyeang_live` → đích `py19-main-33843450`, công ty 1. Chỉ đạo hiện hành: hoàn tất chuẩn bị để tiếp tục sau bàn giao khóa; phiên này chưa thực thi `--execute`.

## Trạng thái mới nhất

Đã chốt đúng định nghĩa nguồn **947 move**, theo tháng 7/8/9/10 là **436/231/183/97**. Baseline cũ 448 được giữ để truy lịch sử. Truy kín đồ thị phần đơn hàng ngoài kỳ 730 move, không còn liên kết chưa đọc, không trùng nguồn baseline, SO/PO trong kỳ hoặc MO. [Tập nguồn đúng](corrected-source-scope.json), [bằng chứng](outside-order-readiness.json).

Đã đóng gói **254 move trong 72 đợt**, gồm 52 đợt baseline và 20 đợt chỉ gắn mapping cho move ngoài kỳ đã tồn tại. **Tiền kiểm live chỉ đọc đạt 72/72**: [baseline](package-preflight.json), [ngoài kỳ](outside-package-preflight.json). Các thay đổi lot từ đợt trước chỉ được mô phỏng ở tiền kiểm tổng; phải đọc lại thật sau nhận khóa. Chưa chạy mẫu ghi thật trên production.

Audit từng phần hiện đạt **353/947**, theo tháng **195/436, 97/231, 39/183, 22/97**. Audit hợp nhất mới tại [latest-corrected-audit.json](latest-corrected-audit.json) là kết quả nên đọc trước khi tiếp tục. 451 move vẫn giữ chờ: 43 ở baseline, 408 ở phần ngoài kỳ. Vì vậy **chưa thể nói toàn mốc chỉ còn chờ khóa**. Phần đủ điều kiện đã có manifest; phần giữ chờ có hồ sơ và lý do riêng.

Phân hoạch công việc: 242 không cần ghi + 254 trong queue + 451 giữ chờ = 947. 111 move trong queue đã đối chiếu đạt và chỉ bổ sung External ID, nên không cộng số audit vào số queue.

## Baseline 448 đã đóng gói

- Tập nguồn gốc tái lập đúng 156/131/104/57. Capture `capture-20261028T121136137404Z/`; nguồn không đổi ở audit cuối.
- Audit mới: **134/156 tháng 7, 76/131 tháng 8, 33/104 tháng 9, 19/57 tháng 10**, tổng 262/448. [Bằng chứng](scope-audit-20261028T123832779138Z/summary.json). Chưa nghiệm thu toàn mốc.
- Phân hoạch công việc: 242 move không cần ghi, 163 move trong **52 đợt** và 43 move giữ chờ. Trong 163 có 20 move đã đạt nhờ mapping local, queue chỉ bổ sung External ID cho chúng; không cộng tổng audit với queue.
- 5 luồng tiền kiểm mẫu đã đạt, 0 ghi ERP: [kết quả](queue-last-result.json). Kiểm thử local 11/11 đạt: [offline-validation.json](offline-validation.json). Chưa chạy mẫu ghi thật; chưa thể coi writer đã được chứng minh trên production.
- Ngoại lệ 43 move: 42 move thuộc 9 nhóm thiếu tồn/giữ hàng; một move `505141` có đích `17478` nhưng thiếu liên kết return gốc `17477`. [Review](EXCEPTIONS_REVIEW.md), [lượng thiếu](supply-blockers.json). Không tạo lại move đã có.
- Có changeset ngày/hạn cho 52 lot theo quy tắc đã duyệt trong EXECPLAN. Không sửa lot khi còn trong giai đoạn chuẩn bị. Đợt ghi chỉ áp dụng đúng phụ thuộc của manifest.

## Lịch sử phát hiện phạm vi bị bộ đếm cũ bỏ sót

Định nghĩa hiện hành của EXECPLAN bao gồm move liên quan SO/PO ngoài kỳ. Kiểm tra chỉ đọc phát hiện 349 move có liên kết trực tiếp; lan truyền trong đồ thị move theo kỳ thành **499 move**, tháng 7/8/9/10 là **280/100/79/40**. Không trùng 448 nguồn gốc. [Worklist](outside-order-worklist.json), [component](outside-order-components.json), [tổng hợp](outside-order-summary.json).

Tại bước đầu, 164 move còn liên kết ra ngoài đồ thị theo kỳ. **Đã giải quyết bước này** bằng capture riêng `outside-capture-20261028T125216839787Z/`: truy đủ 730 move, không còn liên kết chưa đọc. Mẫu số 947 đã được xác minh theo định nghĩa mốc và cập nhật có giải thích trong EXECPLAN; queue baseline được giữ nguyên.

## Các bước chuẩn bị đã thực hiện

1. Tiền kiểm chỉ đọc toàn bộ 52 đợt baseline và 20 đợt ngoài kỳ đã đạt; giữ đủ proof từng đợt.
2. Capture/truy kín phần đơn hàng ngoài kỳ; xác minh live 141 sản phẩm, đối chiếu native dòng SO/PO, lưu changeset cho 91 move và ngoại lệ cho 408 move. Chưa tạo mới move kho cho phần này.
3. Công cụ nhận riêng hai queue, dùng chung khóa/journal, có mẫu đầu mỗi phạm vi/luồng. Audit hợp nhất kiểm tra đủ 947 nguồn và trùng đích giữa hai phần. Toolchain được seal; các kiểm thử và kết quả tại [offline-validation.json](offline-validation.json).

## Bàn giao và chạy

Đọc [INDEX.md](INDEX.md). Dùng đúng khóa kho chung; không tự nhả khóa writer khác. `status.py` chỉ thăm dò và nhả ngay khóa nếu lấy được; không giữ chỗ. Kiểm tra journal/phase khi thực sự nhận khóa. Thăm dò trước từng thấy khóa rảnh và 204 journal sạch, nhưng đó là bằng chứng tại thời điểm đọc, không thay kiểm tra mới.

Queue đã chuẩn bị có thể chạy qua `run_queue.py --execute` sau khi gate của phạm vi đủ điều kiện được xác minh. Khóa rảnh không thay thế tiền kiểm cuối, chạy mẫu và audit từng đợt. Không có background waiter hoặc tự retry. Không mở rộng ghi sang phần đơn hàng ngoài kỳ chưa có manifest riêng.

Không rebuild queue đã bắt đầu ghi; không chạy file `batches/` ngoài danh mục `batch-index.json`. Khi lỗi, giữ state/journal và đọc lại ERP trước bất kỳ lần gửi RPC tiếp theo.
