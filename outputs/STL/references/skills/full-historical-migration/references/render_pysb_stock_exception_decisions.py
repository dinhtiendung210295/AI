"""Xuất quyết định lịch sử DO/MO từ trao đổi và hồ sơ local; không kết nối Odoo."""
import json
from pathlib import Path
from html import escape

OUT = Path('outputs/pysb-stock-migration-20261012')
rows = []
def add(topic, issue, decision, result, evidence, quote=''):
    rows.append(dict(id=f'KHO-{len(rows)+1:02}', topic=topic, issue=issue,
                     decision=decision, user_quote=quote, result=result, evidence=evidence))

add('Phạm vi phiếu kho', '72 phiếu liên quan SO/PO tháng 7 hoàn tất vào tháng 8–9.',
    'Chuyển toàn bộ phiếu liên quan, không giới hạn ngày hoàn tất trong tháng 7.',
    'Nhóm nguồn done đã chuyển: 3.028 phiếu; không validate các phiếu nguồn chưa done hoặc đã hủy.',
    'stock-next-step-handoff.json', 'Toàn bộ phiếu liên quan SO/PO tháng 7, kể cả tháng 8–9')
add('MO thay Repack Order', 'Không có Repack Order done tháng 7; nguồn có 516 MO.',
    'Ban đầu yêu cầu chờ hỏi nghiệp vụ; sau phản hồi PYSB, cho phép chuyển MO tháng 7.',
    '516/516 MO hoàn tất. Vấn đề cost/packing ratio được để xử lý riêng.',
    'stock-next-step-handoff.json', 'tiến hành đi')
add('Reference No của MO', '371 MO có Reference No nhưng ban đầu v19 thiếu trường tương ứng.',
    'Bruce bổ sung x_studio_reference_no; dùng trường này thay đề xuất lưu vào Source/origin.',
    'Giữ Reference No trong trường mới, tên MO theo nguồn.',
    'execution-journal.json', 'tôi đã bổ sung giúp bạn rồi đó: x_studio_reference_no')
add('Độ chính xác số lượng', '7 dòng MO có lượng 0,972 hoặc 3,33333; v19 cấu hình 2 chữ số và UOM 0,01.',
    'Không nâng Decimal Accuracy hoặc đổi rounding kg/M-L/ROLL; vẫn hoàn tất MO với cấu hình hiện tại.',
    'MO hoàn tất; 7 dòng chênh nhỏ được phân loại riêng trong nghiệm thu.',
    'closing-adjusted-reconciliation.json', 'giữ cầu hình và vẫn hoàn tất các MO này')
add('Tiêu chí nghiệm thu', 'v14 dùng AVCO, v19 dùng FIFO nên định giá không nhất thiết khớp.',
    'Chỉ so số lượng và lot/serial; không yêu cầu định giá khớp.',
    'Báo cáo cuối kỳ so lượng theo sản phẩm, lot/serial và vị trí.',
    'closing-adjusted-reconciliation.json', 'bạn chị cần so sánh số lượng, lot thôi nhé')
add('Thiếu điều chỉnh tồn thực', 'HQ/MO/24396 cần 20,856 M-L; nguồn có điều chỉnh +23,056 M-L ngày 28/07 ngoài phạm vi ban đầu.',
    'Tái hiện điều chỉnh tồn nguồn trên v19 và tiếp tục MO.',
    'Đã chuyển các điều chỉnh tồn thực theo bằng chứng; MO thuộc nhóm 516 hoàn tất.',
    'supplementary-adjustment-results.json', 'v19 cần có sự điều chỉnh tồn tương tự')
add('Kiện tồn đầu kỳ', 'HQ/PICK/55657 cần 10 PACK trong kiện cụ thể; v19 có tổng tồn nhưng không gắn đúng kiện.',
    'Sửa tồn đầu kỳ cho toàn bộ sản phẩm chưa có kiện để khớp v14.',
    'Đã sửa theo bằng chứng và nhật ký; giữ tổng lượng khi chỉ sửa phân bổ kiện.',
    'opening-package-correction-report.json', 'hãy sửa tồn đầu kỳ cho tất cả sp đầu kỳ chưa có kiện trên v19 sao cho khớp v14')
