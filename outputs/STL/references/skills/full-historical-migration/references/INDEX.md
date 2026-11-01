# Danh mục script Full Historical Migration

## Gom theo tháng và chặng (26/10/2026)

- `resume_pysb_stock_phase.py --kind delivery --mode batch --monthly`: chọn tháng Malaysia sớm nhất còn chuỗi đủ điều kiện. Bắt đầu hai chuỗi cùng luồng; chỉ mở rộng sau khi mẫu Validate chung chặng phụ thuộc đã hoàn tất đủ chuỗi và vượt kiểm chứng cuối. `native_picking_batch_pilot.finish_monthly` chọn các chặng có mọi tiền nhiệm đã hoàn tất, cùng loại phiếu, thuộc các chuỗi độc lập; gom tạo chi tiết, kiểm tra tổng nguồn tồn, native Validate rồi khôi phục ngày và đối chiếu. Không giới hạn theo ngày/10/100; luồng chưa chứng minh vẫn thử mẫu, chuỗi qua tháng cần review riêng. Các phiếu bị giữ không được tính xong tháng. Nhật ký từng thao tác và hàng rào chống lặp Validate vẫn giữ.
- Hàng đợi stock dùng `--monthly` cho DO, giữ ưu tiên nhập PO và kiểm tra lại khả năng Inventory/MO trước tiêu thụ. Hiện adapter gom ghi theo chặng áp dụng cho picking DO; Inventory adjustment/MO tiếp tục qua writer riêng, không giả định mọi Inventory move đều là kiểm kê hoặc dùng cùng nút Validate.
- `tests/test_monthly_stock_batches.py`: ranh giới tháng Malaysia, chuỗi qua tháng, phụ thuộc, mẫu đầy đủ trước mở rộng, không Validate lại chặng, chặn predecessor native chưa Done. Số liệu chuẩn bị/toàn lượt và đếm RPC nằm trong `phases/stock-last-group.json` của lượt tháng.

## Gom DO theo ngày Malaysia (26/10/2026)

- `resume_pysb_stock_phase.py --kind delivery --mode batch --daily` chọn ngày hoàn tất v14 sớm nhất trong hàng đợi đủ điều kiện, không giới hạn 10/100. Luồng mới vẫn thử mẫu; các gốc độc lập cùng loại được chuẩn bị chi tiết và Validate chung qua `native_picking_batch_pilot.finish_daily`, rồi hoàn tất chặng phụ thuộc. Cần quyền theo ngày và mẫu 10 phiếu đã kiểm chứng. Chứng từ bị giữ vẫn chưa hoàn tất, không kết luận cả ngày đã xong. `run_pysb_stock_only_queue.py` dùng chế độ này, giữ ưu tiên nhập PO, kiểm tra tồn, nhật ký và đối chiếu cuối chuỗi.
- `tests/test_daily_stock_batches.py`: mốc nửa đêm Malaysia, chọn cả ngày trên 100 phiếu, chặn chuỗi qua ngày, gom 12 gốc một lần và bỏ qua gốc đã hoàn tất khi chạy chặng sau.

## Quyết định production được bổ sung ngày 25/10/2026

- [repair_pysb_pvc_opening.py](repair_pysb_pvc_opening.py): **riêng 50 UNIT PVC nguồn 51469 → đích 112635, Packing Zone 9** theo phê duyệt. Native inventory count, không sửa trực tiếp quant.quantity; giữ giá vốn 0,70, xác minh giá trị 35 MYR, không sinh bút toán với cấu hình periodic; ngày đầu kỳ `2026-06-30 15:59:59 UTC`. Có nhật ký chống ghi lặp và kiểm chứng hai mốc. Không dùng để cấp tồn tạm hoặc sửa sản phẩm khác.

- [historical_account_selection.py](historical_account_selection.py): ánh xạ tài khoản theo chứng từ cũ, tách theo sản phẩm/loại chứng từ khi cần; loại tài khoản chung `v14`, giữ mơ hồ. Điều khoản so lịch đến hạn, không chỉ tên. Chỉ kích hoạt với phê duyệt trong hồ sơ; preflight kiểm tra lại metadata.
- [apply_pysb_tracking_decisions.py](apply_pysb_tracking_decisions.py): **riêng đúng ba master đã duyệt** MIMAKI serial, PTC theo lot, AINKJET serial; kiểm tra không có move mở/giữ chỗ và chứng minh tồn không đổi. PP PRIMER giữ `none` theo ngoại lệ được lưu. Không dùng để đổi tracking chung hoặc sửa quant.
- [create_pysb_new_ed42.py](create_pysb_new_ed42.py): **riêng nguồn 54870/54871**; tạo hai hồ sơ mới được duyệt, giữ hồ sơ cũ archive, kiểm tra thuế/đơn vị/nhóm/danh tính và External ID, có nhật ký chống trùng. Không chạy cho sản phẩm khác.
- Hồ sơ quyết định và kết quả: `outputs/pysb-aug-oct-prod-20261024/CAP_NHAT_QUYET_DINH_20261025.md`. Các báo cáo trước đó là bằng chứng theo thời điểm, không thay trạng thái cập nhật.

Bản chuẩn của script thuộc skill nằm tại đây; không duy trì bản sao trong `test_script/`. Di chuyển chỉ chuẩn hóa đường dẫn, không cấp quyền chạy lại các script ghi. Đọc mã và hồ sơ đầu vào đúng đợt trước khi dùng: nhiều file là xử lý riêng có ID cố định, một số file gọi nghiệp vụ ngay khi chạy và không có chế độ đọc.

Helper SO/PO dùng chung: [test_prepare_july_2026_so_po_migration.py](../../so-po-migration/scripts/test_prepare_july_2026_so_po_migration.py). Không sao chép helper này vào skill lịch sử.

[Hướng dẫn theo bước](../SKILL.md) · [Hồ sơ ngoại lệ DO/MO](PYSB_DO_MO_Exception_Records_EN.xlsx).

## Invoice, Bill và kế toán

- [historical_invoice_checks.py](historical_invoice_checks.py) — hàm dùng chung, không ghi Odoo: suy tỷ giá từ dòng nguồn, mapping salesperson theo login, báo khác biệt contact/parent/company_name, kiểm tra readback nguyên tệ/MYR và dòng. Prepare/create/audit draft/post dùng cùng bộ kiểm tra phiên bản 1; manifest cũ phải prepare lại. Scope/output của các entrypoint vẫn gắn đợt cũ.
- [tests/test_historical_invoice_checks.py](tests/test_historical_invoice_checks.py) — kiểm thử offline FX, salesperson, contact; hồi quy hồ sơ 18 Bill/17 Invoice khi có evidence local.

