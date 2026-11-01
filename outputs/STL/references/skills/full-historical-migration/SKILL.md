---
name: full-historical-migration

description: Chuyển dữ liệu giao dịch lịch sử PYSB từ Odoo v14 sang v19 theo từng bước, xác nhận SO/PO đã được nhập theo [skill so-po-migration](../so-po-migration/SKILL.md). Skill này không nhập thêm SO/PO.
---

| Task | Input | Output |
| --- | --- | --- |
| Confirm PO | PO v14 và PO v19 đã khớp | PO đã xác nhận, ngày lịch sử khớp nguồn và liên kết phiếu nhập. |
| Confirm SO | SO v14 và SO v19 đã khớp | SO đã xác nhận, ngày lịch sử khớp nguồn và liên kết phiếu xuất. |
| Confirm DO,MO | Phiếu transfer và MO v14, ánh xạ SO/PO v19 | Chứng từ hoàn tất, ngày lịch sử và liên kết nhập/xuất khớp nguồn; ngoại lệ được ghi rõ. |
| Confirm Invoice,Bill | Invoice/Bill v14 và liên kết giao dịch v19 | Chứng từ đã xác nhận, ngày và liên kết đúng; nguyên tệ, tiền công ty, đối tác, salesperson và quy tắc số được đối chiếu riêng. |
| Verify | Báo cáo v14 và v19, danh sách chênh lệch | Xác định phần đã khớp, phần lệch được duyệt và phần còn cần xử lý; chỉ nghiệm thu khi đủ tiêu chí. |


### Cách dùng Reference

- Bản script chuẩn của skill nằm trong `references/`; không tạo hoặc dùng bản sao ở `test_script/`. Xem [INDEX.md](references/INDEX.md) để tìm script theo nhóm. Helper chuẩn SO/PO dùng trực tiếp từ skill `so-po-migration/scripts/`, không sao chép vào skill này.
- Đọc script để tham khảo rồi tự viết script riêng phù hợp cho task hiện tại

## 1 Confirm PO



- Kiểm tra trạng thái, ngày lịch sử, dữ liệu đầu đơn/từng dòng và thay đổi supplier được phép; ghi nhận ID phiếu nhập được sinh để dùng ở bước tiếp theo.
- Lưu ý định trước lời gọi ghi và kết quả sau đó. Mất phản hồi thì đọc lại trạng thái/chứng từ liên quan trước khi xử lý, không tự gọi confirm lại.
- Kiểm tra số lượng PO confirmed trên v19 với ngày xác nhận khớp nguồn.
- Confirm PO chỉ kiểm tra đơn/dòng và ghi nhận liên kết phiếu nhập.

### Reference

- [confirm_pysb_july_po_staging.py](references/confirm_pysb_july_po_staging.py) — **Đọc/Ghi theo mode**: preflight, sample, batch, verify; cần xác nhận backup khi ghi, baseline thử đạt trước batch và quyền thêm supplier nếu có. Không validate receipt hoặc tạo bill.
- [investigate_pysb_po_supplier_gap.py](references/investigate_pysb_po_supplier_gap.py) — **Đọc, Riêng**: truy nguồn thiếu liên kết supplier của 16 PO từ baseline đợt đã chạy; phân biệt thiếu danh bạ với thiếu liên kết trong sản phẩm.
- [audit_pysb_confirmed_po_staging.py](references/audit_pysb_confirmed_po_staging.py) — **Đọc**: đối chiếu PO sau confirm theo nhật ký, lập bàn giao PO–receipt.



## 2 Confirm SO


- Thử confirm một SO trước khi chạy nhiều.
- Ghi nhận ID phiếu xuất được sinh để dùng ở bước tiếp theo. Lưu ý định trước lời gọi ghi và kết quả sau đó. Mất phản hồi thì đọc trạng thái/chứng từ liên quan trước khi xử lý, không tự gọi confirm lại.
- Kiểm tra số lượng SO confirmed trên v19 với ngày xác nhận khớp nguồn.

### Reference