add('Nguồn xuất âm', 'Ví dụ ED100, lot F-AK-DP038A2025-8-11, nguồn xuất khi tồn lot không đủ.',
    'Cho phép điều chỉnh tạm trên v19, ghi kỹ reference và chứng từ nguồn; tiếp tục cho các trường hợp nguồn âm đã chứng minh.',
    'Các khoản tạm được lưu riêng; không coi là nhập tồn thực từ v14 và không che chênh lệch.',
    'temporary-negative-stock-report.json', 'những trường hợp này trên v19 hãy làm điều chỉnh đê tạm có tồn, nhưng cần phải note refence kĩ trong record điều chỉnh')
add('PO cũ nhập muộn', 'Thiếu receipt của PO-04349 tháng 6 và PO-04217 tháng 3, cùng các PO cũ khác.',
    'Tạo phiếu nhập lẻ nếu chưa có; rà tất cả PO trước 01/07 có receipt done từ 01/07 trở đi, không giới hạn ngày cuối tới dữ liệu nguồn hiện tại.',
    'Đã xử lý 43 PO cũ, 308 move nguồn và 125 phiếu lẻ; tránh tạo trùng, giữ ngày nguồn.',
    'standalone-source-receipts-result.json', 'Không giới hạn, đến dữ liệu nguồn hiện tại')
add('Software serial số lượng 2', 'HQ/IN/05919 → HQ/IN/00083: OPT-01022 dùng cùng LOT01 cho lượng 2, bị chặn vì tracking serial.',
    'Bruce tự đổi sản phẩm 130306 sang lot; xác nhận đã Save rồi yêu cầu tiếp tục.',
    'Tiếp tục receipt sau khi kiểm tra tracking lot.',
    'software-receipt-tracking-check.json', 'Lần này đã sửa trên staging và save rồi')
add('Giao dịch kho ngoài SO/PO/MO', 'Các nguồn cấp tồn còn thiếu là chuyển nội bộ, trả hàng, consignment và điều chỉnh thực.',
    'Tái hiện giao dịch tương ứng của v14 trên v19 nếu chưa có.',
    'Đã bổ sung theo nguồn; sổ bàn giao có 154 record hỗ trợ (152 verified, 2 tích hợp phạm vi gốc) và 118 điều chỉnh thực.',
    'stock-next-step-handoff.json', 'chuyển kho nội bộ, hàng trả lại, consignment và điều chỉnh tồn thực trên v14 cũng cần được làm tương tự trên v19 nếu chưa có')
add('T NO.135 không có lot', 'HQ/MO/24170 tiêu hao 10 M không ghi lot trên v14, v19 bắt buộc lot.',
    'Bruce đổi T NO.135 sản phẩm 118397 sang Track By Quantity trên staging.',
    'MO tiếp tục theo lượng, không tự đặt lot.',
    'resumed-mo-recovery-result.json', 'tôi đã giúp bạn chuyển thánh track By Quantity trên staging rồi đó')
add('Khôi phục thành phẩm MO', 'Nguyên liệu MO đã xuất nhưng thành phẩm cần xử lý lại; nguy cơ tiêu hao hai lần.',
    'Duyệt giữ nguyên nguyên liệu đã xuất 10 M và xử lý lại thành phẩm.',
    'HQ/MO/24170 và HQ/MO/24338 đều done; nhật ký giữ move nguyên liệu, không xuất lại.',
    'resumed-mo-recovery-result.json', 'ok tiến hành đi')
add('Lot/serial tồn đầu kỳ', 'HOTRONIX 201700249 thiếu 1 máy; AJ/EPSON khác serial; SG1000-CYAN và TENNETH khác tên lot.',
    'Cho phép sửa tồn đầu kỳ và ánh xạ lot/serial theo bằng chứng v14, giữ tên đã làm sạch và ghi nguồn.',
    'Nhóm đầu kỳ đã xử lý; không mặc định mọi cặp serial khác nhau đều tương đương.',
    'execution-journal.json', 'Cho phép sửa tồn đầu kỳ và ánh xạ lot/serial theo bằng chứng v14')
