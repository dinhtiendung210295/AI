# ExecPlan: migration PYSB tháng 7–10/2026

Lấy mãu từ https://learn.chatgpt.com/cookbook/articles/codex_exec_plans?utm_source=chatgpt.com là một template Plan cho phiên làm việc dài nhiều tiếng, nhiều ngày

## Phạm vi và trạng thái

Nguồn v14 production `paoyeang_live`; đích v19 production `py19-main-33843450`; công ty 1. Phạm vi inventory tháng 8–10, hết ngày 25/10/2026 Malaysia (`2026-10-25 16:00 UTC`); [hồ sơ hiện hành](../../../outputs/po-move-migration-20261027/INDEX.md).

Định danh move nguồn–đích bằng External ID có quy ước nguồn rõ ràng, mapping bền vững hoặc journal; tên, ID số và `origin` chỉ là dấu hỗ trợ. Hồ sơ cũ đã mất; tái lập bằng capture/audit còn lại và đọc live. Mọi thao tác ghi dùng khóa chung, journal từng RPC, đọc lại kết quả mơ hồ trước khi tiếp tục; không ghi lặp.

## Tiến độ

| Month | PO confirm | SO confirm | Bill posted | Invoice posted |
|---|---:|---:|---:|---:|
| 7 | 86/85 | 953/954 | 170/170 | 967/967 |
| 8 | 77/77 | 888/888 | 159/159 | 892/892 |
| 9 | 48/48 | 951/951  | 159/159 | 959/959 |
| 10 | 70/70 | 764/764  | 114/114 | 770/770 |


| Month | PO received | MO done | SO delivered | Other move |
|---|---:|---:|---:|---:|
| 7 | 85/85 | 518/518 | 943/954* | 320/321* |
| 8 | 77/77 | 415/415 | 799/888* | 189/190* |
| 9 | 48/48 | 558/558 | 821/951* | 110/135* |
| 10 | 70/70 | 367/367 | 596/764* | 50/66* |



**Cách đo**

- PO received: chọn PO confirmed theo date_order; so qty_received hiện tại trên từng dòng. Một PO đạt khi tất cả dòng tương ứng bằng nhau theo số hiển thị. gồm cả trả nhà cung cấp
- SO delivered: chọn SO confirmed theo date_order; so qty_delivered hiện tại trên từng dòng, cùng cách tính PO. gồm cả khách hàng trả hàng
  - Dấu * ở cột SO delivered: số là kết quả đọc sơ bộ ngày 30/10, chưa phải audit nghiệm thu toàn tháng. Phép đo dùng mapping sản phẩm snapshot cũ và đối chiếu UOM thận trọng; vì vậy không coi các SO còn chênh là chắc chắn chưa giao. [Bằng chứng](../../../outputs/so-delivered-20261028/baseline-20261030T024344828607Z/summary.json).
- MO done: chọn MO nguồn done theo ngày hoàn tất; đối chiếu lượng nguyên liệu và thành phẩm của từng MO với đích done. Kiểm tra cả phụ phẩm; không tính đạt chỉ vì có External ID hoặc tổng thành phẩm bằng nhau. gồm cả unbuild
- Other move: phạm vi 712 move, không gồm điều chỉnh tồn. Dấu * chỉ số nguồn có bằng chứng trong snapshot cũ, có định danh SO/PO ngoài kỳ hoặc đã xử lý trong đợt hoàn tất; hợp nhất theo ID nguồn để không đếm trùng. Đây là độ phủ hồ sơ, không phải audit hay xác nhận tương đương tồn kho. [Chi tiết](../../../outputs/other-move-20261028/progress-coverage-20261029.json).

## Plan of work

### Final verify sau các phiên thực hiện