- [confirm_pysb_july_so_staging.py](references/confirm_pysb_july_so_staging.py) — **Đọc/Ghi theo mode**: preflight, sample, batch; luồng hiện dùng `action_confirm` và khôi phục `date_order` nguồn. Mặc định nhóm 25; có tùy chọn confirm từng đơn để xử lý lỗi singleton tùy chỉnh, vẫn kiểm tra theo nhóm.
- [audit_pysb_confirmed_so_staging.py](references/audit_pysb_confirmed_so_staging.py) — **Đọc**: đối chiếu SO/dòng và liên kết phiếu kho, không đối chiếu toàn bộ kho/kế toán.
- [inspect_pysb_stock_migration.py](references/inspect_pysb_stock_migration.py) và [prepare_pysb_stock_plan.py](references/prepare_pysb_stock_plan.py) — **Đọc/Hồ sơ local**: khảo sát schema, route và luồng kho từ bàn giao SO/PO trước chuyển transfer.



## 3 Confirm DO,MO


Chuẩn bị toàn bộ dữ liệu trước khi validate:


Trước chuẩn bị và sau hoàn tất, chạy `references/scan_pysb_july_other_stock_coverage.py` ở chế độ chỉ đọc. Bộ lọc phải lấy **mọi stock.move done trong kỳ theo company và ngày move**, không giới hạn ngày SO/PO/MO, sản phẩm trong manifest, tên phiếu hoặc inventory_id. Đọc phân trang, kiểm tra tổng số nguồn và ghi trạng thái từng move: đã kiểm chứng, ngoại lệ được duyệt, hoặc chưa giải quyết. Ánh xạ có ID chưa đủ chứng minh đã chuyển; phải đọc lại trạng thái done, lượng, đơn vị, ngày, vị trí, lot/kiện/chủ sở hữu ở đích.


Lưu output mới ở thư mục riêng bằng `--output-dir`; `--evidence-dir` chỉ hồ sơ manifest/journal đầu vào. Không ghi đè hồ sơ lịch sử. Mã thoát scanner: 0 = mọi move đã kiểm chứng; 1 = còn vấn đề hoặc ngoại lệ, không phải lỗi kết nối; lỗi API/phân trang phải báo scan không hoàn tất. Chạy lại sau mỗi lần thay đổi dữ liệu; không dùng báo cáo cũ để nghiệm thu trạng thái mới.

`discover_pysb_supporting_stock.py` và `discover_pysb_closing_gaps.py` dùng cùng bộ lọc đầy đủ; nhận cả sản phẩm chưa ánh xạ, đọc toàn bộ phiếu/MO và quan hệ phụ thuộc. MO, Scrap, Unbuild và move chưa xác định được giữ thành nhóm riêng. Giao dịch ngoài kỳ hoặc chưa done trong chuỗi chỉ là bằng chứng phụ thuộc, không tự được duyệt chuyển. Output mới có `discovery_only=true`: không nạp trực tiếp vào các script ghi cũ; phải review nhóm nghiệp vụ, ánh xạ, phụ thuộc và duyệt change set trước khi chuẩn bị thực thi. Thiếu master phải báo ngoại lệ, không loại dòng khỏi kết quả rà.

- Kiểm tra dữ liệu tồn đầu kỳ khớp theo sản phẩm–vị trí–lot/serial–kiện–chủ sở hữu nếu có.
- Lấy phiếu và chi tiết thực hiện từ v14: chứng từ nguồn, dòng SO/PO, sản phẩm, đơn vị, số lượng thực tế, serial/lot, vị trí nguồn–đích, ngày hoàn tất, trạng thái và liên kết trả hàng/backorder.
- Đối chiếu với phiếu đã sinh khi confirm SO/PO trên v19; sử dụng lại đúng phiếu và stock move, tránh tạo trùng.
- Ánh xạ lot theo công ty + sản phẩm + tên lot/serial; tái sử dụng lot đã có, lập danh sách lot còn thiếu cần tạo.
- Điền đúng serial/lot và lượng thực hiện của v14, thay vì lấy lượng đặt hàng hoặc lot Odoo tự giữ chỗ.
- Truy ngược nguồn cung trước khi validate: receipt PO cũ, điều chỉnh thực, chuyển nội bộ, trả hàng, consignment và tồn đầu kỳ. Không chờ chạy hàng loạt rồi mới tìm nguồn thiếu. Có receipt chạy trước chưa đủ nếu thiếu đúng location/lot/kiện.
- Validate theo ngày lịch sử và quan hệ phụ thuộc thực tế; nghiệm thu bằng bộ báo cáo cuối có thể chạy lại.
Ví dụ: receipt ngày 03/07 → MO ngày 04/07 → delivery ngày 05/07. Cách này giúp lot xuất ra đã có nguồn nhập hoặc nguồn sản xuất đúng thời điểm.
Trong cùng ngày, ưu tiên chứng từ cung cấp hàng trước chứng từ tiêu thụ hàng theo liên kết thực tế. Không áp dụng cứng “receipt → MO → delivery” nếu có trả hàng, chuyển nội bộ hoặc Repack nhiều tầng. Thiếu hàng/lot hoặc ngày nguồn mâu thuẫn thì ghi ngoại lệ, không tự lấy hàng nhập ở ngày sau để bù.