add('T NO.120 không có lot', '6 phiếu dùng T NO.120(65 inch), sản phẩm 118378, nguồn xuất 3 M và 1 M không ghi lot.',
    'Đổi tracking sang theo số lượng trên staging.',
    'Tiếp tục chuyển các phiếu theo lượng nguồn, không tự chọn lot.',
    'execution-journal.json', 'Đổi sang theo số lượng trên staging')
add('PTC013WS không có lot', 'Điều chỉnh SAMPLE FOR TESTING (Shin Mei) giảm 1 PC PTC013WS 400 × 600 mm không ghi lot.',
    'Đổi sản phẩm 116236 sang Track By Quantity trên staging.',
    'Đã đổi và đưa lại điều chỉnh nguồn vào lượt chuyển.',
    'new-6115-28mm-product-result.json', 'PTC013WS hãy đổi thành track by quantity trên v19 staging')
add('Thiếu SKU 6115-03SW GREY', 'Thiếu đúng bản 28 mm × 10 m; các bản 18/32/50 mm không thay thế được.',
    'Trước hết kiểm tra ngày tạo so với hai lần import 28/06 và 28/07; sau đó cho phép tạo sản phẩm mới.',
    'Nguồn tạo ngày 29/07, sau hai mốc import; đã tạo sản phẩm v19 130352, chuyển điều chỉnh +1 ROLL.',
    'new-6115-28mm-product-result.json', 'tạo sản phẩm mới đi')
add('Cấp tạm cho vòng chuyển–trả', 'NLW-902 WHITE RUBBER BINDER (5KGS), lot 20250627 thiếu lượng để chạy 4 phiếu do các xuất sau đã dùng tồn.',
    'Cấp tạm +1 rồi trừ lại đúng 1 ngay sau vòng, có reference đối ứng và ngày lịch sử.',
    'Đã chạy chuỗi; cặp cấp/trừ tạm đã đối ứng, không giữ dư khoản này.',
    'execution-journal.json', 'Cho phép cấp tạm rồi trừ lại ngay')
add('UV WHITE / PO-04604', 'Điều chỉnh ngày 10/10 phụ thuộc receipt PO-04604 ngày 24/09, PO ngoài phạm vi cũ đã duyệt.',
    'Bruce chưa duyệt nhập riêng PO-04604; sau đó yêu cầu điều chỉnh tạm trước.',
    'Cấp tạm +4 (move 17672), chạy điều chỉnh nguồn 17673–17675. Khoản tạm còn hiệu lực, thuộc tháng 10; khi chuyển receipt thực phải trừ đối ứng, tránh nhập trùng.',
    'execution-journal.json', 'hãy điều chỉnh tạm trước')
add('Cost SOL', 'Cost có thể bị tính lại khi hoàn tất kho.',
    'Tạm bỏ qua kiểm tra/cập nhật cost SOL đến khi Bruce đổi ý.',
    'Không dùng cost SOL làm tiêu chí nghiệm thu kho hiện tại.',
    'Closing_Gap_Execution_Result.md', 'tạm thời cứ bỏ qua cost SOL cho đến khi tôi thay đổi ý định')
add('Ngày tồn đầu kỳ', 'Báo cáo đầu tháng lệch vì một số tồn nhập đầu kỳ có timestamp sau mốc mở tháng.',
    'Bruce chấp nhận giải thích đầu kỳ và yêu cầu chuyển sang truy nguyên nhân cuối kỳ; bước xử lý cuối kỳ không sửa ngày tồn đầu kỳ.',
    'Giữ riêng vấn đề mốc báo cáo; không diễn giải thành mọi báo cáo đầu kỳ đều đã khớp.',
    'opening-date-mismatch-evidence.json', 'ok vậy đầu kỳ ko sao rồi, hãy kiểm tra cuối kỳ xem nguyên nhân lệch do đâu rồi đề xuất cách xử lý')
