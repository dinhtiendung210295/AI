"""Review-only proposed offsets of evidenced legacy temporary stock, never applies counts."""
import json,runpy
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
BASE=Path(__file__).parent
I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'));OUT=I['OUT']
def load(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False
def main():
    provenance=load('opening-adjustment-provenance.json');opening={tuple(x['target_key']):x for x in load('detailed-opening-comparison.json')['rows']}
    units={x['id']:x for x in load('target-uom.uom.json')};products={x['id']:x for x in load('target-products.json')};locations={x['id']:x for x in load('target-stock.location.json')}
    net=defaultdict(float);evidence=defaultdict(set)
    for row in provenance['rows']:
        move=row['move'];origin=(move.get('origin') or '').upper();note=(move.get('description_picking_manual') or '').upper()
        strong=any(x['module']=='pysb_temporary_inventory' for x in row['external_ids']) or origin.startswith('PYSB-TEMP') or 'TEMPORARY STOCK TO REPLAY V14 NEGATIVE STOCK' in note
        if not strong:continue
        for line in row['lines']:
            pid=rid(line['product_id']);u=rid(line['product_uom_id']);base=rid(products[pid]['uom_id']);q=line['quantity']*units[u]['factor']/units[base]['factor']
            for destination,sign in [(False,-1),(True,1)]:
                location=rid(line['location_dest_id'] if destination else line['location_id'])
                if locations[location]['usage']!='internal':continue
                key=(pid,location,rid(line['lot_id']),rid(line['result_package_id'] if destination else line['package_id']),rid(line['owner_id']))
                net[key]+=sign*q;evidence[key].add(move['id'])
    candidates=[key for key,q in net.items() if abs(q)>1e-6]
    b=I['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    current=b.scan('stock.quant',[['company_id','=',1],['product_id','in',sorted({x[0] for x in candidates})]],['product_id','location_id','lot_id','package_id','owner_id','quantity','reserved_quantity'])
    pool=defaultdict(lambda:[0.,0.]);qids=defaultdict(list)
    for quant in current:
        key=tuple(rid(quant[x]) for x in ['product_id','location_id','lot_id','package_id','owner_id']);pool[key][0]+=quant['quantity'];pool[key][1]+=quant['reserved_quantity'];qids[key].append(quant['id'])
    rows=[]
    for key in candidates:
        q=net[key];op=opening.get(key);matches=bool(op and abs(op['delta']-q)<=1e-6);after=pool[key][0]-q
        rows.append(dict(target_key=list(key),product=products[key[0]]['name'],unit=units[rid(products[key[0]]['uom_id'])]['name'],temporary_move_ids=sorted(evidence[key]),temporary_net=q,opening=op,proposed_delta=-q,exact_opening_difference_explained=matches,current_quantity=pool[key][0],current_reserved=pool[key][1],current_quant_ids=qids[key],proposed_current_count=after,requires_negative_count=after<-1e-6,would_be_below_existing_reservations=after+1e-6<pool[key][1],safe_sample_candidate=matches and after>=-1e-6 and after+1e-6>=pool[key][1] and len(qids[key])<=1))
    rows.sort(key=lambda x:(not x['safe_sample_candidate'],not x['exact_opening_difference_explained'],x['target_key']))
    report=dict(read_only=True,discovery_only=True,write_authorized=False,generated_utc=datetime.now(timezone.utc).isoformat(),proposed_effective_utc='2026-07-31 15:59:59',rows=rows,summary=dict(candidate_keys=len(rows),exactly_explained_keys=sum(x['exact_opening_difference_explained'] for x in rows),safe_sample_candidates=sum(x['safe_sample_candidate'] for x in rows),negative_count_candidates=sum(x['exact_opening_difference_explained'] and x['requires_negative_count'] for x in rows)),note='Proposal only. Requires explicit approval for offsets outside frozen scope. Preserve original validated moves; no direct quant.quantity, no blanket removal by tag, no automatic count below reservations or below zero.')
    I['save']('temporary-opening-reconciliation-review.json',report)
    text=['# Đề xuất đối chiếu tồn tạm cũ — chưa thực hiện','',f"Cập nhật UTC: {report['generated_utc']}. Chỉ đọc, chưa có quyền ghi.",'','Chỉ đưa vào nhóm có bằng chứng nguồn gốc tồn tạm. Cột “khớp chênh đầu kỳ” yêu cầu lượng tồn tạm thuần đúng bằng chênh tại cùng sản phẩm/vị trí/lot/kiện/chủ sở hữu. Không tự xóa chứng từ đã done.','','| Sản phẩm | Khóa v19 (SP/vị trí/lot/kiện/chủ) | Tồn tạm thuần | Delta đề xuất | Khớp chênh đầu kỳ | Tồn hiện tại | Giữ chỗ | Tồn sau đối ứng | Có thể lấy mẫu không âm/không lấn giữ chỗ |','|---|---|---:|---:|---|---:|---:|---:|---|']
    for row in rows:
        text.append(f"| {row['product'].replace('|','/')} | {row['target_key']} | {row['temporary_net']:g} | {row['proposed_delta']:g} | {'Có' if row['exact_opening_difference_explained'] else 'Chưa'} | {row['current_quantity']:g} | {row['current_reserved']:g} | {row['proposed_current_count']:g} | {'Có' if row['safe_sample_candidate'] else 'Giữ chờ'} |")
    text+=['','Mốc đề xuất đối ứng: 31/07/2026 23:59:59 Malaysia, ngoài kỳ giao dịch tháng 8–10 đã chốt nên cần Operator duyệt riêng. Đây là hồ sơ chuẩn bị, chưa phải change set được phép thực thi. Cần kiểm tra lại live, đơn vị, valuation và bút toán native trước lấy mẫu. Chi tiết ID chứng từ tồn tạm và số liệu đầu kỳ ở [JSON](temporary-opening-reconciliation-review.json).']
    (OUT/'DE_XUAT_DOI_UNG_TON_TAM_CU.md').write_text('\n'.join(text)+'\n',encoding='utf8')
    print(json.dumps(report['summary']),flush=True);print(json.dumps([x for x in rows if x['safe_sample_candidate']][:2],ensure_ascii=False),flush=True)
if __name__=='__main__':main()