- [audit_pysb_sue_invoice_feedback.py](audit_pysb_sue_invoice_feedback.py) — chỉ đọc nguồn/đích, đối chiếu tiền công ty, nguyên tệ, header và file Bill của Sue; offline mặc định, đọc hướng dẫn trong SKILL.md trước dùng.
- [tests/test_audit_pysb_sue_invoice_feedback.py](tests/test_audit_pysb_sue_invoice_feedback.py) — kiểm thử hồi quy offline cho công cụ audit mới.
- [audit_pysb_historical_invoice_drafts.py](audit_pysb_historical_invoice_drafts.py) — Final commercial draft audit only; AR/AP, payments and bank matching deferred.
- [create_pysb_historical_invoice_drafts.py](create_pysb_historical_invoice_drafts.py) — Idempotent draft-only creation with source freeze, exact commercial read-back.
- [finish_pysb_explicit_account_mapping.py](finish_pysb_explicit_account_mapping.py) — Apply Bruce's explicit machine-account choices to the 13 remaining draft lines.
- [inspect_pysb_historical_invoices.py](inspect_pysb_historical_invoices.py) — Read-only Invoice/Bill scope through July order links, all source dates.
- [migrate_pysb_credit_notes.py](migrate_pysb_credit_notes.py) — Staging-only historical Credit Notes, explicit provenance and resumable journal.
- [post_pysb_historical_invoices.py](post_pysb_historical_invoices.py) — Post only proven migrated Invoice/Bill ids; no payments or reconciliation.
- [prepare_pysb_historical_invoices.py](prepare_pysb_historical_invoices.py) — Prepare complete historical draft invoices; no Odoo writes or master creation.
- [prepare_pysb_supplement_posting_accounts.py](prepare_pysb_supplement_posting_accounts.py) — Use already-approved active account policy for the isolated July supplement.
- [preserve_pysb_einvoice_reference.py](preserve_pysb_einvoice_reference.py) — Copy historical MyInvois metadata only, without sending or validating externally.
- [remap_pysb_archived_invoice_accounts.py](remap_pysb_archived_invoice_accounts.py) — Operator-approved transaction-line remap; no account/product master changes.
- [render_pysb_exception_decisions.py](render_pysb_exception_decisions.py) — Render the three operator decisions in UTF-8, with the full 315-line audit.
- [report_pysb_credit_notes.py](report_pysb_credit_notes.py) — Read-only final Credit Note and SO invoiced-quantity verification.
- [report_pysb_july_invoice_supplement.py](report_pysb_july_invoice_supplement.py) — July invoice-date coverage across original and supplemental source provenance.
- [report_pysb_posted_invoices.py](report_pysb_posted_invoices.py) — Current posting and preserved E-invoice-reference report; no reconciliation.
- [resolve_pysb_supplement_final_exceptions.py](resolve_pysb_supplement_final_exceptions.py) — Approved Insurance consolidation, D&D creation, and SC-F9430 account choice.
- [supplement_pysb_july_invoices.py](supplement_pysb_july_invoices.py) — Isolated July-date supplement reusing verified invoice tools, never old outputs.

## SO/PO và ngoại lệ

- Bổ sung SO ngày 25/10/2026: Bruce đã cho phép duyệt native, kiểm tra/sửa cả sáu nhóm ngoại lệ và thêm đúng 16 SO thiếu. Quyền này lưu ở `phases/operator-so-remediation-approval.json`, không mở rộng sang validate kho/kế toán hoặc sửa master chung. Hồ sơ riêng: `so-remediation/` dưới đợt production hiện tại.
- [inspect_pysb_so_remediation.py](inspect_pysb_so_remediation.py), [inspect_pysb_so_supplement.py](inspect_pysb_so_supplement.py), [inspect_pysb_missing_so_masters.py](inspect_pysb_missing_so_masters.py), [inspect_pysb_dropship_so.py](inspect_pysb_dropship_so.py) — đọc định danh, quyền duyệt và phụ thuộc nguồn/đích; ba script bổ sung không giữ khóa writer.
- [prepare_pysb_so_repairs.py](prepare_pysb_so_repairs.py), [prepare_pysb_missing_so.py](prepare_pysb_missing_so.py) — lập phương án local, không ghi DB. Không dùng barcode/VAT đơn lẻ để ép ghép; lưu bằng chứng địa chỉ/cha–con và template/variant.
- [apply_pysb_so_repairs.py](apply_pysb_so_repairs.py) — sửa đúng record trong phương án đã duyệt, mẫu trước nhóm, nhả khóa sau từng record. Đổi sản phẩm phải truyền đồng thời giá/mô tả lịch sử để tránh native recompute. [recover_pysb_pd1900_commercial.py](recover_pysb_pd1900_commercial.py) là phục hồi riêng dòng 193912 → 11842, không dùng như công cụ sửa giá chung.
- [create_pysb_missing_so.py](create_pysb_missing_so.py) — bổ sung đúng 16 SO nháp đã được duyệt bằng ORM native, External ID đầu/dòng, kiểm chứng toàn bộ thương mại; không confirm trong bước tạo, không sinh master.
- [resume_pysb_so_short_batches.py](resume_pysb_so_short_batches.py), [production_so_route_proof.py](production_so_route_proof.py) — đọc trước không giữ khóa; mỗi kho/tuyến lấy mẫu riêng, native confirm từng SO, đọc lại nhóm tối đa 25 và nhả khóa giữa nhóm. `applied-overlay.json` chứa ánh xạ bổ sung, ngoại lệ PC theo SKU và hai địa chỉ GENTING archive được chứng minh lịch sử; không unarchive contact. Riêng SO 65338 giữ route Dropship, confirm với `skip_procurement` theo API native để không tạo thêm PO vì PO nguồn 5581 → đích 1040 đã tồn tại; chuỗi kho sẽ tái sử dụng POL 3888 và SOL 26017 theo move nguồn 533596. Không xem confirmed SO này là đã giao hàng.

- [confirm_pysb_prod_so.py](confirm_pysb_prod_so.py) — **Riêng hồ sơ production tháng 8–10/2026**: preflight thương mại và tuyến HQ MTS, sample trước batch; dùng `--singleton` vì bản `paoyeang_sale.write` production lỗi khi ghi nhiều SO. `--all --limit 25 --singleton` gọi confirm từng SO và đối chiếu theo nhóm, không validate kho hoặc tạo hóa đơn. Lỗi phải đọc lại; `--recover-group-nochange` chỉ phục hồi đúng mẫu hai SO lỗi singleton khi chứng minh đầy đủ không có hiệu lực. Phê duyệt tiếp tục SO của Bruce ngày 25/10 thay chỉ dẫn dừng sau PO đối với riêng bước SO; không cấp quyền kho/kế toán.
- [verify_pysb_prod_so_confirmation.py](verify_pysb_prod_so_confirmation.py) — **Chỉ đọc production**: đối chiếu lại toàn phạm vi SO, ngày lịch sử và dữ liệu thương mại của nhóm xác nhận mới; kiểm tra liên kết phiếu kho và đóng gate với các nhóm giữ chờ riêng.