[Kế hoạch final verify tháng 7–10](FINAL_VERIFY_PLAN.md): đối chiếu số lượng SO/PO, MO/unbuild, Invoice/Bill và tồn thực cuối kỳ hết 25/10/2026 Malaysia; tái sử dụng quy tắc/lịch sử ánh xạ của các phiên. Không verify Transfer/Other move, không kiểm tra tiền và không đối chiếu riêng tám cột tiến độ. Đo đầy đủ chênh lệch tồn trước, sau đó mới truy nguyên gồm tồn tạm, đối ứng, adjustment và các nguyên nhân khác; không loại các khoản này khỏi tồn thực. Mọi lệch tồn còn lại chặn nghiệm thu tồn. **Đã lập kế hoạch, chưa chạy final verify**; bắt đầu chụp nghiệm thu sau khi writer kết thúc và RPC chưa rõ được xác minh.

### Bill posted tháng 9–10 — phiên riêng

Đã nghiệm thu theo baseline gốc: **159/159 tháng 9**, **114/114 tháng 10**, 273 Bill có binding duy nhất và trạng thái posted; 713/713 dòng hóa đơn có External ID. [Verification cuối](../../../outputs/bill-sep-oct-20261028/verification.json), [kế hoạch và quyết định](BILL_T9_T10_PLAN.md), [checkpoint](../../../outputs/bill-sep-oct-20261028/CHECKPOINT.md).

Mốc ban đầu 96/159 gồm 91 binding posted và 5 ứng viên posted; 55/114 gồm 53 binding posted và 2 ứng viên posted, còn một ứng viên draft. Các ứng viên đã được xác minh hoặc hoàn tất theo quyết định; 448525 và 448536 phát sinh sau baseline không tính vào mẫu số. [Baseline](../../../outputs/bill-sep-oct-20261028/baseline.json), [phạm vi](../../../outputs/bill-sep-oct-20261028/source-scope.json).

Ngoại lệ được duyệt: Bill 443309 giữ hạn đích và khác UOM; 14 Bill dùng CNH nguồn → CNY đích; Bill 445562 giữ thông tin hai dòng ±0,01 CNH trong hồ sơ; Bill 441466 bổ sung bút toán riêng 83638 Nợ 1876/Có 1887, audit đạt. Bốn dòng ghi chú có lượng nguồn 1/đích 0, giá trị 0 và nội dung khớp. Bruce nghiệm thu hiện trạng **83 Bill liên kết PO tạo trực tiếp** trước chỉ đạo Create Bill: đã kiểm tra dữ liệu và dòng kế toán, nhưng chưa chứng minh đầy đủ tương đương action PO. [Danh sách và giới hạn](../../../outputs/bill-sep-oct-20261028/direct-created-po-bills-review.json), [phê duyệt](../../../outputs/bill-sep-oct-20261028/direct-created-po-bills-approval.json).

Journal Bill không có thao tác chưa rõ; kiểm tra khóa Bill đã được nhả. Khóa Bill riêng chỉ điều phối writer Bill cùng máy, không điều phối writer kho; việc chạy song song đã được Bruce chấp thuận. Không tự chạy lại Bill hoặc bút toán đã xử lý.

**Bổ sung ngày 30/10:** Bruce duyệt chuyển bốn Bill phát sinh sau tập gốc; không có PO trên các dòng nguồn. Đã tạo/post và audit độc lập 448525→83639, 448536→83640, 448794→83641, 448795→83642; bốn cặp có External ID đầu/dòng, tổng kiểm 4/4 đạt. Giữ baseline 273 cũ, thêm [overlay bốn Bill](../../../outputs/final-verify-20261030T095459+0700/bill-baseline-extension-four.json) và [audit toàn tập](../../../outputs/final-verify-20261030T095459+0700/four-bill-final-verification.json). Đây chưa phải nghiệm thu final verify toàn kỳ.