add('Giữ khoản tạm và tách báo cáo', '33 sản phẩm còn lệch tổng tồn thực do các khoản tạm đã duyệt.',
    'Giữ khoản tạm; báo cáo tồn thực, phần tạm và tồn sau loại phần tạm riêng.',
    '856/856 sản phẩm đã ánh xạ khớp sau loại tạm, ngưỡng 0,00501; tồn thực vẫn lệch ở 33 sản phẩm.',
    'closing-adjusted-reconciliation.json', 'PLEASE IMPLEMENT THIS PLAN: Xử lý chênh lệch tồn cuối tháng 7 của Pao Yeang')
add('24 phiếu xuất thiếu cuối kỳ', 'Thiếu PICK/PACK/DO của 6 SO ngoài danh sách ban đầu; SO-52939 có UTC cuối tháng 6 nhưng Malaysia là 01/07.',
    'Duyệt tạo phiếu lẻ, không tạo/sửa SO; giữ dữ liệu nguồn, ghi riêng ngoại lệ ranh giới ngày; không tự cấp tạm mới.',
    '24 phiếu hoàn tất, 39 stock move và 52 dòng chi tiết nguồn.',
    'Closing_Gap_Execution_Result.md', 'PLEASE IMPLEMENT THIS PLAN: Xử lý chênh lệch tồn cuối tháng 7 của Pao Yeang')
add('Unbuild và Scrap', 'Thiếu UB/00618, UB/00619 (4 move) và SP/00084 giảm 1 FCN-30; Unbuild không phải MO.',
    'Tái hiện đúng move của hai phía Stock–Production, không chạy lại BOM/tạo MO; dùng Scrap chuẩn.',
    'Unbuild move 17715–17718; Scrap ID 2, move 17719 hoàn tất theo nguồn.',
    'Closing_Gap_Execution_Result.md', 'PLEASE IMPLEMENT THIS PLAN: Xử lý chênh lệch tồn cuối tháng 7 của Pao Yeang')
add('Lot SG1000 khác dấu cách', 'Hai cặp SG1000 Black/Magenta khác dấu cách cuối tên lot.',
    'Kiểm tra duy nhất rồi ghi ánh xạ tương đương; giữ tên đã làm sạch trên v19.',
    'Ánh xạ đã xác minh, không đổi tên lot.',
    'Closing_Gap_Execution_Result.md', 'PLEASE IMPLEMENT THIS PLAN: Xử lý chênh lệch tồn cuối tháng 7 của Pao Yeang')
add('Serial EPSON chưa xác nhận', 'I3200-A1: v14 C551466A0606K, v19 C551466A0600K.',
    'Trong kế hoạch đã duyệt: giữ ngoại lệ chờ Bruce xác nhận serial đúng, chưa đổi tồn hoặc coi tương đương.',
    'Còn chờ xác nhận serial thực; 2 dòng báo cáo ngoại lệ. Không có quyết định chọn một serial trong lịch sử hiện có.',
    'Closing_Gap_Execution_Result.md')
add('NLB-901 lot nguồn âm', 'Nguồn lot 20251107 = −1, 20260106 = +1; v19 hai lot = 0, tổng sản phẩm khớp.',
    'Giữ ngoại lệ lot âm nguồn, không chuyển lượng giữa lot để che chênh.',
    'Còn 2 dòng phân bổ lot khác nguồn, đã giải thích; không coi là khớp từng lot.',
    'Closing_Gap_Execution_Result.md')

title = 'PYSB — Ngoại lệ DO/Transfer và MO cùng quyết định của Bruce'
intro = ('Phạm vi: Pao Yeang, v14 prod → v19 staging py19-staging-39654560, công ty ID 1. '
         'Tổng hợp ngày 14/10/2026 từ lịch sử trao đổi hiện có và hồ sơ local. DO trong báo cáo bao gồm '
         'các bước PICK/PACK/Delivery và phiếu nhập/chuyển kho hỗ trợ. Không bao gồm ngoại lệ PO/SO hoặc Invoice/Bill riêng. '
         'Đây là báo cáo lịch sử, không thực hiện ghi Odoo hoặc rà toàn bộ DO tháng 7.')