### Ngoại lệ và kinh nghiệm đã ghi nhận

- **Đối ứng tồn tạm cũ:** theo chỉ dẫn Bruce ngày 26/10/2026, kiểm tra lịch sử cộng và các lần đối ứng/hoàn đã có, chứng minh lượng thuần đúng từng sản phẩm–vị trí–lot–kiện–chủ sở hữu và so với nguồn trước khi ghi. Đủ bằng chứng mới đối ứng, lấy mẫu và đọc lại trước khi mở nhóm; không chỉ dựa vào nhãn TEMP để trừ tồn. Giữ nguyên chứng từ done gốc, dùng chứng từ đối ứng có truy vết. Không gỡ đồng loạt; trường hợp âm, đang giữ chỗ hoặc thiếu nguồn/phụ thuộc tiếp tục giữ chờ. Quyền ghi cụ thể vẫn theo phạm vi/phê duyệt của từng đợt, không phải quyền chung sửa mọi khoản tồn tạm.

- **Decimal:** một số Transfer/MO có lượng 0,972 hoặc 3,33333 trên v14; đã đổi thành 0,97 và 3,33 trên v19.
- **Nguồn xuất âm:** khi có bằng chứng v14 xuất âm, làm điều chỉnh tạm v19 trong quyền đã cấp, note đầy đủ để truy vết. Không kết luận mọi thiếu tồn đều là xuất âm; phân biệt với giao dịch nguồn chưa chuyển và sai tồn đầu kỳ.

- **Nguồn bổ sung:** chuyển nội bộ, hàng trả lại, consignment và điều chỉnh tồn thực v14 cần tái hiện trên v19 nếu chưa có. Giữ liên kết trả hàng/backorder, tránh tạo trùng.
- **Dữ liệu nền riêng:** một số sản phẩm được phép đổi sang track by quantity trên v19 staging. 
- **Phiếu chờ:** phân loại thiếu nguồn giao dịch, sai đầu kỳ, sai lot/kiện, lỗi tracking, nguồn thực xuất âm và chờ phiếu trước

### Reference

