"""Offline business review of opening differences blocking historical stock; no writes to ERP."""
import json,runpy
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
BASE=Path(__file__).parent
I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'));OUT=I['OUT']
def load(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False
def fmt(q):return format(q,'.8f').rstrip('0').rstrip('.') or '0'
def main():
    opening=load('native-opening-comparison.json');detailed=load('detailed-opening-comparison.json')
    moves={x['id']:x for x in load('source-moves.json')};mos={x['id']:x for x in load('source-mo-execution-details.json')}
    plan=load('independent-mo-supply-plan.json');impact=defaultdict(set)
    bad={x['source_id']:x for x in opening['rows'] if not x['exact_quantity_match']}
    for row in plan['rows']:
        if 'product_mapping_or_opening_hold' not in row['errors']:continue
        mo=mos[row['source_mo']]
        for mid in mo['move_raw_ids']+mo['move_finished_ids']:
            if mid in moves and rid(moves[mid]['product_id']) in bad:impact[rid(moves[mid]['product_id'])].add(mo['name'])
    results=[]
    for sid,source in bad.items():
        keys=[x for x in detailed['rows'] if x['target_key'][0]==source['target_id'] and not x['exact_match']]
        results.append(dict(**source,affected_mos=sorted(impact[sid]),affected_mo_count=len(impact[sid]),detailed_differences=keys,decision='Chưa duyệt sửa tồn hoặc chấp nhận ngoại lệ; cần truy nguyên theo vị trí/lot/kiện/chủ sở hữu.'))
    results.sort(key=lambda x:(-x['affected_mo_count'],-abs(x['delta']),x['source_id']))
    report=dict(generated_utc=datetime.now(timezone.utc).isoformat(),read_only=True,erp_mutations=0,opening_cutoff_utc=load('scope.json')['start_utc'],rows=results,detailed_summary=detailed.get('summary'),scope_note='Chỉ tập đã ánh xạ; không thay đối chiếu tồn toàn công ty. Chưa tự sửa quant/master hoặc duyệt tolerance.')
    I['save']('opening-business-review.json',report)
    text=['# Chênh tồn đầu kỳ đang chặn MO/DO','',f"Hồ sơ local cập nhật UTC: {report['generated_utc']}. Không ghi Odoo.",'','Mốc đầu kỳ: 01/08/2026 00:00 giờ Malaysia. Số dưới đây là nguồn và đích trong snapshot tại cùng mốc, không phải tồn hiện tại. Một MO có thể vướng nhiều sản phẩm, không cộng chồng số ảnh hưởng.','','| Sản phẩm | ID v14 → v19 | Nguồn | Đích | Đích − nguồn | Đơn vị đích | MO bị chặn |','|---|---|---:|---:|---:|---|---:|']
    for row in results:
        text.append(f"| {row['name'].replace('|','/')} | {row['source_id']} → {row['target_id']} | {fmt(row['source_quantity'])} | {fmt(row['target_quantity'])} | {fmt(row['delta'])} | {row['target_unit'][1]} | {row['affected_mo_count']} |")
    text+=['','Chênh nhỏ có thể do độ chính xác; chênh lớn hoặc lệch lot/vị trí cần truy nguyên giao dịch nền. Chưa coi các chênh nhỏ là đã được duyệt, và chưa đề xuất tự cân tồn.','','Chi tiết MO bị ảnh hưởng và khóa vị trí/lot/kiện/chủ sở hữu ở [opening-business-review.json](opening-business-review.json). Báo cáo này không thay nghiệm thu tồn toàn công ty.']
    (OUT/'TON_DAU_KY_CAN_XAC_MINH.md').write_text('\n'.join(text)+'\n',encoding='utf8')
    print(json.dumps(dict(products_with_opening_difference=len(results),mo_impacts_are_overlapping=True,top_affected=[dict(name=x['name'],affected_mos=x['affected_mo_count']) for x in results[:5]]),ensure_ascii=False))
if __name__=='__main__':main()
