"""Offline status of this authorized stock continuation; never claims full acceptance."""
import json,runpy
from datetime import datetime,timezone
from pathlib import Path
BASE=Path(__file__).parent
I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'));OUT=I['OUT']
def load(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def stamp(value):return datetime.fromisoformat(value.replace('Z','+00:00')) if value else datetime.min.replace(tzinfo=timezone.utc)
def main():
    approval=load('phases/operator-stock-resume-approval.json');start=stamp(approval['recorded_utc'])
    results={};uncertain=[];unfinished=[]
    for kind,name,key,field,done,date in [('receipt','independent-receipts-journal.json','groups','phase','completed','completed_utc'),('delivery','independent-delivery-journal.json','groups','phase','completed','completed_utc'),('mo','independent-mo-journal.json','mos','status','verified_done','verified_utc'),('inventory','independent-inventory-journal.json','groups','status','verified_done','verified_utc')]:
        j=load(name);complete=[{**row,'source_id':sid} for sid,row in j[key].items() if row.get(field)==done];new=[x for x in complete if stamp(x.get(date))>=start]
        uncertain.extend(dict(journal=name,index=i,model=x['model'],method=x['method']) for i,x in enumerate(j['operations']) if x['status'] in ['intent','uncertain'])
        unfinished.extend(dict(journal=name,source_id=sid,name=x.get('source_name'),phase=x.get(field),execution_hold=bool(x.get('execution_hold')),reason=x.get('hold_reason')) for sid,x in j[key].items() if x.get(field)!=done)
        results[kind]=dict(total_verified=len(complete),new_verified=len(new),new_source_ids=[x['source_id'] for x in new],new_moves=sum(len(x.get('verified_moves',[])) for x in new),new_pickings=sum(len(x.get('picking_pairs',{})) for x in new))
    coverage=load('after-run-stock-coverage.json');source=load('source-frozen-rescan-comparison.json')
    report=dict(generated_utc=datetime.now(timezone.utc).isoformat(),authorization_started_utc=start.isoformat(),scope=load('scope.json'),results=results,uncertain_operations=uncertain,unfinished_groups=unfinished,coverage=coverage['summary'],coverage_generated_utc=coverage['generated_utc'],source_rescan=source,full_acceptance=False)
    I['save']('phases/stock-resume-report.json',report)
    lines=['# Tiếp tục chuyển kho production PYSB','',f"Cập nhật UTC: {report['generated_utc']}. Chưa nghiệm thu toàn bộ.",'','| Nhóm | Hoàn tất mới trong lượt này | Tổng đã kiểm chứng | Move mới | Phiếu kho mới |','|---|---:|---:|---:|---:|']
    for kind,label in [('receipt','Chuỗi nhập PO'),('delivery','Chuỗi giao SO'),('mo','MO'),('inventory','Nhóm kiểm kê')]:
        x=results[kind];lines.append(f"| {label} | {x['new_verified']} | {x['total_verified']} | {x['new_moves']} | {x['new_pickings']} |")
    lines+=['',f"Quét move gần nhất: {json.dumps(report['coverage'],ensure_ascii=False)}.",f"Thao tác chưa rõ phản hồi: {len(uncertain)}. Nhóm chưa hoàn tất/giữ chờ: {len(unfinished)}.",'','Phạm vi nguồn: 01/08/2026 đến trước 24/10/2026 08:50:44 giờ Malaysia. Không mở rộng mốc chụp.','', 'Thứ tự đã được Bruce chốt: ưu tiên phiếu nhập PO đã confirm, rồi Inventory/MO/DO theo nguồn lịch sử. Gỡ giữ chỗ chỉ trong phạm vi phiếu migration chưa picked/done và có kiểm chứng tồn vật lý không đổi.','', 'Chi tiết và ID nguồn xem [báo cáo JSON](phases/stock-resume-report.json). Báo cáo bao phủ phải chạy lại sau lượt ghi cuối; còn move unresolved thì chưa được kết luận hoàn tất toàn bộ.']
    (OUT/'BAO_CAO_TIEP_TUC_KHO.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    compact={kind:{k:v for k,v in row.items() if k!='new_source_ids'} for kind,row in results.items()}
    print(json.dumps(dict(results=compact,unresolved_operations=len(uncertain),unfinished_groups=len(unfinished)),ensure_ascii=False),flush=True)
if __name__=='__main__':main()