- [audit_pysb_confirmed_po_staging.py](audit_pysb_confirmed_po_staging.py) — Read-only final audit against the durable confirmation batch journal.
- [audit_pysb_confirmed_so_staging.py](audit_pysb_confirmed_so_staging.py) — Final SO/line and document-link audit only; no stock/accounting reconciliation.
- [confirm_pysb_july_po_staging.py](confirm_pysb_july_po_staging.py) — Confirm PYSB July POs on staging only; default is read-only preflight.
- [confirm_pysb_july_so_staging.py](confirm_pysb_july_so_staging.py) — Staging-only SO confirmation in batches; no inventory/accounting audit.
- [confirm_pysb_so53440_free_item.py](confirm_pysb_so53440_free_item.py) — Bruce-approved free-item exception for SO-53440, staging only.
- [correct_pysb_so_po_lines.py](correct_pysb_so_po_lines.py) — Correct known July line differences on staging, without workflow changes.
- [repair_pysb_so_base_prices.py](repair_pysb_so_base_prices.py) — Correct three known historical SO base prices; never changes selling prices.
- [supplement_pysb_missing_po_lines.py](supplement_pysb_missing_po_lines.py) — Scoped XML-RPC supplement: four known service lines, staging only.

## Kho, MO, helper và xử lý riêng

- [inspect_pysb_aug_oct_prod.py](inspect_pysb_aug_oct_prod.py), [enrich_pysb_aug_oct_prod.py](enrich_pysb_aug_oct_prod.py) — **Chỉ đọc**, hồ sơ riêng `outputs/pysb-aug-oct-prod-20261024`: quét nguồn tháng 8 đến mốc chụp, chứng từ và master hai phía production; không phải công cụ ghi migration. Snapshot chưa `complete` không dùng để nghiệm thu.
- [verify_pysb_prod_orders.py](verify_pysb_prod_orders.py), [order_quantity_checks.py](order_quantity_checks.py) — **Chỉ đọc/offline**: kiểm tra từng dòng SO/PO ordered, delivered/received, invoiced gồm dịch vụ và báo phụ thuộc ngoài kỳ. Gọi qua `report_pysb_order_fulfillment.py --production-evidence-dir ...`.
- [tests/test_order_quantity_checks.py](tests/test_order_quantity_checks.py) — Kiểm thử offline kiểm tra lượng từng dòng; không kết nối Odoo.
- [verify_pysb_prod_mos.py](verify_pysb_prod_mos.py), [mo_quantity_checks.py](mo_quantity_checks.py), [tests/test_mo_quantity_checks.py](tests/test_mo_quantity_checks.py) — Đối chiếu MO và kiểm thử offline, gồm thiếu phụ phẩm và tiêu hao trùng.
- [prepare_pysb_aug_oct_manifest.py](prepare_pysb_aug_oct_manifest.py), [resolve_pysb_aug_oct_masters.py](resolve_pysb_aug_oct_masters.py), [inspect_pysb_aug_oct_accounting.py](inspect_pysb_aug_oct_accounting.py), [check_pysb_aug_oct_coverage.py](check_pysb_aug_oct_coverage.py), [check_pysb_aug_oct_opening.py](check_pysb_aug_oct_opening.py) — Khảo sát/kiểm chứng **chỉ đọc** hoặc hồ sơ local. Manifest `discovery_only` chưa được phép dùng cho script ghi. Kiểm tra tồn đầu kỳ theo sản phẩm đã ánh xạ không thay nghiệm thu tồn toàn công ty hoặc chi tiết location/lot/package/owner.