**Sửa ngày Invoice ngày 30/10:** theo duyệt của Bruce, ba cặp 447624→83289, 447865→83329 và 447880→83330 đã sửa ngày hóa đơn, ngày kế toán và hạn thanh toán về 26/10 như v14; mỗi chứng từ được post lại và audit độc lập. [Tổng kiểm](../../../outputs/final-verify-20261030T095459+0700/three-invoice-date-final-verification.json) đạt, 15 External ID đầu/dòng được xác nhận; [overlay mapping](../../../outputs/final-verify-20261030T095459+0700/invoice-date-baseline-extension-three.json). Ba cặp ngoài cutoff sau sửa. Cần chạy lại final verify và tồn sau các thay đổi, không suy nghiệm thu từ số đếm.

### MO done

[Kế hoạch MO done tháng 7–10](MO_DONE_T7_T10_PLAN.md): audit đầy đủ MO và unbuild theo từng tháng.

Tháng 8: 408 MO và 5 unbuild đạt audit trước đó; thêm 2 MO đã hoàn tất và audit độc lập đạt, tổng cộng 415/415 theo các lượt audit riêng. Chưa chụp lại toàn bộ sau lượt ghi cuối. [Audit ban đầu](../../../outputs/mo-done-20261028/month-08-full-capture-20261028T012150226064Z/audit-summary.json), [MO 24716](../../../outputs/po-move-migration-20261027/september-mo24716-003-independent-audit-20261028T025226907568Z/audit.json), [MO 25134](../../../outputs/po-move-migration-20261027/september-mo25134-independent-audit-20261028T025237651526Z/audit.json).



Tháng 10: audit live đạt **362/362 MO và 5/5 unbuild**, tổng **367/367**; không còn MO chưa nhận diện. [Audit MO](../../../outputs/mo-done-20261028/month-10-full-capture-20261028T131121746241Z/audit-summary.json), [audit 5 unbuild](../../../outputs/mo-done-20261028/october-unbuild-final-audit-20261028T131155244531Z/audit-summary.json), [hồ sơ nghiệm thu](../../../outputs/mo-done-20261028/october-mo-final-acceptance-20261028.json).

Tháng 9: audit độc lập sau lượt ghi cuối đạt **552/552 MO và 6/6 unbuild**, tổng **558/558**. Không có thao tác journal chưa rõ; các khoản tồn tạm tiếp tục đối chiếu nguồn cung trong mục ngoại lệ, còn nghiệm thu tồn toàn công ty là mốc riêng. [Audit MO](../../../outputs/mo-done-20261028/month-09-full-capture-20261028T062719786509Z/audit-summary.json), [audit unbuild](../../../outputs/mo-done-20261028/september-unbuild-full-audit-20261028T062829184489Z/audit-summary.json), [hồ sơ nghiệm thu](../../../outputs/mo-done-20261028/september-mo-final-acceptance-20261028.json).


### SO delivered

[Kế hoạch SO delivered tháng 7–10](SO_DELIVERED_T7_T10_PLAN.md): theo chỉ đạo 29/10, chạy một hàng đợi chung tháng 7–10 theo mẻ lớn, không chờ theo tháng và không xếp thứ tự phụ thuộc giữa SO, không pilot, không tiền kiểm riêng, không audit mẫu/mẻ/cuối mốc; giữ journal và guard live chống ghi trùng, đúng SO/sản phẩm/lot/lượng. Bỏ xét hạn lot; lot master thiếu thì tạo đúng sản phẩm. Thiếu tồn đúng lot thì cấp tạm phần thiếu; Bruce đã yêu cầu tắt tạm cơ chế tự phân bổ khi nhập, chuyển nội bộ hoặc điều chỉnh tồn trên toàn v19 và khôi phục trạng thái ban đầu khi kết thúc. Ghi journal và theo dõi đối chiếu nguồn cung.

**Cách theo dõi mốc:** Chụp live `qty_delivered` từng dòng khi cần báo tiến độ; nêu thời điểm và giới hạn mapping/UOM. Không gọi số sơ bộ là audit hoặc nghiệm thu độc lập.

### Other move

