"""Offline review proposal only. Never rounds or writes MO production fields."""
import csv
import json
import runpy
from decimal import Decimal,ROUND_HALF_UP
from pathlib import Path
I=runpy.run_path(str(Path(__file__).with_name('inspect_pysb_aug_oct_prod.py')))
OUT=I['OUT']
def load(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def rid(x):return x[0] if isinstance(x,(tuple,list)) and x else x or False

def main():
    maps=load('resolved-master-evidence.json')['maps']['uom.uom'];units={x['id']:x for x in load('target-uom.uom.json')}
    moves={x['id']:x for x in load('source-moves.json')};mos=load('source-mos.json');plan=load('independent-mo-supply-plan.json');eligible={x['source_mo'] for x in plan['rows'] if x['eligible']}
    rows=[]
    def propose(mo,model,sid,field,value,source_unit,role):
        tid=maps.get(str(source_unit))
        if not tid:return
        precision=Decimal(str(units[tid]['rounding']));rounded=float((Decimal(str(value))/precision).quantize(Decimal('1'),rounding=ROUND_HALF_UP)*precision)
        if abs(value-rounded)<=1e-8:return
        rows.append({'source_mo':mo['id'],'name':mo['name'],'model':model,'source_id':sid,'field':field,'role':role,'source_quantity':value,'proposed_target_quantity':rounded,'delta':rounded-value,'target_unit':tid,'unit_name':units[tid]['name'],'precision':float(precision),'would_be_zero':bool(value and not rounded),'otherwise_eligible':mo['id'] in eligible,'decision':'pending_not_authorized'})
    for mo in mos:
        for field in ['product_qty','qty_produced']:propose(mo,'mrp.production',mo['id'],field,mo[field],rid(mo['product_uom_id']),'planned' if field=='product_qty' else 'actual_via_qty_producing')
        for role,field in [('raw','move_raw_ids'),('finished_or_byproduct','move_finished_ids')]:
            for mid in mo[field]:
                if mid in moves:
                    m=moves[mid];propose(mo,'stock.move',mid,'product_uom_qty',m['product_uom_qty'],rid(m['product_uom']),role)
    affected=sorted({x['source_mo'] for x in rows});zero={x['source_mo'] for x in rows if x['would_be_zero']};nonzero=[i for i in affected if i not in zero]
    result={'write_authorized':False,'policy':'Existing operator decision covers 22 stock detail lines only; these MO header/demand/qty_producing proposals remain held pending explicit extension',
        'automatic_review_rejection':'Expanded MO field rounding may change production consumption/output outside the approved 22 stock lines','rows':rows,'affected_mos':affected,'nonzero_only_mos':nonzero,'would_zero_mos':sorted(zero),
        'summary':{'affected_mos':len(affected),'field_differences':len(rows),'otherwise_eligible_mos':len(set(affected)&eligible),'nonzero_only_otherwise_eligible':len(set(nonzero)&eligible),'would_zero_otherwise_eligible':len(zero&eligible)}}
    I['save']('mo-extra-precision-review.json',result)
    with (OUT/'MO_CAN_DUYET_LAM_TRON_THEM.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]) if rows else ['source_mo']);writer.writeheader();writer.writerows(rows)
    text=['# MO cần quyết định làm tròn ngoài 22 dòng stock','',f"Tổng hợp: `{result['summary']}`.",'','Chưa được phép ghi các thay đổi đề xuất. Lượng thực tế của MO được đề xuất thông qua đầu vào `qty_producing`, không sửa trực tiếp trường tính toán `qty_produced`. Các MO có bất kỳ lượng đề xuất về 0 nên tiếp tục giữ chờ.','',
        'Tự động duyệt đã từ chối mở rộng vì quyết định cũ chỉ bao phủ 22 dòng stock; thay đổi thêm có thể ảnh hưởng tiêu hao và thành phẩm.','',
        '| MO | Trường | Nguồn | Đề xuất | Chênh lệch | Đơn vị v19 | Về 0 |','|---|---|---:|---:|---:|---|---|']
    text.extend(f"| {x['name']} | {x['model']} {x['source_id']}: {x['field']} | {x['source_quantity']} | {x['proposed_target_quantity']} | {x['delta']:.8g} | {x['unit_name']} ({x['precision']}) | {'Có' if x['would_be_zero'] else ''} |" for x in rows if x['otherwise_eligible'])
    (OUT/'MO_CAN_DUYET_LAM_TRON_THEM.md').write_text('\n'.join(text)+'\n',encoding='utf8');print(json.dumps(result['summary']),flush=True)

if __name__=='__main__':main()