- [apply_pysb_missing_source_adjustments.py](apply_pysb_missing_source_adjustments.py) — Replay evidenced missing v14 inventory deltas, with existing products/lots only.
- [apply_pysb_source_adjustment_508338.py](apply_pysb_source_adjustment_508338.py) — Replay one evidenced source inventory adjustment, then finish its blocked MO.
- [apply_pysb_supporting_adjustments.py](apply_pysb_supporting_adjustments.py) — Replay complete source inventory/product groups including both sides of lot swaps.
- [apply_pysb_temporary_negative_stock.py](apply_pysb_temporary_negative_stock.py) — Approved temporary stock, only for evidenced source-negative pending lines.
- [batch_pysb_old_po_receipts.py](batch_pysb_old_po_receipts.py) — Read-back recovery and batched preparation of old-PO standalone receipts.
- [batch_pysb_supporting_inventory_adjustments.py](batch_pysb_supporting_inventory_adjustments.py) — Native inventory application in disjoint batches, preserving source pair groups.
- [bridge_pysb_closed_return_chain.py](bridge_pysb_closed_return_chain.py) — Approved +1/-1 stock bridge, native chronological validation, exact read-back.
- [check_pysb_sol_cost_v14_v19.py](check_pysb_sol_cost_v14_v19.py) — Read-only July PYSB sale-line historical Cost comparison.
- [classify_pysb_source_negative_stock.py](classify_pysb_source_negative_stock.py) — Evidence source stock immediately before consumption for pending shortages.
- [complete_pysb_closed_return_chain.py](complete_pysb_closed_return_chain.py) — Replay the evidenced six-picking closed return loop without extra stock credits.
- [complete_pysb_stock_migration.py](complete_pysb_stock_migration.py) — Complete prepared stock events chronologically and emit a combined quantity audit.
- [create_pysb_6115_28mm_and_quantity_ptc.py](create_pysb_6115_28mm_and_quantity_ptc.py) — Explicit operator-approved one new SKU and PTC013WS quantity tracking.
- [discover_pysb_closing_gaps.py](discover_pysb_closing_gaps.py) — Read complete source documents explaining July closing gaps, staging guarded.
- [discover_pysb_old_po_receipts.py](discover_pysb_old_po_receipts.py) — Read-only inventory of pre-July POs with completed receipts from July onward.
- [discover_pysb_supporting_stock.py](discover_pysb_supporting_stock.py) — Read-only discovery of real omitted stock flows supporting pending documents.
- [enrich_pysb_stock_snapshot.py](enrich_pysb_stock_snapshot.py) — Read-only dependencies for company-1 historical stock migration.
- [execute_pysb_stock_migration.py](execute_pysb_stock_migration.py) — Company-1 historical stock migration, staging only; explicit journal, no RPC retries.
- [export_pysb_stock_exception_records.py](export_pysb_stock_exception_records.py) — Xuất record ngoại lệ kho có link v14/v19; chỉ gọi API đọc.
- [finish_pysb_old_po_receipts.py](finish_pysb_old_po_receipts.py) — Complete prepared old-PO chains in batches, with read-back and UTC dates.
- [finish_pysb_supporting_transfers.py](finish_pysb_supporting_transfers.py) — Use reviewed native validation and quantity readback for supporting transfers.
- [fix_pysb_opening_packages.py](fix_pysb_opening_packages.py) — Restore missing package dimension on evidenced existing opening inventory lines.
- [fix_pysb_picking_partners.py](fix_pysb_picking_partners.py) — Use existing cleaned v19 SO shipping/vendor partners on migrated stock headers.
- [import_pysb_all_old_po_receipts.py](import_pysb_all_old_po_receipts.py) — Standalone replay of approved old-PO late receipts; existing masters only.
- [import_pysb_standalone_receipts.py](import_pysb_standalone_receipts.py) — Replay two approved missing July supply chains without importing old POs.
- [inspect_pysb_last_support_chain.py](inspect_pysb_last_support_chain.py) — inspect_pysb_last_support_chain
- [inspect_pysb_stock_migration.py](inspect_pysb_stock_migration.py) — Read-only source/target stock migration inventory, company 1 only.
- [investigate_pysb_po_supplier_gap.py](investigate_pysb_po_supplier_gap.py) — Read-only supplier provenance investigation for the 16 blocked July POs.
- [map_pysb_other_stock_existing_products.py](map_pysb_other_stock_existing_products.py) — Map extra stock products to existing cleaned masters, never create products.
- [prepare_pysb_stock_plan.py](prepare_pysb_stock_plan.py) — Offline mapping and exception report; no Odoo writes.
- [prepare_pysb_supporting_transfers.py](prepare_pysb_supporting_transfers.py) — Separate ledger for authorized supporting transfers; reuse reviewed preparation.
- [prove_pysb_later_source_negative_consumption.py](prove_pysb_later_source_negative_consumption.py) — Find already-replayed source-negative consumption explaining physical shortages.
- [read_pysb_mo_details.py](read_pysb_mo_details.py) — Read source MO execution and target dependencies; company 1 only.
- [read_pysb_stock_balances.py](read_pysb_stock_balances.py) — Read full source quantity ledger for mapped products, for opening/closing gap reports.
- [record_pysb_closing_lot_aliases.py](record_pysb_closing_lot_aliases.py) — Record only uniquely evidenced whitespace aliases; preserve cleaned lot names.
- [record_pysb_historical_negative_allowances.py](record_pysb_historical_negative_allowances.py) — Evidence source-negative history without duplicating real later supply.
- [refine_pysb_stock_plan.py](refine_pysb_stock_plan.py) — Resolve MO dependencies read-only, generate execution manifest.
- [repair_pysb_mo_finished_preparation.py](repair_pysb_mo_finished_preparation.py) — Repair staging-only finished-move preparation; keep consumed raw moves done.
- [repair_pysb_pending_opening_lots.py](repair_pysb_pending_opening_lots.py) — Operator-approved opening corrections for five evidenced products only.
- [repair_pysb_resumed_mo_finished.py](repair_pysb_resumed_mo_finished.py) — Targeted recovery of MO 584; preserve already posted raw consumption.
- [repair_pysb_stock_historical_dates.py](repair_pysb_stock_historical_dates.py) — Restore source UTC dates after Odoo load timezone conversion; no validation.
- [replay_pysb_unbuild_and_scrap.py](replay_pysb_unbuild_and_scrap.py) — Native stock replay of two source Unbuild pairs and one standard Scrap.
- [resume_pysb_excluded_consignment_routes.py](resume_pysb_excluded_consignment_routes.py) — Resolve mapped NOVA and replace untouched default routes with exact source routes.
- [resume_pysb_tno120_quantity_tracking.py](resume_pysb_tno120_quantity_tracking.py) — Operator-approved quantity tracking; restore six omitted source pickings.
- [resume_pysb_untracked_material_mos.py](resume_pysb_untracked_material_mos.py) — Resume only the two previously excluded MOs after operator tracking change.
- [scan_pysb_july_other_stock_coverage.py](scan_pysb_july_other_stock_coverage.py) — **Chỉ đọc**: rà mọi move done trong tháng theo company/ngày; kiểm chứng trạng thái và chi tiết đích, không lọc theo đơn hoặc master đã ánh xạ. Giữ khóa output cũ, thêm danh sách move đầy đủ; mặc định output riêng. Chạy trước/sau DO/MO. Mã thoát 1 nghĩa là còn vấn đề/ngoại lệ.
- [temporary_pysb_uv_white_supply.py](temporary_pysb_uv_white_supply.py) — Explicitly approved temporary replacement for missing PO-04604 receipt.
- [topup_pysb_proven_later_negative_stock.py](topup_pysb_proven_later_negative_stock.py) — Complete source-negative credits for already replayed later consumption.
- [update_pysb_sol_historical_cost.py](update_pysb_sol_historical_cost.py) — Restore July historical SOL costs on staging only; journal every write.

## Báo cáo và đối chiếu

- [audit_pysb_late_so_supply.py](audit_pysb_late_so_supply.py) — Chỉ đọc DB: SO tháng 7, xuất tháng sau, nguồn nhập muộn và cách chuyển v19.
- [check_pysb_acceptance_current.py](check_pysb_acceptance_current.py) — Read-only current comparison of the user's migration acceptance checklist.
- [render_pysb_late_so_audit_summary.py](render_pysb_late_so_audit_summary.py) — Bản kết luận dễ đọc từ kết quả kiểm tra DB đã lưu, không kết nối ERP.
- [render_pysb_stock_exception_decisions.py](render_pysb_stock_exception_decisions.py) — Xuất quyết định lịch sử DO/MO từ trao đổi và hồ sơ local; không kết nối Odoo.
- [render_pysb_stock_reports.py](render_pysb_stock_reports.py) — Render a concise Vietnamese review report from completed reconciliation evidence.
- [report_pysb_all_old_po_result.py](report_pysb_all_old_po_result.py) — Final evidence for old-PO late receipts and the additional temporary adjustment.
- [report_pysb_closing_adjusted.py](report_pysb_closing_adjusted.py) — Warehouse and mapped consignment quantities, with approved temporary supply separated.
- [report_pysb_lot_balances.py](report_pysb_lot_balances.py) — Quantity-only opening/closing comparison by product and lot name.
- [report_pysb_order_fulfillment.py](report_pysb_order_fulfillment.py) — Read-only SO delivered/PO received comparison after historical stock migration.
- [report_pysb_product_balances.py](report_pysb_product_balances.py) — Native as-of-date quantity comparison for mapped migration products; no valuation.
- [report_pysb_standalone_receipts_result.py](report_pysb_standalone_receipts_result.py) — Publish the quantity-only result of the approved standalone receipts.
- [report_pysb_temporary_stock_result.py](report_pysb_temporary_stock_result.py) — Render durable evidence after the temporary-stock retry; no Odoo writes.