| Nhóm | Script, thời điểm đọc và chế độ |
|---|---|
| Khảo sát | [inspect_pysb_stock_migration.py](references/inspect_pysb_stock_migration.py), [enrich_pysb_stock_snapshot.py](references/enrich_pysb_stock_snapshot.py), [read_pysb_mo_details.py](references/read_pysb_mo_details.py) — **Đọc**: chụp phiếu, schema, phụ thuộc và chi tiết MO từ bàn giao SO/PO. |
| Lập kế hoạch | [prepare_pysb_stock_plan.py](references/prepare_pysb_stock_plan.py) — **Hồ sơ local**, ánh xạ snapshot và ngoại lệ; [refine_pysb_stock_plan.py](references/refine_pysb_stock_plan.py) — **Đọc/Hồ sơ local**, bổ sung phụ thuộc MO và sinh execution manifest. |
| Chuẩn bị/hoàn tất | [execute_pysb_stock_migration.py](references/execute_pysb_stock_migration.py) — **Ghi với `--prepare`**, dựng phiếu/MO/chi tiết; [complete_pysb_stock_migration.py](references/complete_pysb_stock_migration.py) — **Ghi với `--complete`**, chạy theo thời gian; `--retry-pending`/`--event-keys-file` chọn chạy tiếp; `--audit` đọc Odoo, xuất đối chiếu. Đọc manifest/nhật ký trước khi dùng. |
| Sự cố MO đầu lượt | [repair_pysb_mo_finished_preparation.py](references/repair_pysb_mo_finished_preparation.py) — **Ghi, Riêng MO 70/71/72**: khôi phục ba MO hủy và hiệu chỉnh thành phẩm, giữ nguyên tiêu hao. Script chuẩn bị gốc vẫn có đoạn `picked=True`; đọc đối chiếu script sửa này trước tái sử dụng, không coi luồng chuẩn bị gốc đã sửa triệt để. |
| MO chạy tiếp | [resume_pysb_untracked_material_mos.py](references/resume_pysb_untracked_material_mos.py) và [repair_pysb_resumed_mo_finished.py](references/repair_pysb_resumed_mo_finished.py) — **Ghi, Riêng HQ/MO/24170 và HQ/MO/24338**: chuẩn bị lại sau đổi tracking/khôi phục thành phẩm, tránh tiêu hao nguyên liệu lần hai. |
| PO cũ nhập muộn | [discover_pysb_old_po_receipts.py](references/discover_pysb_old_po_receipts.py) — **Đọc**, cần hồ sơ bằng chứng của đợt; [import_pysb_all_old_po_receipts.py](references/import_pysb_all_old_po_receipts.py) — **Ghi**, dựng receipt lẻ; [finish_pysb_old_po_receipts.py](references/finish_pysb_old_po_receipts.py) — **Ghi**, validate/read-back receipt và các bước liên quan. |
| Giao dịch bổ sung | [discover_pysb_supporting_stock.py](references/discover_pysb_supporting_stock.py) — **Đọc**, tìm luồng nguồn bỏ sót; [prepare_pysb_supporting_transfers.py](references/prepare_pysb_supporting_transfers.py) và [finish_pysb_supporting_transfers.py](references/finish_pysb_supporting_transfers.py) — **Ghi**, chuẩn bị/hoàn tất transfer được duyệt; luồng finish dùng lại code finish PO cũ. |
| Điều chỉnh thực | [apply_pysb_missing_source_adjustments.py](references/apply_pysb_missing_source_adjustments.py) — **Ghi, theo bằng chứng đợt**, chuyển delta tồn thực từ nguồn, dùng sản phẩm/lot đã có. |
| Tồn đầu kỳ | [fix_pysb_opening_packages.py](references/fix_pysb_opening_packages.py) và [repair_pysb_pending_opening_lots.py](references/repair_pysb_pending_opening_lots.py) — **Ghi, Riêng nhóm được duyệt**: sửa kiện/ngày đầu kỳ hoặc lượng/lot đầu kỳ theo bằng chứng; không chạy như điều chỉnh chung. |
| Nguồn âm/tồn tạm | [classify_pysb_source_negative_stock.py](references/classify_pysb_source_negative_stock.py) — **Đọc**, chứng minh tồn trước tiêu hao; [apply_pysb_temporary_negative_stock.py](references/apply_pysb_temporary_negative_stock.py) — **Ghi, theo quyền đã cấp**, cấp tồn tạm có nhật ký. |
| Cặp tạm và UV WHITE | [bridge_pysb_closed_return_chain.py](references/bridge_pysb_closed_return_chain.py) — **Ghi, Riêng**, cấp +1 rồi trừ −1 cho chuỗi xuất–trả NLW-902 lot 20250627; [temporary_pysb_uv_white_supply.py](references/temporary_pysb_uv_white_supply.py) — **Ghi, Riêng**, cấp tạm 4 UV WHITE thay nguồn PO-04604 chưa chuyển, còn cần đối ứng về sau. |
| Sản phẩm/tracking | [create_pysb_6115_28mm_and_quantity_ptc.py](references/create_pysb_6115_28mm_and_quantity_ptc.py) — **Ghi, Riêng**: tạo đúng SKU 28 mm, đổi PTC013WS sang quantity và đưa lại điều chỉnh đã loại. |
| Chi tiết ngoại lệ | [PYSB_DO_MO_Exception_Records_EN.xlsx](references/PYSB_DO_MO_Exception_Records_EN.xlsx) |