note = ('Cột lời Bruce chỉ trích phần trả lời có trong lịch sử; phần quyết định là diễn giải theo phạm vi đã duyệt. '
        'Các mục duyệt thông qua kế hoạch được ghi rõ, không giả định có câu trả lời riêng. '
        'Link chat chia sẻ không tải được trong phiên này; không coi là nguồn đã đọc. Không suy đoán thời điểm của từng quyết định.')
data = dict(title=title, generated_date='2026-10-14', scope=intro, provenance=note,
            shared_chat_url='https://chatgpt.com/s/cx_6ace17a3f3b48191996d1461e53923f0',
            shared_chat_fetch_status='failed_cache_miss', decisions=rows)
stem = 'PYSB_DO_MO_Exception_Decisions'
(OUT / (stem+'.json')).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
md = [f'# {title}', '', intro, '', note, '', f'Tổng cộng **{len(rows)} mục**.', '']
for r in rows:
    md += [f"## {r['id']} — {r['topic']}", '', f"- **Ngoại lệ:** {r['issue']}",
           f"- **Quyết định:** {r['decision']}", f"- **Kết quả / việc còn lại:** {r['result']}"]
    if r['user_quote']:
        md += [f"- **Lời Bruce:** “{r['user_quote']}”"]
    md += [f"- **Hồ sơ:** [{r['evidence']}]({r['evidence']})", '']
(OUT / (stem+'.md')).write_text('\n'.join(md), encoding='utf-8')
cards=[]
for r in rows:
    fields = ''.join(f'<p><strong>{label}:</strong> {escape(r[key])}</p>' for label,key in
                     [('Ngoại lệ','issue'),('Quyết định','decision'),('Kết quả / việc còn lại','result')])
    if r['user_quote']:
        fields += f'<blockquote>{escape(r["user_quote"])}</blockquote>'
    cards.append(f'<article><h2>{r["id"]} — {escape(r["topic"])}</h2>{fields}'
                 f'<p class="source">Hồ sơ: <a href="{escape(r["evidence"])}">{escape(r["evidence"])}</a></p></article>')
html = f'''<!doctype html><html lang="vi"><meta charset="utf-8"><title>{escape(title)}</title>
<style>body{{font:16px/1.6 Arial,sans-serif;background:#f4f7fa;color:#183047;max-width:1100px;margin:32px auto;padding:0 24px}}h1{{font-size:28px}}h2{{font-size:20px;margin-top:0}}article{{background:white;padding:20px 24px;margin:18px 0;border:1px solid #d9e3eb;border-radius:8px;break-inside:avoid}}p{{margin:8px 0}}blockquote{{border-left:3px solid #3e8eab;padding:8px 16px;margin:12px 0;background:#edf7fa}}.source{{font-size:14px}}a{{color:#11658c}}@media print{{body{{background:white;margin:0;max-width:none}}article{{border-radius:0}}}}</style>
<h1>{escape(title)}</h1><p>{escape(intro)}</p><p>{escape(note)}</p>
<p><strong>{len(rows)} mục.</strong> Còn chờ: xác nhận serial EPSON; đối ứng khoản tạm UV WHITE khi chuyển receipt thực. Lot âm NLB-901 và 7 dòng độ chính xác được giữ riêng theo kế hoạch đã duyệt.</p>
{''.join(cards)}</html>'''
(OUT / (stem+'.html')).write_text(html, encoding='utf-8')
missing = sorted({r['evidence'] for r in rows if not (OUT/r['evidence']).exists()})
assert not missing, missing
assert len({r['id'] for r in rows}) == len(rows)
print(json.dumps({'items':len(rows),'outputs':[str(OUT/(stem+x)) for x in ('.html','.md','.json')], 'missing_evidence':missing}, ensure_ascii=False))