## Kiểm thử offline

## Đợt production PYSB tháng 8–10/2026

- Bruce duyệt thử Validate hàng loạt ngày 26/10: `resume_pysb_stock_phase.py --kind delivery --mode sample --bulk-pilot` dùng [native_picking_batch_pilot.py](native_picking_batch_pilot.py), chỉ đúng 2 phiếu chặng đầu độc lập cùng ngày/loại, tổng nhu cầu được kiểm tra cùng lúc. Action production ID 531 đã đọc và chứng minh gọi `records.button_validate()`. Gọi native một lần cho hai ID; sau đó đọc từng phiếu done, khôi phục ngày nguồn riêng và kiểm chứng toàn chuỗi. Mất phản hồi/wizard hoặc trạng thái bất ngờ thì dừng, không gọi validate lại. Mẫu chưa đồng nghĩa cho phép áp dụng nhóm lớn hay gộp chặng phụ thuộc. Hồ sơ quyền/live action/kết quả dưới `phases/`.

- Theo Bruce duyệt ngày 26/10, `check_pysb_aug_oct_coverage.py --after-run --incremental` dùng kết quả đã kiểm chứng làm cache, đọc live các move mới/đổi ánh xạ/chưa đạt rồi chạy lại bộ đối chiếu toàn tập nguồn. Báo cáo ghi rõ `verification_mode`, mốc `full_target_readback_utc` và không cho nghiệm thu đầy đủ ở mode incremental. `run_pysb_stock_only_queue.py` quét target đầy đủ sau tối đa 5 nhóm và cuối hàng đợi; đầu phiên luôn full. Không bỏ đọc lại sau ghi hoặc kiểm tra live nguồn tồn trước validate. Receipt preflight được làm lại ở checkpoint hoặc sau nhóm receipt thay vì lặp mọi nhóm DO. Mẫu luồng mới và nhóm tối đa 10 giữ nguyên.

- Tiếp tục kho theo yêu cầu Bruce ngày 25/10: quyền riêng lưu trong `phases/operator-stock-resume-approval.json`, `operator-reservation-release-approval.json`, `operator-receipt-resume-approval.json`. Quyền phiếu nhập chỉ validate PO đã confirmed, không confirm thêm PO hoặc tạo Bill. Ưu tiên nguồn nhập trước MO/DO phụ thuộc; hoàn tất nhóm đang chạy trước khi bàn giao.
- [resume_pysb_stock_phase.py](resume_pysb_stock_phase.py), [run_pysb_stock_only_queue.py](run_pysb_stock_only_queue.py) — controller kho dùng writer chuẩn dưới khóa production và token gắn PID; mẫu theo luồng, nhóm tối đa 10, đọc lại sau ghi, dừng khi lỗi hoặc thiếu phản hồi. Không chạy writer cũ trực tiếp để vượt phase guard. `--refresh-target` chỉ đọc và lưu bản trước, không thay snapshot nguồn.
- [stock_confirmation_handoff.py](stock_confirmation_handoff.py) — hợp nhất định danh liên quan kho từ bàn giao SO đã nghiệm thu; chặn xung đột, không nhập ánh xạ đơn vị PC toàn cục hoặc user vào kho. SO đã sale/done tái sử dụng native picking/move, không gọi confirm lại.
- [scoped_delivery_reservations.py](scoped_delivery_reservations.py) — chỉ theo quyền riêng của Bruce: gỡ giữ chỗ xung đột của phiếu do đợt confirm SO này vừa tạo, toàn bộ chưa picked/done; kiểm tra nguồn gốc từ nhật ký và tồn vật lý trước/sau không đổi. Không áp dụng cho phiếu ngoài nhật ký hoặc thiếu hàng thực.
- Nếu cùng lot có cả phiếu cũ ngoài phạm vi, bộ gỡ giữ chỗ giữ nguyên các phiếu đó và chỉ xử lý phần có quyền; vẫn phải kiểm tra đủ tồn/giữ chỗ trước validate. [prepared_delivery_readback.py](prepared_delivery_readback.py) đọc lại nguồn, chuỗi native, chi tiết và nhật ký trước tiếp tục phần đã chuẩn bị; chặn mọi lần validate chưa được kiểm chứng, không retry. [reopen_confirmed_delivery_hold.py](reopen_confirmed_delivery_hold.py) chỉ mở giữ chờ phê duyệt cũ khi bước SO đã xác minh confirmed, native chưa picked/done; không gọi confirm lại.
- [report_pysb_stock_resume.py](report_pysb_stock_resume.py) — chỉ đọc hồ sơ local, cập nhật `BAO_CAO_TIEP_TUC_KHO.md` và `phases/stock-resume-report.json` sau nhóm; phân biệt số mới trong lượt với tổng đã kiểm chứng. Báo cáo coverage có thời điểm riêng và phải quét lại sau lượt ghi cuối để nghiệm thu.
- Điều tra đầu kỳ ngày 26/10: [prepare_pysb_opening_review.py](prepare_pysb_opening_review.py), [inspect_pysb_july31_opening_dependencies.py](inspect_pysb_july31_opening_dependencies.py), [inspect_pysb_opening_adjustment_provenance.py](inspect_pysb_opening_adjustment_provenance.py), [prepare_pysb_temporary_opening_review.py](prepare_pysb_temporary_opening_review.py), [preflight_pysb_safe_temporary_offsets.py](preflight_pysb_safe_temporary_offsets.py) — chỉ đọc/offline; xác định tồn tạm cũ và lập đề xuất, không cấp quyền đối ứng. Thấy tag tồn tạm chưa đủ để sửa tồn; phải chứng minh delta đúng từng khóa và đọc ledger live. Ba trường hợp không âm có phương án riêng `PHUONG_AN_3_DOI_UNG_TON_TAM.md`; cần Operator duyệt vì ngoài kỳ. Các trường hợp âm hoặc đang giữ chỗ không được tự mở rộng theo ba mẫu.
- [inspect_pysb_delivery_reservations.py](inspect_pysb_delivery_reservations.py), [inspect_pysb_free_delivery_candidates.py](inspect_pysb_free_delivery_candidates.py) — chỉ đọc chi tiết giữ chỗ và tồn khả dụng đúng lot/vị trí. Không dùng kết quả local cũ thay kiểm tra live trước validate.