## 4 Confirm Invoice,Bill



### Element

- Chụp nguồn và danh bạ đích trước chuyển. Ghép chứng từ theo công ty + ID nguồn/External ID; số chứng từ và tên hiển thị chỉ hỗ trợ tìm, không thay định danh.
- Chạy `prepare_pysb_historical_invoices.py` trước create/post để tạo manifest có `historical_checks` phiên bản 1 và `invoice-contact-preflight.json`. Báo riêng khác `parent_id`, `company_name`, đối tác thương mại và trạng thái archive; không tự đổi tên, nối mẹ hoặc unarchive contact. Định danh chưa chứng minh hoặc contact sai công ty chặn chứng từ; khác biệt cấu trúc/tên được báo để xử lý riêng, không suy tên giống là cùng record.
- Trước khi tạo, chốt chính sách số hóa đơn v19 và ánh xạ salesperson lịch sử cho Invoice. Không để mặc định partner/SO thay thế salesperson nguồn mà không báo khác biệt; thiếu ánh xạ thì ghi ngoại lệ. Trường salesperson trống trên Bill là hành vi chuẩn v19, không tự coi là lỗi mất nhân viên kinh doanh của Invoice.
- Đối chiếu riêng tổng nguyên tệ, loại tiền, tổng quy đổi có dấu theo tiền công ty và tỷ giá tại ngày chứng từ. `amount_total` khớp chưa chứng minh `amount_total_signed` khớp. CNH → CNY phải ghi rõ là ánh xạ đã chọn, vẫn phải kiểm tra tỷ giá; không sửa tỷ giá toàn cục chỉ để làm khớp một chứng từ.
- Prepare truyền `invoice_currency_rate` native, cùng giá trị nghịch đảo `x_foreign_to_company_rate` nếu schema hỗ trợ; XML-RPC không tự chạy onchange. Chọn tỷ giá tái tạo được balance các dòng nguồn theo rounding, không chỉ chia hai tổng; tổng 0 vẫn kiểm tra dòng. Chứng từ mọi dòng bằng 0 cần bằng chứng tỷ giá nguồn/bảng ngày, không chia cho 0. Bút toán phụ ngoài dòng hóa đơn có balance 0 và nguyên tệ triệt tiêu nhau được tách khỏi suy tỷ giá, giữ ID trong bằng chứng manifest. Không tái tạo được số tiền nguồn bằng một tỷ giá thì chặn để review.
- Invoice phải truyền `invoice_user_id` tường minh (nguồn trống thì giữ trống), ghép theo login duy nhất, user đích active và được phép công ty. Riêng đợt PYSB này dùng WAREHOUSE → Siti qua login `BILLING1`, không hardcode user ID; Bill không áp yêu cầu salesperson Invoice. Create, audit draft và post đều đọc lại tổng nguyên tệ/MYR, tỷ giá, salesperson và balance/amount_currency dòng hóa đơn. Manifest cũ thiếu bộ kiểm tra phải inspect/prepare lại trước khi ghi.
- Giữ danh bạ v19 đã làm sạch: báo riêng khác tên hiển thị, khác hoa/thường và sai partner ID. Không khôi phục tên v14 khi chưa chứng minh ánh xạ sai. Đọc lại các tiêu chí sau tạo và sau post; báo rõ trường chưa kiểm tra hoặc cần quyết định nghiệp vụ.
- Với chứng từ đã posted, công cụ audit chỉ đọc; không tự reset draft, sửa số hoặc post lại. Luồng ghi đã bổ sung FX, salesperson và báo cáo contact; script vẫn phụ thuộc phạm vi/output đợt 13–14/10, còn chính sách sequence chưa chốt. Không coi sửa hai phần này là đã tổng quát hóa toàn bộ migration hoặc đủ điều kiện chạy lại batch lịch sử.

### Reference