**Cách theo dõi mốc (chỉ đạo mới 29/10):** tổng hợp kết quả xử lý theo ba nhóm SO/PO ngoài kỳ (499), chuyển kho độc lập (95), scrap (118); không chia đợt theo tháng, không tiền kiểm, không audit và không chờ khóa của session SO delivered. Giữ journal và đọc lại khi RPC mất phản hồi. Bảng thể hiện độ phủ hồ sơ, gồm snapshot lịch sử và kết quả các đợt.

[Kế hoạch Other move](OTHER_MOVE_T7_T10_PLAN.md): chạy → lưu kết quả/journal; ghi song song với session SO delivered, không đợi khóa giữa hai session, không tiền kiểm hoặc audit.

**Quyết định Bruce ngày 29/10/2026:** migrate theo thứ tự **Move thuộc SO/PO ngoài kỳ → Chuyển kho độc lập → Scrap — loại bỏ/phế hàng**. Không migrate **inventory adjustment**; loại 235 move khỏi tập 947 trước đây, còn **712 move** (499 + 95 + 118). Không xóa hoặc đảo adjustment đã có trên đích.

Tiến độ Other move ngày 29/10: **669/712** move có bằng chứng theo cách đo trong bảng; còn **43** chưa có trong tập bằng chứng này. Đã chuyển sang scrap theo chỉ đạo, trong khi 38 move chuyển kho tiếp tục giữ chờ. Không tiền kiểm, không audit; [checkpoint](../../../outputs/other-move-20261028/CHECKPOINT.md).


## Ngoại lệ chưa xử lý

| Vấn đề | Cần làm |
|---|---|
| Tồn tạm đã cấp | Đối chiếu nguồn cung thật, tránh ghi trùng các adjustment `32389`, `32392`, `32737`, `32750`, `32761`, `32773`–`32776`, `32787`, `33122`, `33168`-`33170`, `33185`. Quyết định, lot và chứng từ liên quan: [checkpoint](../../../outputs/mo-done-20261028/CHECKPOINT.md). |
| `HQ/MO/26236` | Move đã audit đạt; tồn đúng lot trước move khớp 25,75 KG-L, song tổng sản phẩm lệch 3,145 KG (v14 55,225; v19 52,08). Truy trong đối chiếu cutoff. [Trace](../../../outputs/po-move-migration-20261027/october-mo26236-stock-precutoff-20261027T210022837149Z/trace.json). |
| `HQ/INT/06391` tháng 8 | Kiểm tra lại hai lot và phiếu CL28 sau khi nhả giữ SO; chưa coi chuỗi đã hoàn tất. [Hồ sơ trước nhả](../../../outputs/po-move-migration-20261027/cl28-reservation-delivery-20261027T195011307333Z/summary.json), [lượt nhả](../../../outputs/mo-done-20261028/pending-so-unreserve-preflight-20261028T054806246083Z/cases.json). |
| `SO-53682` tháng 8 | Các move trả hàng đã done, nhưng v19 còn move trung gian chờ với liên kết khác nguồn; kiểm tra chuỗi trước sửa. [Chuỗi](../../../outputs/po-move-migration-20261027/so53682-chain-20261027T193505979867Z/). |
| `PO-04094` tháng 8 | Ba move nhập done đã mang dấu nguồn, serial đã xuất, nhưng PO đích chưa gắn dòng nên `qty_received=0`; xử lý liên kết, không nhận trùng. [Hồ sơ](../../../outputs/po-move-migration-20261027/epson-po-supply-trace-20261027T192142294908Z/status.json). |
| Move cất kho `492349` | Thiếu liên kết lần nhập tháng 6 trên v19; truy nguồn và phụ thuộc khác kỳ trước xử lý. [Trace](../../../outputs/po-move-migration-20261027/june-po-parent-20261027T192642046764Z/summary.json). |
| Scrap tháng 8 | `SP/00104` thiếu 2 thùng đúng lot; hai move đổi lot CYAN có tồn lot xuất bằng 0. Giữ chờ, không tạo tồn âm. [Trace](../../../outputs/po-move-migration-20261027/august-scrap-source-trace-20261027T193749294195Z/summary.json). |