- [run_pysb_phased_migration.py](run_pysb_phased_migration.py) — Điều khiển theo pha, hiện mới mở adapter xác nhận PO và Verify PO. `--recordset` gọi public `button_confirm` cho nhiều PO; mẫu 2 PO trước nhóm tối đa 25. Các adapter SO/kho/kế toán chưa triển khai đầy đủ, không coi các mode được khai báo là đã có writer. Bruce đã yêu cầu dừng sau PO; xem `operator-stop-after-confirm-po.json` và báo cáo trong hồ sơ production.
- [confirm_pysb_prod_orders.py](confirm_pysb_prod_orders.py), [production_operation_log.py](production_operation_log.py), [production_phase_guard.py](production_phase_guard.py) — Xác nhận PO, nhật ký JSONL fsync và chặn writer cũ. Không validate receipt, sửa master hoặc tạo bill. Phục hồi mẫu nguồn 5275 chỉ sau readback chứng minh đã commit; không dùng như retry chung.
- [approved_order_currency_mapping.py](approved_order_currency_mapping.py) — Tái sử dụng ánh xạ CNH → CNY đã chọn trong migration; kiểm chứng metadata/rounding trực tiếp, không sửa currency hoặc tỷ giá. Ánh xạ master gốc vẫn được giữ nguyên; bằng chứng overlay nằm trong `phases/order-currency-map-evidence.json`.
- [inspect_pysb_po_workflow_holds.py](inspect_pysb_po_workflow_holds.py) — Chỉ đọc điều kiện supplier của PO chờ; phân biệt native có thể thêm supplier khi chưa đăng ký và số supplier ≤10 với nhóm >10 không tự thêm. Việc mở lại workflow hold chỉ áp dụng PO chưa có mutation intent, có lịch sử và bằng chứng đọc lại.
- [verify_pysb_phase_orders.py](verify_pysb_phase_orders.py), [render_pysb_po_confirmation_report.py](render_pysb_po_confirmation_report.py) — Đối chiếu toàn tập PO, đóng gate có ngoại lệ và xuất `BAO_CAO_CONFIRM_PO_VA_DIEM_DUNG.md`. Đợt 25/10: 67 PO xác nhận mới; 166/206 đạt bước PO, 40 cần xử lý ngoại lệ, không còn PO đủ điều kiện chưa xử lý. Đã dừng, không nghiệm thu kho/kế toán.
- [inspect_pysb_order_confirmation_actions.py](inspect_pysb_order_confirmation_actions.py) — Chỉ đọc định nghĩa action; đã chứng minh action Confirm RFQ trên v19 gọi `records.button_confirm()`. Không thực thi server action.
- [production_rpc_metrics.py](production_rpc_metrics.py) — Đo thời gian, số lượng và kích thước kết quả RPC, không lưu payload/credentials. Baseline M0 là lượt đọc, chưa phải baseline thông lượng xác nhận tương đương để công bố hệ số tăng tốc.

- check_pysb_aug_oct_coverage.py --source-only — Chỉ quét nguồn và so snapshot, gồm lượng, ngày, chi tiết và liên kết SO/PO/MO/trả hàng; không đọc/ghi đích hoặc ghi đè ánh xạ. Dùng được trong lúc writer đích hoạt động. Verify SO/PO cuối đợt cũng liệt kê riêng chứng từ không thuộc snapshot dù ngày chứng từ vẫn trong kỳ.

- [same_factor_unit_alias.py](same_factor_unit_alias.py) — Chứng minh hai đơn vị v19 cùng gốc, cùng factor và cùng độ chính xác; chỉ tỷ lệ 1:1. Kiểm kê chỉ dùng đúng move trong inventory-unit-alias-validation.json đã xác minh live; kiểm tra lại metadata trước ghi. Giữ nguyên master và ánh xạ chung, lưu proof theo từng move; luồng alias lấy mẫu riêng. Đối chiếu tồn công ty giữ độ chính xác nguồn, không dùng đơn vị tương đương để che chênh lượng.
- [delivery_lot_matching.py](delivery_lot_matching.py) — Nếu tìm tên lot không trả bản ghi, quét đủ lot đúng sản phẩm/công ty rồi so tên chính xác và ID đã ánh xạ. Chặn trùng tên hoặc xung đột ID, không đổi/tạo lot khi đã có bản ghi đúng. --resume-unvalidated của DO chỉ tiếp tục chuỗi có nhật ký, chưa picked/tiêu hao/chưa từng validate và không có liên kết ngoài chuỗi.

- [audit_pysb_inventory_rounding.py](audit_pysb_inventory_rounding.py) — Chỉ đọc Odoo, đối chiếu hai dòng kiểm kê thuộc đúng 22 dòng được duyệt. --record-evidence chỉ bổ sung delta vào nhật ký local sau khi nguồn và đích khớp bằng chứng; không ghi lại tồn. inspect_pysb_inventory_adjustments.py --refresh-target-lots-only chỉ làm mới candidate lot đích, giữ nguyên snapshot nguồn.

- [run_pysb_independent_work_queue.py](run_pysb_independent_work_queue.py) — Điều phối tuần tự kiểm kê → MO → DO → kế toán bằng writer chuẩn; quét và lập lại preflight giữa các lượt. DO tối đa 10 SO/lượt, luồng mới vẫn lấy mẫu theo writer. Lỗi, thao tác chưa rõ phản hồi hoặc chuỗi chưa hoàn tất đều dừng; không tự thử lại. Nhóm được giữ chờ tính riêng khỏi số hoàn tất. Không tạo quyền ghi hay phạm vi mới.
- [inspect_pysb_return_origins.py](inspect_pysb_return_origins.py) — Chỉ đọc chứng từ gốc của trả hàng còn chờ, gồm move ngoài kỳ và XMLID đích. Không tạo/sửa chứng từ ngoài kỳ; có XMLID chưa chứng minh đã chuyển.

