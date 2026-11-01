"""Offline all-category month backlog; a month closes only with no unresolved move."""
import argparse,json,collections
from pathlib import Path
from datetime import datetime,timedelta,timezone
BASE=Path(__file__).parent;OUT=BASE.parents[5]/'outputs/pysb-aug-oct-prod-20261024'
def load(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False
def month_of(value):return (datetime.strptime(value,'%Y-%m-%d %H:%M:%S')+timedelta(hours=8)).strftime('%Y-%m')
def main(month):
    moves={x['id']:x for x in load('source-moves.json')};coverage=load('after-run-stock-coverage.json');cov={x['source_move_id']:x for x in coverage['results']}
    reasons=collections.defaultdict(list)
    for file,key,field in [('independent-receipts-manifest.json','groups','issues'),('independent-delivery-plan.json','rows','errors'),('independent-inventory-adjustment-plan.json','groups','errors')]:
        for g in load(file)[key]:
            for mid in g.get('moves',[]):reasons[mid].append(dict(plan=file,source_document=g.get('source',{}).get('name',g.get('name')),issues=g.get(field,[])))
    mo={x['source_mo']:x for x in load('independent-mo-supply-plan.json')['rows']}
    summary=collections.defaultdict(collections.Counter);rows=[]
    for mid,m in sorted(moves.items(),key=lambda x:(x[1]['date'],x[0])):
        if month_of(m['date'])!=month:continue
        c=cov[mid];summary[c['category']][c['status']]+=1
        if c['status']!='unresolved':continue
        plans=list(reasons[mid]);moid=rid(m.get('production_id')) or rid(m.get('raw_material_production_id'))
        if moid and moid in mo:plans.append(dict(plan='independent-mo-supply-plan.json',source_document=mo[moid]['name'],issues=mo[moid]['errors'],shortages=mo[moid].get('shortages',[])))
        rows.append(dict(source_move=mid,date_utc=m['date'],category=c['category'],name=m['name'],product=m['product_id'],picking=m['picking_id'],source_location=m['location_id'],destination_location=m['location_dest_id'],quantity=m['quantity_done'],coverage_issues=c['issues'],plan_evidence=plans,native_adapter_review_required=not plans,origin_returned_move=rid(m.get('origin_returned_move_id')),predecessors=m['move_orig_ids'],successors=m['move_dest_ids']))
    result=dict(month_malaysia=month,coverage_generated_utc=coverage['generated_utc'],report_generated_utc=datetime.now(timezone.utc).isoformat(),read_only=True,erp_calls=0,summary={k:dict(v) for k,v in summary.items()},unresolved_count=len(rows),month_complete=not rows,rows=rows)
    target=OUT/'phases'/('warehouse-backlog-'+month+'.json');target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    lines=[f'# Nghiệp vụ kho tháng {month} (Malaysia)','',f"Nguồn đối chiếu: {coverage['generated_utc']}. Còn {len(rows)} move chưa kiểm chứng. Chưa nghiệm thu tháng.",'','| Loại move | Đã kiểm chứng | Ngoại lệ được duyệt | Chưa giải quyết |','|---|---:|---:|---:|']
    for k,v in sorted(summary.items()):lines.append(f"| {k} | {v['verified']} | {v['approved_exception']} | {v['unresolved']} |")
    lines+=['','Mỗi move chưa giải quyết và liên kết nguyên nhân nằm trong JSON cùng tên. Receipt được ưu tiên; các nhóm còn lại theo phụ thuộc thực tế. Không dùng hết hàng đợi đủ điều kiện để thay thế nghiệm thu toàn tháng.']
    (OUT/f'NGHIEP_VU_KHO_{month}.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--month',required=True,choices=['2026-08','2026-09','2026-10']);main(p.parse_args().month)