## Kinh nghiệm ngoại lệ đã xử lý

Trước khi hỏi Bruce, đối chiếu quyết định và hồ sơ đã có; chỉ áp dụng đúng phạm vi đã duyệt. Ngoại lệ mới cần quyết định thì bổ sung bài học chung tại đây, không ghi record ID và không tạo Excel ngoại lệ.

| Vấn đề | Bài học và quyết định |
|---|---|
| Lot/serial | Tạo lot thiếu đúng sản phẩm, sửa hạn theo nguồn khi đã được duyệt; xác minh danh tính nếu tên có khoảng trắng. Trường hợp đích không theo lot chỉ bỏ lot hoặc chuyển tồn sang không lot theo quyết định cụ thể, giữ bằng chứng và tổng tồn. |
| Các quyết định MO tháng 10 | Bruce duyệt chuyển 4 M-L từ lot cũ sang không lot cho MO `26723`; bật sản phẩm 119744 cho MO `26378`; cấp tạm 1,5 KG cho `26435`, 5,2 KG-L cho `26438`, 1,24 KG-L cho `26632` và cấp tạm 1 BOX CYAN cho `26623`; đối chiếu nguồn cung. |
| Tồn tạm | Chỉ cấp theo quyết định từng trường hợp; ghi journal, đọc lại và đối chiếu nguồn cung thật để tránh ghi trùng. Khoản chưa đối chiếu vẫn theo dõi trong bảng ngoại lệ chưa xử lý. |
| Giấy A4 thiếu mapping | Bruce chọn dùng sản phẩm gói 100 tờ v19 cho hai MO; dùng lot `NO BATCH` theo quyết định Bruce. |
| Sản phẩm và UOM | Tên hoặc thông số khác phải có bằng chứng và xác nhận phù hợp. UOM tương đương thì giữ UOM đích, lưu quy đổi; không tự sửa danh mục. |
| Unbuild | Nếu đã chứng minh move done, MO gốc, lượng, lot và ngày, khôi phục phiếu và gắn move hiện có theo quyết định đã duyệt; kiểm tra tồn không đổi, không chạy lại unbuild. |
| Nhận từng phần/cất kho | Giữ từng lần và ngày nguồn. Phiếu done đã gộp cần phương án đối ứng có truy vết, bảo toàn tổng tồn theo vị trí/lot và lượng nhận PO; xác minh phụ thuộc khác kỳ trước sửa. |
| Trả hàng | Liên kết đúng move gốc, giữ ngày/lot và các chặng nguồn. Nhà cung cấp đi Stock → Input → Vendors; khách trả hàng cần kiểm tra điểm đến do wizard chọn trước xác nhận. |
| Ngày lịch sử và RPC | Đặt ngày bắt đầu trước hoàn tất; sau action đọc lại và khôi phục ngày chứng từ, move, chi tiết. Phản hồi không rõ phải đối chiếu journal và trạng thái live trước khi tiếp tục, tránh ghi lặp. |
| Giữ hàng | Nhả phần giữ sai và phân bổ lại đúng lot trong phạm vi đã duyệt; kiểm tra ảnh hưởng các phiếu liên quan. |
| Bill/Invoice | Ánh xạ đối tác, PO và dòng bằng định danh nguồn; giữ hạn, tỷ giá và từng chứng từ lịch sử. Lượng nhận PO không phải điều kiện bắt buộc để tạo/post Bill liên kết PO. Tài khoản hoạt động và ngoại lệ chỉ áp dụng theo danh sách đã duyệt trong hồ sơ Bill. |
| Trùng số chứng từ | Phân biệt bằng định danh nguồn, đối tác và nội dung; dùng số đích tự sinh, lưu số nguồn để tra cứu. |