- [INDEX.md](references/INDEX.md) — danh mục script tạo nháp/post/bổ sung và các xử lý riêng. Không chạy toàn bộ danh sách.
- [historical_invoice_checks.py](references/historical_invoice_checks.py) — logic dùng chung cho tỷ giá, salesperson, báo cáo contact và kiểm tra read-back; không kết nối hoặc ghi Odoo khi import. Được gọi từ prepare/create/audit draft/post, không chạy riêng như một migration.
- [tests/test_historical_invoice_checks.py](references/tests/test_historical_invoice_checks.py) — kiểm thử offline hai phần sửa; có hồi quy từ snapshot 18 Bill và danh sách 17 Invoice nếu hồ sơ sự cố được cài tại dự án.
- [audit_pysb_sue_invoice_feedback.py](references/audit_pysb_sue_invoice_feedback.py) — **Chỉ đọc**, offline mặc định từ snapshot; `--live` chụp nguồn v14 prod và đúng v19 staging đã khóa danh tính; `--details` đọc bổ sung; `--sue-workbook` đọc file Bill của Sue mà không sửa Excel. Dùng `--help` trước chạy. Hiện phạm vi lịch sử được dựng từ hai journal đợt 13–14/10/2026; mã thoát 1 là có khác biệt, 2 là chưa đủ dữ liệu/lỗi, không coi là nghiệm thu đạt. Kết quả so khớp v14 không thay cho xác nhận hóa đơn gốc.
- [tests/test_audit_pysb_sue_invoice_feedback.py](references/tests/test_audit_pysb_sue_invoice_feedback.py) — kiểm thử offline cho các trường bị bỏ sót và phân biệt khác tên với sai đối tác.


## 5 Verify

### Input

- Danh sách nguồn đầy đủ, ánh xạ/nhật ký chuyển, báo cáo chứng từ và tồn đầu–cuối cùng mốc giữa v14/v19; danh sách ngoại lệ đã duyệt và điều chỉnh tạm còn treo.

### Element

- Number of SO and PO confirmed in both version is the same 
- SO and PO has the same order qty, delivered qty, invoiced qty
- Number of Transfer and MO is the same
- DO and MO has the same demand qty and done qty
- Total stock qty on and at the end of July is the same
- Number of Inv and Bill posted is the same 
- Invoice and Bill has the same discount, price, qty, total amount
- Kiểm tra độc lập tiền công ty có dấu, loại tiền/tỷ giá và nguyên tệ; Invoice có salesperson đúng ánh xạ, đối tác đúng định danh và số chứng từ đúng chính sách v19. Khác tên do danh bạ đã làm sạch được báo riêng, không gộp thành sai ánh xạ.

### Reference

- [complete_pysb_stock_migration.py](references/complete_pysb_stock_migration.py) với `--audit` — **Đọc Odoo/Hồ sơ local**: chứng từ, chi tiết move, MO, ngày, ngoại lệ và tồn theo nhật ký; phân biệt báo cáo này với đối chiếu toàn bộ nguồn–đích.
- [report_pysb_product_balances.py](references/report_pysb_product_balances.py) — **Đọc**: tồn sản phẩm theo ngày chuẩn Odoo trên các sản phẩm đã ánh xạ, không valuation; không tự bao phủ mọi sản phẩm công ty.
- [report_pysb_lot_balances.py](references/report_pysb_lot_balances.py) — **Đọc**: tồn đầu/cuối theo sản phẩm và lot; dùng cùng phạm vi/mốc với báo cáo sản phẩm, không thay cho kiểm tra chi tiết vị trí/kiện.
- [verify_pysb_prod_mos.py](references/verify_pysb_prod_mos.py) với `--evidence-dir <thư mục hồ sơ>` — **Đọc production**: đối chiếu trạng thái/ngày, lượng kế hoạch/thực sản xuất, demand/done nguyên liệu và thành phẩm/phụ phẩm; yêu cầu chi tiết move được kiểm chứng. Thiếu MO/move/ánh xạ vẫn xuất dòng lỗi, không bỏ qua; mã thoát 1 là chưa đạt. Không có chỉ tiêu delivered/invoiced cho MO. Dùng manifest mới, không dùng ánh xạ baseline trước ghi để nghiệm thu lượt ghi mới.
- [report_pysb_temporary_stock_result.py](references/report_pysb_temporary_stock_result.py) — **Đọc/Hồ sơ local**: báo cáo khoản tạm và kết quả xử lý theo nhật ký đợt, không coi là bằng chứng mọi khoản đã đối ứng.

