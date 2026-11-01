"""Chỉ đọc DB: SO tháng 7, xuất tháng sau, nguồn nhập muộn và cách chuyển v19."""
import json, runpy, socket, re, sys
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timezone
from html import escape

ROOT=Path(__file__).resolve().parents[6]
OUT=ROOT/'outputs/pysb-stock-migration-20261012/late-so-supply-audit-20261014'
OUT.mkdir(exist_ok=True)
H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/confirm_pysb_july_po_staging.py'))
Reader,rid,require,save=[H[k] for k in ('Reader','rid','require','save')]
socket.setdefaulttimeout(120)
def read(r,model,ids,fields):
    result=[]
    ids=sorted(set(ids))
    for n in range(0,len(ids),300):result+=r.read(model,ids[n:n+300],fields)
    return result
def log(label,**kw):print(json.dumps(dict(phase=label,**kw),ensure_ascii=False),flush=True)
def load(p):return json.loads(p.read_text(encoding='utf8'))
def main():
    a=Reader(ROOT/'mcp-server-odoo/envs/v14-prod/.env')
    b=Reader(ROOT/'mcp-server-odoo/envs/v19-staging/.env')
    if '--reuse-source' in sys.argv:
        cache=load(OUT/'live-source-snapshot.json')
        original_read=a.read; original_search=a.search_read
        cached_models={'sale.order':cache['orders'],'stock.picking':cache['late_pickings'],
                       'stock.move':cache['history_moves'],'stock.move.line':cache['history'],
                       'product.product':cache['products'],'uom.uom':cache['uoms'],'purchase.order':cache['pos']}
        def cached_read(model,ids,fields):
            ix={x['id']:x for x in cached_models.get(model,[])}
            if all(i in ix and all(f in ix[i] for f in fields) for i in ids):return [{f:ix[i][f] for f in ['id']+fields} for i in ids]
            return original_read(model,ids,fields)
        def cached_search(model,domain,fields,**kw):
            key={'stock.move':'moves','stock.move.line':'history','stock.location':'locations','uom.uom':'uoms'}.get(model)
            if key:return [{f:x[f] for f in ['id']+fields} for x in cache[key]]
            return original_search(model,domain,fields,**kw)
        a.read=cached_read;a.search_read=cached_search
        log('reuse_current_session_source_snapshot')
    require(a.db=='paoyeang_live' and b.db=='py19-staging-39654560','Wrong databases')
    require(b.read('res.company',[1],['name'])[0]['name']=='PAO YEANG SDN BHD','Wrong company')
    hand=load(ROOT/'outputs/pysb-so-confirm-20261012-staging/so-delivery-handoff.json')
    orders=read(a,'sale.order',[x['source_id'] for x in hand],['name','date_order','picking_ids','order_line','company_id'])
    require(all(rid(x['company_id'])==1 for x in orders),'Cross company')
    om={x['id']:x for x in orders}
    picks=read(a,'stock.picking',[p for x in orders for p in x['picking_ids']],['name','state','date_done','origin','company_id','location_id','location_dest_id'])
    late=[p for p in picks if p['state']=='done' and p['date_done']>='2026-07-31 16:00:00']
    log('late_pickings',orders=len(orders),pickings=len(late))
    pso=defaultdict(list)
    for o in orders:
        for p in o['picking_ids']:pso[p].append(o['name'])
    mf=['name','date','state','company_id','picking_id','product_id','product_uom','product_uom_qty','move_line_ids','sale_line_id','purchase_line_id','location_id','location_dest_id','move_orig_ids','move_dest_ids','origin_returned_move_id']
    moves=a.search_read('stock.move',[['company_id','=',1],['picking_id','in',[p['id'] for p in late]],['state','=','done']],mf)
    products=sorted({rid(m['product_id']) for m in moves})
    if not products:raise RuntimeError('No later products')
    locs={x['id']:x for x in a.search_read('stock.location',[],['usage','complete_name','company_id'])}
    meta=a.call('stock.move.line','fields_get',[],{'attributes':['type']})
    lf=['move_id','picking_id','product_id','product_uom_id','qty_done','lot_id','date','location_id','location_dest_id','package_id','result_package_id','owner_id']
    if 'product_qty' in meta:lf+=['product_qty']
    late_lines=read(a,'stock.move.line',[i for m in moves for i in m['move_line_ids']],lf)
    latest=max(x['date'] for x in late_lines)
    history=a.search_read('stock.move.line',[['company_id','=',1],['product_id','in',products],['state','=','done'],['date','<=',latest],['qty_done','>',0]],lf)
    require(len(history)<100000,'History hit RPC cap; paginate before concluding')
    log('source_history',products=len(products),lines=len(history),latest=latest)
    hm=read(a,'stock.move',[rid(x['move_id']) for x in history],mf)
    hmi={x['id']:x for x in hm}
    prods={x['id']:x for x in read(a,'product.product',products,['name','uom_id'])}
    uoms={x['id']:x for x in a.search_read('uom.uom',[],['name','factor','rounding'])}
    def q(x):
        # v14 product_qty on move line reflects reservation, not done quantity.
        return x['qty_done']/uoms[rid(x['product_uom_id'])]['factor']*uoms[rid(prods[rid(x['product_id'])]['uom_id'])]['factor']
    receipts=[x for x in history if x['date']>='2026-07-31 16:00:00' and locs[rid(x['location_id'])]['usage']=='supplier' and locs[rid(x['location_dest_id'])]['usage']=='internal']
    receipt_moves={rid(x['move_id']) for x in receipts}
    purchase_lines=read(a,'purchase.order.line',[rid(hmi[i]['purchase_line_id']) for i in receipt_moves if hmi[i]['purchase_line_id']],['order_id'])
    pol={x['id']:rid(x['order_id']) for x in purchase_lines}
    pos={x['id']:x for x in read(a,'purchase.order',pol.values(),['name','date_order','company_id'])}
    journal=load(ROOT/'outputs/pysb-stock-migration-20261012/execution-journal.json')
    manifest=load(ROOT/'outputs/pysb-stock-migration-20261012/execution-manifest.json')
    maps={k:{int(s):t for s,t in v.items()} for k,v in manifest['maps'].items()}
    for model,values in journal['maps'].items():maps.setdefault(model,{}).update({int(s):t for s,t in values.items()})
    for k in ['standalone_source_receipts','supporting_source_transfers','supplementary_inventory_adjustments']:
        for x in journal.get(k,[]):
            if x.get('source_move') and x.get('target_move'):maps.setdefault('stock.move',{})[x['source_move']]=x['target_move']
    external=b.search_read('ir.model.data',[['model','=','stock.move'],['module','=','pysb_v14']],['name','res_id'])
    for x in external:
        match=re.match(r'^stock_move_(\d+)(?:_|$)',x['name'])
        if match:maps.setdefault('stock.move',{})[int(match[1])]=x['res_id']
    relevant=set(receipt_moves)|{x['id'] for x in moves}
    storage_by_receipt={}
    for mid in receipt_moves:
        storage_by_receipt[mid]=[i for i in hmi[mid]['move_dest_ids'] if i in hmi and hmi[i]['state']=='done' and locs[rid(hmi[i]['location_id'])]['usage']=='internal' and locs[rid(hmi[i]['location_dest_id'])]['usage']=='internal']
        relevant.update(storage_by_receipt[mid])
    target_moves=read(b,'stock.move',[maps.get('stock.move',{}).get(i) for i in relevant if maps.get('stock.move',{}).get(i)],['state','date','company_id','picking_id','product_id','product_uom','quantity','location_id','location_dest_id','move_line_ids','origin'])
    tm={x['id']:x for x in target_moves}
    tls=read(b,'stock.move.line',[i for x in target_moves for i in x['move_line_ids']],['move_id','product_id','product_uom_id','quantity','lot_id','date','location_id','location_dest_id','package_id','result_package_id','owner_id'])
    tlm=defaultdict(list)
    for x in tls:tlm[rid(x['move_id'])].append(x)
    slm=defaultdict(list)
    for x in history:slm[rid(x['move_id'])].append(x)
    def verify(mid):
        tid=maps.get('stock.move',{}).get(mid)
        if not tid or tid not in tm:return dict(status='missing_mapping',target_move=tid)
        s=hmi[mid];t=tm[tid];errors=[]
        if t['state']!='done':errors.append('state')
        if rid(t['company_id'])!=1:errors.append('company')
        if t['date']!=s['date']:errors.append('move_date')
        expected=defaultdict(float);actual=defaultdict(float)
        for x in slm[mid]:
            keys=[]
            for f,model in [('product_id','product.product'),('product_uom_id','uom.uom'),('location_id','stock.location'),('location_dest_id','stock.location'),('lot_id','stock.lot'),('package_id','stock.package'),('result_package_id','stock.package')]:
                sid=rid(x[f]);keys.append(maps.get(model,{}).get(sid,('unmapped',sid)) if sid else False)
            keys.append(False if not x['owner_id'] else ('owner',rid(x['owner_id'])))
            expected[tuple(keys)]+=round(x['qty_done'],2)
        for x in tlm[tid]:
            if x['quantity']>0:actual[tuple(rid(x[f]) for f in ['product_id','product_uom_id','location_id','location_dest_id','lot_id','package_id','result_package_id','owner_id'])]+=x['quantity']
            if x['quantity']>0 and x['date']!=s['date']:errors.append('line_date')
        if set(expected)!=set(actual) or any(abs(v-actual.get(k,0))>.00501 for k,v in expected.items()):errors.append('details')
        return dict(status='verified' if not errors else 'review_required',target_move=tid,target_picking=t['picking_id'],errors=sorted(set(errors)))
    checks={mid:verify(mid) for mid in relevant}
    # Reconstruct global internal quantity per product/lot from all done source lines.
    # This proves net need for later receipts, not allocation of a specific receipt to a SO.
    balances=defaultdict(float);recent=defaultdict(float);received=defaultdict(list);before={}
    interested={x['id'] for x in late_lines}
    for x in sorted(history,key=lambda x:(x['date'],x['id'])):
        key=(rid(x['product_id']),rid(x['lot_id']),rid(x['owner_id']))
        src=locs[rid(x['location_id'])]['usage'];dst=locs[rid(x['location_dest_id'])]['usage']
        if x['id'] in interested:
            before[x['id']]=dict(balance=balances[key],later_supplier_receipts=recent[key],receipts=list(received[key]))
        amount=q(x)
        if src=='internal':balances[key]-=amount
        if dst=='internal':balances[key]+=amount
        if src=='supplier' and dst=='internal' and x['date']>='2026-07-31 16:00:00':
            recent[key]+=amount;received[key].append(x['id'])
    histid={x['id']:x for x in history}
    cases=[]
    for x in late_lines:
        # Customer delivery is the actual exit from company internal stock.
        if x['qty_done']<=0 or locs[rid(x['location_id'])]['usage']!='internal' or locs[rid(x['location_dest_id'])]['usage']!='customer':continue
        ev=before[x['id']];receiptids=ev['receipts'];need=q(x)
        if not receiptids:continue
        mids=sorted({rid(histid[i]['move_id']) for i in receiptids})
        supplies=[]
        for mid in mids:
            sm=hmi[mid];po=pos.get(pol.get(rid(sm['purchase_line_id'])))
            supplies.append(dict(source_move=mid,date=sm['date'],source_picking=sm['picking_id'],po=po,quantity=sum(q(histid[i]) for i in receiptids if rid(histid[i]['move_id'])==mid),target=checks[mid],storage_moves=[dict(source_move=i,date=hmi[i]['date'],target=checks[i]) for i in storage_by_receipt[mid]]))
        status='review_required' if checks[rid(x['move_id'])]['status']!='verified' or any(s['target']['status']!='verified' or any(z['target']['status']!='verified' for z in s['storage_moves']) for s in supplies) else 'verified'
        cases.append(dict(source_line=x['id'],so=pso[rid(x['picking_id'])],source_picking=x['picking_id'],source_move=rid(x['move_id']),date=x['date'],product=x['product_id'],lot=x['lot_id'],qty=need,base_uom=prods[rid(x['product_id'])]['uom_id'],source_internal_quantity_before=ev['balance'],later_receipt_qty=ev['later_supplier_receipts'],source_quantity_without_later_receipts=ev['balance']-ev['later_supplier_receipts'],net_later_receipt_dependency=ev['balance']-ev['later_supplier_receipts']+0.00501<need,source_negative_at_delivery=ev['balance']+0.00501<need,supplies=supplies,target_delivery=checks[rid(x['move_id'])],status=status))
    temps=journal.get('temporary_negative_stock_adjustments',[])
    temp_current=read(b,'stock.move',[t['target_move'] for t in temps if t.get('target_move')],['state','date','quantity','product_id','location_id','location_dest_id','origin'])
    late_temp_groups=defaultdict(list)
    for t in temps:
        if t.get('event') and t['date']>='2026-07-31 16:00:00' and t['event']['source'] in pso:
            for ev in t.get('source_evidence',[]):
                late_temp_groups[ev['source_move']].append(t)
    exact=defaultdict(float);source_before={}
    for x in sorted(history,key=lambda x:(x['date'],x['id'])):
        key=(rid(x['product_id']),rid(x['lot_id']),rid(x['location_id']),rid(x['package_id']),rid(x['owner_id']))
        if rid(x['move_id']) in late_temp_groups:source_before[x['id']]=exact[key]
        exact[key]-=q(x)
        exact[(rid(x['product_id']),rid(x['lot_id']),rid(x['location_dest_id']),rid(x['result_package_id']),rid(x['owner_id']))]+=q(x)
    temp_live={x['id']:x for x in temp_current}
    late_temp_review=[]
    for mid,ts in late_temp_groups.items():
        ev=ts[0]['source_evidence'][0];sourceids=ev['source_line_ids']
        line_reviews=[dict(source_line=i,lot=histid[i]['lot_id'],source_qty_before=source_before[i],required=q(histid[i]),source_negative=source_before[i]+.00501<q(histid[i])) for i in sourceids]
        late_temp_review.append(dict(so=pso[ts[0]['event']['source']],source_move=mid,source_picking=hmi[mid]['picking_id'],product=hmi[mid]['product_id'],date=hmi[mid]['date'],source_checks=line_reviews,total_temporary=sum(t['delta'] for t in ts),temporary_moves=[dict(target_move=t['target_move'],delta=t['delta'],live=temp_live.get(t['target_move'])) for t in ts],target_outbound=checks[mid],classification='source_negative' if all(z['source_negative'] for z in line_reviews) else 'review_required'))
    # Live verification of UV WHITE supply and source adjustment, separately from late DO.
    uvsource=read(a,'stock.move',[524618,524639,529698,529699,529700],mf)
    uvtarget=read(b,'stock.move',[17672,17673,17674,17675],['state','date','quantity','product_id','location_id','location_dest_id','origin','move_line_ids'])
    summary=dict(july_so=len(orders),late_done_pickings=len(late),late_moves=len(moves),late_customer_delivery_lines=sum(x['qty_done']>0 and locs[rid(x['location_id'])]['usage']=='internal' and locs[rid(x['location_dest_id'])]['usage']=='customer' for x in late_lines),cases_with_same_lot_later_receipt=len(cases),distinct_so_in_cases=len({so for c in cases for so in c['so']}),net_dependency_cases=sum(c['net_later_receipt_dependency'] for c in cases),case_statuses=dict(Counter(c['status'] for c in cases)),receipt_move_checks=dict(Counter(checks[mid]['status'] for mid in receipt_moves)),delivery_move_checks=dict(Counter(checks[m['id']]['status'] for m in moves)))
    summary['late_temporary_so_cases']=len(late_temp_review)
    report=dict(generated_utc=datetime.now(timezone.utc).isoformat(),source_database=a.db,target_database=b.db,company_id=1,readonly=True,summary=summary,cases=cases,late_temporary_review=late_temp_review,move_checks=checks,temporary_adjustments=temps,temporary_live_moves=temp_current,uv_white=dict(source_moves=uvsource,target_moves=uvtarget),method='July SO scope from approved handoff, live source linked pickings; later = from 01 Aug Malaysia. Same product/lot/owner supplier input before delivery is evidence of available supply, not unique assignment. Net dependency subtracts all later supplier receipts from source internal stock immediately before delivery. Quantities use source base UOM. Validate mapped source moves via done state, dates and per-line product/UOM/qty/lot/location/package; owner mappings need explicit review. Date ties sorted by source line ID; no claim of intra-second real-time order.')
    save(OUT/'late-so-supply-report.json',report)
    save(OUT/'live-source-snapshot.json',dict(orders=orders,late_pickings=late,moves=moves,late_lines=late_lines,history=history,history_moves=hm,locations=list(locs.values()),products=list(prods.values()),uoms=list(uoms.values()),pos=list(pos.values())))
    save(OUT/'live-target-snapshot.json',dict(moves=target_moves,lines=tls,external_ids=external))
    cards=[]
    for c in cases:
        lines=[]
        for s in c['supplies']:
            po=s['po']['name'] if s['po'] else 'không gắn PO'
            podate=s['po']['date_order'] if s['po'] else ''
            lines.append(f'<li>{escape(po)} (ngày PO {escape(podate)}): nhập {s["quantity"]:g} ngày UTC {s["date"]}; move v14 {s["source_move"]} → v19 {s["target"].get("target_move")}; {s["target"]["status"]}, {escape(str(s["target"].get("errors",[])))}. Bước vào kho: {escape(str(s["storage_moves"]))}</li>')
        cards.append(f'<article><h2>{escape(", ".join(c["so"]))} — {escape(c["source_picking"][1])}</h2><p>{escape(c["product"][1])}; lot {escape(c["lot"][1] if c["lot"] else "không lot")}; xuất {c["qty"]:g} ngày UTC {c["date"]}.</p><p>Tồn nội bộ nguồn trước xuất: {c["source_internal_quantity_before"]:g}; nếu loại nhập từ tháng 8: {c["source_quantity_without_later_receipts"]:g}. Phụ thuộc ròng: {c["net_later_receipt_dependency"]}.</p><p>Xuất v19: {escape(str(c["target_delivery"]))}; kết luận kiểm tra: {c["status"]}.</p><ul>{"".join(lines)}</ul></article>')
    html=f'''<!doctype html><html lang="vi"><meta charset="utf-8"><title>SO tháng 7 — nguồn nhập tháng sau</title><style>body{{font:16px/1.6 Arial;max-width:1150px;margin:28px auto;padding:20px;color:#183047}}article{{border:1px solid #ccc;padding:18px;margin:20px 0}}h2{{font-size:20px}}pre{{white-space:pre-wrap}}</style><h1>SO tháng 7 — kiểm tra nguồn nhập tháng sau</h1><p>Đọc trực tiếp v14 prod và v19 staging, công ty Pao Yeang ID 1. Không ghi Odoo. Ngày chi tiết hiển thị UTC; ranh giới tháng dùng Malaysia UTC+8.</p><pre>{escape(json.dumps(summary,ensure_ascii=False,indent=2))}</pre><p>Có nhập cùng sản phẩm/lot không đồng nghĩa phiếu đó cấp riêng cho SO. Phụ thuộc ròng được xét bằng tồn nguồn trước xuất sau khi loại lượng nhập từ tháng 8. Chưa kết luận tồn tại từng vị trí hoặc mọi biến động nguồn đều đã chuyển chỉ từ phép kiểm tra này. 13 receipt chưa ánh xạ trong phần thống kê rộng không trùng nguồn cùng lot cấp trước các DO đã chọn; không coi tất cả là receipt cần chuyển.</p>{''.join(cards)}<h2>Hai SO xuất tháng 8 dùng tồn tạm</h2><pre>{escape(json.dumps(late_temp_review,ensure_ascii=False,indent=2))}</pre><h2>UV WHITE riêng</h2><p>Đây là điều chỉnh tồn ngày 10/10, không phải DO tháng 10. Khoản tạm +4 còn hiệu lực theo quyết định đã duyệt.</p><pre>{escape(json.dumps(report['uv_white'],ensure_ascii=False,indent=2))}</pre></html>'''
    (OUT/'PYSB_Late_SO_Supply_Review.html').write_text(html,encoding='utf8')
    log('complete',**summary)
if __name__=='__main__':main()