- [historical_expiry_confirmation_guard.py](historical_expiry_confirmation_guard.py) — Chỉ xác nhận wizard hết hạn theo quyền Operator và danh sách MO nguồn đã chốt; kiểm tra đúng lot, MO chưa tiêu hao, giữ nguyên metadata hạn lot. Không bỏ qua các wizard khác.
- [inspect_pysb_inventory_adjustments.py](inspect_pysb_inventory_adjustments.py), [inventory_count_checks.py](inventory_count_checks.py), [prepare_pysb_inventory_adjustments.py](prepare_pysb_inventory_adjustments.py) — Đọc chứng từ và dòng kiểm kê thật; chỉ lập nhóm đầy đủ có delta nguồn được chứng minh, tồn đầu kỳ và ánh xạ hợp lệ. Không tạo tồn hỗ trợ.
- [migrate_pysb_inventory_adjustments.py](migrate_pysb_inventory_adjustments.py) — Quy trình kiểm kê native: nhập tồn hiện tại cộng delta lịch sử; không ghi trực tiếp quant.quantity. Mỗi luồng lấy mẫu trước nhóm. Nếu mất phản hồi, dừng; --recover-applied GROUP chỉ hoàn tất ánh xạ/ngày sau khi đọc lại chứng minh đã áp dụng đúng một lần, tuyệt đối không áp dụng lại delta. Nhật ký kiểm kê được hợp nhất vào Verify và xét nguồn tồn. --finish-applied chỉ hoàn tất đối chiếu phiếu đã áp dụng có phản hồi; --resume-staged chỉ được dùng khi nhật ký chưa có lệnh áp dụng và đọc lại chứng minh tồn chưa đổi, đầu vào kiểm kê vẫn đúng. Không dùng các mode này để thử lại lệnh chưa rõ kết quả.

- [approved_mo_demand_rounding.py](approved_mo_demand_rounding.py) — Chỉ áp dụng demand nguyên liệu đúng 13 MO và từng move trong hồ sơ Operator đã duyệt; kiểm tra giá trị nguồn, đơn vị, độ chính xác. Không đổi product_qty hoặc qty_producing. Phê duyệt lưu tại `operator-mo-demand-rounding-approval.json`.
- [run_pysb_independent_mo_queue.py](run_pysb_independent_mo_queue.py) — Điều phối writer MO hiện có qua các lượt đã lấy mẫu; chỉ đi tiếp khi có tiến độ verified_done, dừng ngay khi writer lỗi hoặc có thao tác chưa rõ phản hồi. Không tự thử lại lỗi.
- [unconsumed_mo_recovery_guard.py](unconsumed_mo_recovery_guard.py) — `migrate_pysb_independent_mos.py --recover-unconsumed ID` chỉ phục hồi MO đã tạo có nhật ký, nguồn chưa đổi, chưa picked/tiêu hao và chưa từng gọi mark_done. Phải đọc lại trước; không dùng để thử lại một lần tiêu hao chưa rõ kết quả.
- [native_mo_placeholder_matching.py](native_mo_placeholder_matching.py) — Với MO vừa tạo của đợt này, chỉ gắn các move cùng vai trò/sản phẩm/đơn vị/vị trí/demand, chưa picked và không có liên kết cung ứng/trả hàng. Lot và chi tiết lịch sử được gắn rồi kiểm chứng riêng. Không áp dụng cho move đã dùng hoặc master không rõ danh tính.
- [inspect_pysb_hq_mts_routes.py](inspect_pysb_hq_mts_routes.py), [hq_mts_delivery_proof.py](hq_mts_delivery_proof.py) — Chỉ đọc bằng chứng quy tắc giao HQ: rule khách duy nhất là pull từ Stock theo make_to_stock; Manufacture vào Stock không phải rule tại vị trí khách. Chỉ nhóm warehouse1, route sản phẩm/category4–5 được xét thêm; native writer kiểm tra lại vị trí khách, warehouse từng dòng, route package và cấu hình trước xác nhận. Bắt buộc mẫu riêng; không đổi master/route, không bỏ guard phát sinh PO/MO ngoài dự kiến.
- [mo_approved_exception_checks.py](mo_approved_exception_checks.py) — Giữ nguyên source/target/delta và kết quả gốc; ghi riêng ngoại lệ MO chỉ khi giá trị đích đúng phê duyệt và chi tiết move đã được kiểm chứng độc lập. Sai liên kết, ngày hoặc chiều dữ liệu vẫn chặn.
- [migrate_pysb_independent_deliveries.py](migrate_pysb_independent_deliveries.py) — Chuỗi giao hàng SO đã khớp, tái sử dụng move native, kiểm tra phê duyệt SO và chuỗi Pick/Pack/Delivery; không vượt phê duyệt thiếu hoặc gọi carrier.
- [production_workflow_rpc.py](production_workflow_rpc.py) — Ngữ cảnh ghi production dùng active_test=True để quy trình native chọn quy tắc đang hoạt động; đọc đối chiếu vẫn giữ bản ghi archive.
- [production_write_lock.py](production_write_lock.py) — Khóa hệ điều hành ngăn hai writer của đợt này chạy đồng thời.
- [inspect_pysb_company_balances.py](inspect_pysb_company_balances.py) — Chỉ đọc toàn bộ quant công ty và move line done từ đầu kỳ, dựng tồn chi tiết đầu kỳ, cuối tháng 8, cuối tháng 9 và mốc chụp tháng 10. Giữ nguyên mọi khóa thiếu ánh xạ, so theo đơn vị từng sản phẩm; lấy khóa writer trong lúc chụp để tránh đợt này tự thay đổi số liệu.
- [prepare_pysb_mo_precision_review.py](prepare_pysb_mo_precision_review.py) — Chỉ lập đề xuất local. Không chạy lại để thay thế danh sách phê duyệt đã chốt.
- [check_pysb_aug_oct_coverage.py](check_pysb_aug_oct_coverage.py) — Thêm `--rescan-source` để quét lại toàn bộ move/chi tiết nguồn trong kỳ, giữ snapshot gốc và báo chứng từ mới hoặc thay đổi riêng.

