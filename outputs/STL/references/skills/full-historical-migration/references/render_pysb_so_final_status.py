"""Offline UTF-8 final SO status; never connects to Odoo."""
import json
from pathlib import Path
BASE=Path(__file__).parent
ROOT=BASE.parents[5]
OUT=ROOT/'outputs/pysb-aug-oct-prod-20261024'

def replace_last_section(path,predicate,new_section):
    if not path.exists():return
    text=path.read_text(encoding='utf8');offset=0;found=None
    for line in text.splitlines(keepends=True):
        if predicate(line.strip()):found=offset
        offset+=len(line)
    if found is not None:text=text[:found].rstrip()
    path.write_text(text+'\n\n'+new_section.strip()+'\n',encoding='utf8')

def main():
    r=json.loads((OUT/'phases/confirm-so-verification.json').read_text(encoding='utf8'))
    if r['errors'] or r['eligible_unattempted'] or r['unresolved_operations']:raise RuntimeError('SO acceptance incomplete')
    summary='''# Xác nhận SO đã hoàn tất — v14 prod → v19 prod

Nghiệm thu ngày 25/10/2026, cùng công ty PAO YEANG SDN BHD. Phạm vi nguồn cố định của hồ sơ production tháng 8–10/2026 và các SO cũ có giao dịch được phạm vi này tham chiếu.

- Tổng phạm vi: **2.592 SO**; **2.591 confirmed và khớp thương mại/ngày lịch sử**; **1 nguồn hủy**, không confirm.
- Xác nhận mới từ đầu công việc này: **2.276 SO**; 315 SO đã xác nhận từ trước đã được đối chiếu lại, gồm 7 ngoại lệ cũ nay đã xử lý.
- Bổ sung đủ **16 SO thiếu**, đối chiếu draft trước confirm, giữ External ID đầu và dòng.
- Sửa/kiểm chứng **257 đầu đơn và 12 dòng hàng**. Không sửa master contact hoặc cấu hình kho.
- Các SO xác nhận mới sinh **2.304 phiếu kho**, **5.598 stock move**; chưa validate kho trong bước này.
- Không còn SO đủ điều kiện chưa xử lý, nhóm SO giữ chờ, lỗi nghiệm thu hoặc RPC chưa rõ kết quả. Gate SO: **fully_passed**.
- 252 kiểm thử offline đạt. Khóa writer đã nhả và các pha ghi đã tắt.

Ngoại lệ được duyệt vẫn ghi riêng: 14 cờ Sample trên dòng giá 0/lượng 0; PC theo đúng SKU PTFE tính từng miếng; hai địa chỉ lịch sử GENTING vẫn archive. PD-1900 đúng sản phẩm 130303, giá 35.000 MYR và tổng SO 88.000 MYR. SO dropship 65338 tái sử dụng phụ thuộc PO 1040/P00742, không tạo PO mua trùng; bước kho sẽ nối đúng POL 3888 và SOL 26017.

[Báo cáo xác nhận SO](BAO_CAO_CONFIRM_SO.md). [Đối chiếu toàn phạm vi](phases/confirm-so-verification.json). [Bàn giao SO/chuỗi native](phases/so-confirmation-handoff.json).

Đây là nghiệm thu bước xác nhận SO; chưa nghiệm thu giao hàng, hóa đơn hoặc migration toàn công ty.
'''
    (OUT/'TIEN_DO_SO_BO_SUNG.md').write_text(summary,encoding='utf8')
    po=json.loads((OUT/'phases/confirm-po-gate.json').read_text(encoding='utf8'))
    (OUT/'TIEN_DO_THEO_PHA.md').write_text(summary+f"\nTheo gate PO hiện lưu: {po['completed_count']} PO đạt, {po['held_count']} chờ. SO đã đóng fully_passed; chưa chạy tiếp kho/kế toán trong lượt SO này.\n",encoding='utf8')
    addition='''## Kết quả cuối bước SO ngày 25/10/2026

M3 đã đóng **fully_passed**: rà đủ 2.592 SO; 2.591 confirmed khớp thương mại/ngày lịch sử và 1 nguồn hủy không confirm. Tổng xác nhận mới 2.276 SO, gồm 16 SO bổ sung được Bruce cho phép. Đã sửa 257 đầu đơn và 12 dòng; không sửa master contact/cấu hình kho. 7 SO confirmed cần rà trước đó đã hết lỗi. Không còn SO đủ điều kiện chưa thực hiện, giữ chờ hay RPC chưa rõ kết quả. 252 test offline đạt.

Chuỗi mới: 2.304 picking và 5.598 move chưa validate. Bàn giao EVIDENCE/phases/so-confirmation-handoff.json và EVIDENCE/so-remediation/applied-overlay.json; writer kho phải đọc ánh xạ này và tái sử dụng chuỗi, không confirm SO lại. SO dropship nguồn 65338/đích 9481 đã confirm với cơ chế skip_procurement native vì PO nguồn 5581/đích 1040 đã có; bước kho tái sử dụng POL 3888 và SOL 26017 theo move nguồn 533596.

Ngoại lệ được ghi rõ: 14 cờ Sample cho dòng giá 0/lượng 0, PC theo SKU PTFE 12x15cm tính miếng, hai địa chỉ GENTING archive giữ archive. Khi sửa PD-1900, native compute đã đổi giá thành 1; đã đọc lại, khôi phục giá 35.000 MYR/mô tả lịch sử và kiểm chứng SO tổng 88.000 MYR trước khi confirm. Nhật ký phục hồi riêng được giữ.

Theo yêu cầu nhường production cho session khác: các lượt đọc bổ sung/đối chiếu cuối không giữ khóa; ghi theo record/nhóm ngắn và nhả giữa lượt. Windows reader từng chặn atomic rename local; đã dùng tên file tạm riêng và thử lại riêng thao tác lưu file, không thử lại ERP RPC. Nhật ký được tối ưu bằng kiểm tra signature file khi giữ khóa; vẫn full checksum replay khi handoff/checkpoint, có hồi quy chống sửa ngoài luồng. Cuối lượt khóa đã nhả và các pha ghi tắt. M4–M6 chưa thực hiện trong lượt SO này; chưa nghiệm thu migration toàn đợt.

Báo cáo hiện hành: EVIDENCE/BAO_CAO_CONFIRM_SO.md. Các đoạn tiến độ SO trước đây là lịch sử.
'''
    for path in [ROOT/'.agents/long-workflow/EXECPLAN_PYSB_TIEP_TUC_THEO_PHA.md',OUT/'EXECPLAN_PYSB_TIEP_TUC_THEO_PHA.md']:
        replace_last_section(path,lambda line:line.startswith('## K') and 'SO' in line and '25/10/2026' in line,addition)
    replace_last_section(OUT/'CAC_VAN_DE_CAN_XU_LY.md',lambda line:line.startswith('## Ch') and 'SO 25/10/2026' in line,'''## Chốt ngoại lệ SO 25/10/2026

Đã xử lý hết các nhóm SO đã duyệt: 2.591 confirmed khớp, 1 nguồn hủy không confirm; không còn ngoại lệ SO giữ chờ. 16 SO thiếu đã bổ sung, 7 confirmed cũ đã xử lý. Các mục SO cũ phía trên là lịch sử. Bước kho cần dùng [bàn giao SO](phases/so-confirmation-handoff.json), gồm ánh xạ bổ sung và trường hợp dropship tái sử dụng PO 1040. [Báo cáo SO hiện hành](BAO_CAO_CONFIRM_SO.md).
''')
    print('Final UTF-8 SO status and ExecPlan updated offline')

if __name__=='__main__':main()
