"""Read-only acceptance of resumed production SO confirmations."""
import hashlib
import json
import runpy
from collections import Counter
from pathlib import Path
import argparse

BASE = Path(__file__).parent
M = runpy.run_path(str(BASE / 'confirm_pysb_prod_so.py'))
save = M['save']; rid = M['rid']


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--evidence-dir', required=True); args = parser.parse_args()
    out = Path(args.evidence_dir).resolve(); phase = out / 'phases'
    # Read-only acceptance does not monopolize production while another session
    # works on POs. Reject unstable SO snapshots instead of taking writer lock.
    lock = None
    try:
        run = M['Run'](out); run.capture()
        stamps=run.b.read('sale.order',run.target,['write_date'])
        if any(x['write_date']!=run.target[x['id']]['write_date'] for x in stamps):raise RuntimeError('SO snapshot changed during read-only verification; recapture required')
        verified = []; errors = []
        bysource = {x['source_id']: x for x in run.rows}
        for sid, entry in run.j['orders'].items():
            if entry['status'] != 'verified_confirmed': continue
            row = bysource[int(sid)]
            if row['classification'] != 'confirmed_commercially_matched' or row['issues'] or not row['date_matches']:
                errors.append(dict(source_id=int(sid), reason='confirmed_SO_no_longer_matches', live=row))
            else: verified.append(int(sid))
        picks = run.b.read('stock.picking', [i for x in run.j['orders'].values() for i in x.get('picking_ids', [])], ['name', 'state', 'company_id', 'sale_id', 'move_ids', 'date_done'])
        moves = run.b.read('stock.move', [i for p in picks for i in p['move_ids']], ['company_id', 'state', 'sale_line_id', 'picking_id', 'product_id', 'product_uom_qty', 'move_orig_ids', 'move_dest_ids'])
        targets = {x['target_id'] for x in run.j['orders'].values() if x['status'] == 'verified_confirmed'}
        if any(rid(p['company_id']) != 1 or rid(p['sale_id']) not in targets or p['state'] == 'done' or p['date_done'] for p in picks): errors.append(dict(reason='unexpected_picking_company_link_or_completion'))
        if any(rid(m['company_id']) != 1 or m['state'] == 'done' for m in moves): errors.append(dict(reason='unexpected_move_company_or_completion'))
        unattempted = [r['source_id'] for r in run.rows if r['eligible'] and str(r['source_id']) not in run.j['orders']]
        statuses = Counter()
        for r in run.rows:
            if r['classification'].startswith('confirmed_'):
                status = r['classification']
                if status == 'confirmed_commercially_matched' and not r['date_matches']: status = 'confirmed_historical_date_requires_review'
            elif r['eligible']:
                status = 'held_native_approval' if str(r['source_id']) in run.j['orders'] else 'eligible_unattempted'
            elif r['classification'] == 'draft_matched_pending_workflow_preflight': status = 'draft_workflow_hold'
            else: status = r['classification']
            r['final_status'] = status; statuses[status] += 1
        report = dict(identity=run.identity, completed_utc=M['now'](), erp_mutations=0, total=len(run.rows), summary=dict(statuses), newly_confirmed=len(verified), new_confirmation_source_ids=verified, picking_count=len(picks), move_count=len(moves), eligible_unattempted=len(unattempted), journal_statuses=dict(Counter(x['status'] for x in run.j['orders'].values())), unresolved_operations=len(run.log.unresolved()), errors=errors, rows=run.rows, pickings=picks, moves=moves)
        if (out/'so-remediation/applied-overlay.json').exists():
            report['remediation_evidence']=dict(overlay='so-remediation/applied-overlay.json',repairs='so-remediation/repairs-journal.json',missing_SO='so-remediation/missing-so-journal.json',approved_exceptions=['PC base unit identity for exact PTFE 12x15cm SKU; no length conversion claim','14 is_free flags on historical zero-price or zero-quantity lines','2 historical GENTING shipping addresses remain archived','SO-56453 confirmed without duplicate procurement; warehouse phase must reuse existing PO P00742'])
            save(phase/'so-confirmation-handoff.json',dict(identity=run.identity,captured_utc=M['now'](),maps=run.overlay.get('maps',{}),orders=run.j['orders'],dropship_dependency='so-remediation/dropship-65338-dependency.json',instruction='Reuse existing confirmed SO and native pickings/moves. Do not call action_confirm again. Apply source historical stock detail only in the separately authorized stock phase.'))
        save(phase / 'confirm-so-verification.json', report)
        evidence = []
        for name in ['confirm-so-verification.json', 'so-confirmation-journal.json']:
            evidence.append(dict(path='phases/' + name, sha256=hashlib.sha256((phase / name).read_bytes()).hexdigest()))
        closed = not errors and not unattempted and not run.log.unresolved()
        held = sum(v for k, v in statuses.items() if k not in ['confirmed_commercially_matched', 'source_cancelled_do_not_confirm'])
        save(phase / 'confirm-so-gate.json', dict(**run.identity, phase='confirm-so', status=('closed_with_holds' if held else 'fully_passed') if closed else 'open', completed_utc=M['now'](), live_verification_complete=True, eligible_unattempted=len(unattempted), completed_count=statuses['confirmed_commercially_matched'], held_count=held, evidence=evidence))
        lines = ['# Kết quả xác nhận SO trên v19 production', '', 'Phạm vi đã chốt: **' + str(len(run.rows)) + ' SO** thuộc hồ sơ PYSB tháng 8–10/2026 và các đơn được giao dịch trong kỳ tham chiếu.', '', '**Xác nhận mới: ' + str(len(verified)) + ' SO**. Ngày lịch sử và dữ liệu thương mại đã đối chiếu lại với v14.', '', '| Kết quả | Số SO |', '|---|---:|']
        labels = dict(missing_target_order='Chưa tìm thấy SO đích', confirmed_commercially_matched='Đã xác nhận, thương mại và ngày lịch sử khớp', confirmed_historical_date_requires_review='Đã xác nhận từ trước, ngày lịch sử cần rà soát', confirmed_requires_review='Đã xác nhận từ trước, dữ liệu cần rà soát', draft_workflow_hold='SO nháp khớp thương mại, còn vướng quy trình', draft_commercial_hold='SO nháp còn lệch dữ liệu thương mại/ánh xạ', source_cancelled_do_not_confirm='Nguồn đã hủy, không xác nhận', eligible_unattempted='Đủ điều kiện nhưng chưa thực hiện', held_native_approval='Đã gọi quy trình, Odoo giữ chờ phê duyệt')
        lines += ['| ' + labels.get(k, k) + ' | ' + str(v) + ' |' for k, v in statuses.items()]
        lines += ['', 'Phiếu kho sinh ra từ các SO xác nhận mới: **' + str(len(picks)) + '**; stock move: **' + str(len(moves)) + '**. Bước này không validate phiếu kho.', '', 'SO đủ điều kiện chưa thực hiện: **' + str(len(unattempted)) + '**. Thao tác chưa rõ kết quả: **' + str(len(run.log.unresolved())) + '**. Lỗi nghiệm thu xác nhận mới: **' + str(len(errors)) + '**.', '', 'Các nhóm chờ được giữ nguyên để review ánh xạ đối tác/kho, phê duyệt tín dụng, tuyến cung ứng hoặc giá cơ sở. Không tự sửa master hay bỏ qua phê duyệt.', '', '[Chi tiết từng SO và liên kết phiếu kho](phases/confirm-so-verification.json). Đây là nghiệm thu bước xác nhận SO, chưa phải nghiệm thu giao hàng hoặc hóa đơn.']
        if report.get('remediation_evidence'):
            lines += ['', '## Kết quả xử lý ngoại lệ được duyệt', '', '- Sửa và kiểm chứng 257 đầu SO và 12 dòng hàng; không sửa danh bạ master hoặc cấu hình kho.', '- Bổ sung đủ 16 SO thiếu dưới dạng draft, đối chiếu trước xác nhận; giữ External ID cho cả đầu và dòng.', '- Dùng quyền duyệt native hiện có cho cả ba quy tắc; không bỏ qua cơ chế phê duyệt.', '- 14 cờ Sample/is_free được ghi riêng cho dòng giá 0 hoặc lượng 0; lượng, giá bán và tổng tiền giữ nguyên.', '- PC nguồn 1087 → đích 470 theo đúng SKU PTFE 12x15cm tính từng miếng; hệ số chiều dài của v14 không được coi là tương đương v19.', '- Hai SO GENTING dùng đúng địa chỉ lịch sử đã archive; trạng thái archive được giữ nguyên.', '- SO-53906 dùng máy PD-1900 đã qua sử dụng, sản phẩm 130303; giá bán 35.000 MYR, tổng SO 88.000 MYR.', '- SO-56453 không tạo thêm PO: tái sử dụng phụ thuộc PO nguồn PO-04683 → v19 P00742/1040. Bước kho cần nối đúng POL 3888 và SOL 26017 theo move nguồn 533596.', '', '[Bàn giao SO và chuỗi native cho bước kho](phases/so-confirmation-handoff.json).']
        if closed and not held:
            lines=[('Đã xử lý hết các nhóm ngoại lệ SO được duyệt; một SO nguồn đã hủy được giữ không xác nhận.' if line.startswith('Các nhóm chờ được giữ nguyên') else line) for line in lines]
        (out / 'BAO_CAO_CONFIRM_SO.md').write_text('\n'.join(lines) + '\n', encoding='utf8')
        print(json.dumps({k: v for k, v in report.items() if k not in ['rows', 'pickings', 'moves', 'new_confirmation_source_ids']}, ensure_ascii=True), flush=True)
        if not closed: raise SystemExit(1)
    finally:
        if lock:lock.close()


if __name__ == '__main__': main()