- [migrate_pysb_independent_receipts.py](migrate_pysb_independent_receipts.py) — Ghi theo mode sample/batch: chỉ chuỗi nhập PO tự cung ứng đã qua preflight; tái sử dụng phiếu native, nhật ký trước/sau, đọc lại lượng/ngày/lot và PO received. Giữ nhóm tách/gộp phiếu hoặc master chưa khớp. Không dùng để chạy DO/MO.
- [prepare_pysb_independent_invoices.py](prepare_pysb_independent_invoices.py) — Chỉ đọc và lập manifest; chặn sai ánh xạ, phụ thuộc kho chưa sẵn sàng, sai tiền/tỷ giá và nguồn đã đổi.
- [migrate_pysb_independent_invoices.py](migrate_pysb_independent_invoices.py) — Ghi nháp rồi post sau kiểm tra; dùng sequence v19, giữ tham chiếu v14. Credit Note gắn chứng từ gốc sau post để không kích hoạt đối soát tự động. Không tạo thanh toán, đối soát hoặc gửi E-Invoice.
- [inspect_pysb_receipt_execution_holds.py](inspect_pysb_receipt_execution_holds.py) — Chỉ đọc nguyên nhân PO chờ, kiểm chứng đơn vị tương đương; không tự bỏ trạng thái chờ.
- [inspect_pysb_detailed_opening.py](inspect_pysb_detailed_opening.py) — Chỉ đọc tồn đầu kỳ chi tiết theo vị trí/lot/kiện/chủ sở hữu, đảo các dòng done từ đầu kỳ trên quant hiện tại; yêu cầu hai lần đọc quant ổn định. Chỉ bao phủ sản phẩm đã ánh xạ trong snapshot, chưa phải nghiệm thu toàn công ty.
- [resolve_pysb_opening_lots.py](resolve_pysb_opening_lots.py) — Chỉ đọc lot tồn đầu kỳ; đối chiếu chính xác công ty + sản phẩm đã ánh xạ + tên lot duy nhất, giữ các trường hợp không tìm thấy/xung đột. Sau đó `inspect_pysb_detailed_opening.py --reuse-snapshots` đối chiếu lại từ snapshot ổn định, không gọi lại Odoo.
- [inspect_pysb_aug_oct_mo_execution.py](inspect_pysb_aug_oct_mo_execution.py) — Chỉ đọc thêm phụ thuộc thực thi MO và so với nguồn đã chốt.
- [prepare_pysb_independent_mos.py](prepare_pysb_independent_mos.py) — Kế hoạch local bảo thủ: chỉ cộng nguồn đã kiểm chứng, trừ mọi tiêu hao nguồn kể cả DO chưa chuyển. MO được đề xuất chưa phải MO đã chuyển; thực thi phải theo thứ tự và kiểm tra tồn thực tế.
- [migrate_pysb_independent_mos.py](migrate_pysb_independent_mos.py) — Sample trước batch, dùng native MO không BOM, nguyên liệu/thành phẩm chính xác; thành phẩm chính chưa picked trước mark done. MO bị gián đoạn phải đọc lại, không tự tiêu hao lần hai. Không tự xử lý wizard bất ngờ.
- [check_pysb_aug_oct_coverage.py](check_pysb_aug_oct_coverage.py) — `--after-run` hợp nhất ánh xạ nhật ký có kiểm tra xung đột và đọc lại move; lưu báo cáo mới, giữ nguyên baseline. Một ánh xạ có ID chưa chứng minh đã chuyển thành công.

Các công cụ trên khóa đúng hai database và hồ sơ `outputs/pysb-aug-oct-prod-20261024`; không tự dùng cho đợt khác. Không chạy post hóa đơn đồng thời với bước kho vì bước kho kiểm tra số hóa đơn không đổi.

Tiếp nối xử lý sự cố 16/10: script `repair_pysb_invoice_fx_salesperson_20261016.py` có mode `--apply-fx-outside-july`, chỉ chọn đúng 9 ID nguồn tháng 8–9 từ hồ sơ đã xác minh trước đó. Mode này đã chạy đủ 9/9; journal riêng `fx-outside-july-journal.json` được giữ và chặn ghi lặp. Mặc định chỉ đọc để xác minh lại toàn tập.

- [repair_pysb_invoice_fx_salesperson_20261016.py](repair_pysb_invoice_fx_salesperson_20261016.py) — **Riêng sự cố 16/10, v19 staging**: mặc định chỉ đọc/preflight; `--apply-salesperson` sửa 17 Invoice, Warehouse → Siti và kiểm tra SO; `--apply-fx` sửa 9 Bill tháng 7 theo tỷ giá nguồn bằng ORM, giữ posted. Đã thực thi; có journal thì chặn chạy lại mode ghi. Hồ sơ `outputs/pysb-sue-invoice-review-20261016/fx-salesperson-repair/`.

- [test_confirm_pysb_july_po_staging.py](test_confirm_pysb_july_po_staging.py) — Offline safety regression tests; never connects to Odoo.
- [test_confirm_pysb_july_so_staging.py](test_confirm_pysb_july_so_staging.py) — Offline checks for SO batch confirmation invariants.

- [tests/test_stock_coverage.py](tests/test_stock_coverage.py) — Kiểm thử offline bộ lọc và kiểm chứng bao phủ DO/MO; hồi quy 17 scrap và ba move PTC013WS từ bằng chứng local khi có.


### Ti?p t?c DO c? l??ng n?i b? kh?c l??ng giao kh?ch

- [delivery_stage_demand.py](delivery_stage_demand.py) ? Nh?n di?n l??ng th?c hi?n t?ng ch?ng kh?c ch?ng giao kh?ch; b?t bu?c m?u ri?ng tr??c nh?m. Writer ch? ?i?u ch?nh demand c?a move native ch?a th?c hi?n theo ??ng ch?ng ngu?n, gi? l??ng th??ng m?i SO.
- [delivery_preparation_cleanup_guard.py](delivery_preparation_cleanup_guard.py) v? [recover_pysb_delivery_duplicate_preparation.py](recover_pysb_delivery_duplicate_preparation.py) ? **Ri?ng SO ngu?n 63698**: m?c ??nh ch? ??c; ?? x?c minh v? g? move 20408 do ch?nh l??t chu?n b? t?o, ch?a th?c hi?n, kh?ng c? chi ti?t hay ?nh x?. Kh?ng ch?y nh? c?ng c? d?n chung. Ch?ng c? n?m trong h? s? production th?ng 8?10.
- [migrate_pysb_independent_deliveries.py](migrate_pysb_independent_deliveries.py) ? `--source-so` ch?n m?u; `--resume-unvalidated` v? `--finish-prepared` ch? ti?p t?c tr?n chu?i ?? chu?n b? sau ki?m tra nh?t k?, l??ng, chi ti?t v? quan h?. M?u SO54300 ?? ho?n t?t 24 move, gi? 6 ? ch?ng ??u v? 3 ? ch?ng giao kh?ch theo ngu?n.

- [delivery_line_provenance.py](delivery_line_provenance.py) ? Ch?n ngay trong preflight khi m?t move n?i b? d?n t?i nhi?u d?ng SO ho?c kh?ng ch?ng minh ???c d?ng ??ch. Gi? ch? h? tr? merge/split, kh?ng t? ch?n m?t d?ng; b?ng ch?ng SO-54517: `delivery-63950-shared-internal-line-hold.json`.
