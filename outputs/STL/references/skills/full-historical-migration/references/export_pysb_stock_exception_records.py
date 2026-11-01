"""Xuất record ngoại lệ kho có link v14/v19; chỉ gọi API đọc."""
import json, runpy, socket
from pathlib import Path
from collections import defaultdict, Counter
from html import escape
ROOT=Path(__file__).resolve().parents[6]
P=ROOT/'outputs/pysb-stock-migration-20261012'
OUT=P/'exception-records-20261014';OUT.mkdir(exist_ok=True)
H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/confirm_pysb_july_po_staging.py'))
Reader,rid,save=H['Reader'],H['rid'],H['save'];socket.setdefaulttimeout(120)
def load(n):return json.loads((P/n).read_text(encoding='utf8'))
def idx(rows):return {x['id']:x for x in rows}
def url(side,model,id):return (('http://175.145.85.151' if side=='v14' else 'https://py-staging.odoo.com')+f'/web#id={id}&model={model}&view_type=form') if id else ''
def main():
 a=Reader(ROOT/'mcp-server-odoo/envs/v14-prod/.env');b=Reader(ROOT/'mcp-server-odoo/envs/v19-staging/.env')
 assert a.db=='paoyeang_live' and b.db=='py19-staging-39654560'
 j=load('execution-journal.json');manifest=load('execution-manifest.json');mo=load('mo-details.json');gap=load('closing-gap-source-documents.json');recon=load('closing-adjusted-reconciliation.json')
 maps={k:{int(s):t for s,t in v.items()} for k,v in manifest['maps'].items()}
 for k,v in j['maps'].items():maps.setdefault(k,{}).update({int(s):t for s,t in v.items()})
 for key in ['standalone_source_receipts','supporting_source_transfers','supplementary_inventory_adjustments']:
  for x in j.get(key,[]):
   if x.get('source_move') and x.get('target_move'):maps.setdefault('stock.move',{})[x['source_move']]=x['target_move']
   if x.get('source_picking') and x.get('target_picking'):maps.setdefault('stock.picking',{})[x['source_picking']]=x['target_picking']
 templates=[130306,118397,118378,116236]
 temps=j['temporary_negative_stock_adjustments'];receipts=j['standalone_source_receipts']
 mids={x['target_move'] for x in temps if x.get('target_move')}|{x['target_move'] for x in j['precision_differences'].values()}
 source_mo_ids={x['source_mo'] for x in j['precision_differences'].values()}
 target_mos=idx(b.read('mrp.production',[maps['mrp.production'][i] for i in source_mo_ids],['name','state','date_finished']))
 target_moves=idx(b.read('stock.move',mids,['state','date','quantity','product_id','picking_id','origin','move_line_ids']))
 pickids={x['target_picking'] for x in receipts if x.get('target_picking')}|{maps['stock.picking'][x['id']] for x in gap['pickings'] if x['id'] in maps['stock.picking']}|{x['event']['target'] for x in temps if x.get('event') and x['event']['kind']=='picking'}
 target_picks=idx(b.read('stock.picking',pickids,['name','state','date_done','origin']))
 source_products=idx(a.read('product.product',maps['product.product'].keys(),['name','categ_id','tracking']))
 target_products=idx(b.read('product.product',set(maps['product.product'].values())|set(templates)|{x['key'][0] for x in temps},['name','categ_id','tracking','product_tmpl_id']))
 sm=idx(mo['moves']);mos=idx(mo['mo'])
 decimals=[]
 for x in j['precision_differences'].values():
  s=sm[x['source_move']];t=target_moves[x['target_move']];tm=target_mos[maps['mrp.production'][x['source_mo']]]
  decimals.append(dict(source_mo=mos[x['source_mo']]['name'],source_mo_id=x['source_mo'],target_mo=tm['name'],target_mo_id=tm['id'],product=s['product_id'][1],source_product_id=rid(s['product_id']),target_product_id=rid(t['product_id']),source_qty=x['source_qty'],target_qty=x['target_qty'],uom=s['product_uom'][1],source_move=x['source_move'],target_move=x['target_move'],target_state=t['state']))
 negatives=[]
 for x in temps:
  t=target_moves.get(x.get('target_move'),{});key=x['key'];event=x.get('event') or {};ev=x.get('source_evidence',[])
  sourceids=sorted({v['source_move'] for v in ev if v.get('source_move')});sourcepicks=sorted({v['event']['source'] for v in ev if v.get('event',{}).get('kind')=='picking'})
  if event.get('kind')=='picking':sourcepicks=sorted(set(sourcepicks)|{event['source']})
  targetpick=event.get('target') if event.get('kind')=='picking' else None
  negatives.append(dict(token=x['token'],date=x['date'],product=target_products[key[0]]['name'],target_product_id=key[0],lot_id=key[2],location_id=key[1],delta=x['delta'],source_document=event.get('reference') or x.get('note',{}).get('missing_source_receipt','') if isinstance(x.get('note'),dict) else event.get('reference',''),source_picking_ids=sourcepicks,source_move_ids=sourceids,target_picking_id=targetpick,target_picking_name=target_picks.get(targetpick,{}).get('name'),target_move=x.get('target_move'),target_state=t.get('state'),reference=x['reference'],effective_at_july_cutoff=x['date']<recon['cutoff_utc'],purpose='temporary' if x['delta']>0 else 'counterpart_reversal'))
 # Standalone receipt rows preserve source order origin and source/target line IDs.
 old_po=[]
 for x in receipts:
  sp=x.get('note',{}).get('source_picking',{});sl=x.get('note',{}).get('source_line',{});tp=target_picks.get(x.get('target_picking'),{})
  old_po.append(dict(order=sp.get('origin',''),source_picking=sp.get('name',''),source_picking_id=x['source_picking'],target_picking=tp.get('name',''),target_picking_id=x.get('target_picking'),source_move=x['source_move'],target_move=x['target_move'],product=sl.get('product_id',[False,''])[1],source_qty=x['source_qty'],target_qty=x.get('target_qty'),date=x['date'],target_state=tp.get('state'),source_line_id=sl.get('id'),target_line_id=x.get('target_line'),reference=x['reference']))
 old_so=[]
 ordernames=sorted({x['origin'] for x in gap['pickings']})
 source_orders=a.search_read('sale.order',[['company_id','=',1],['name','in',ordernames]],['name','date_order'])
 sodates={x['name']:x for x in source_orders}
 for sp in gap['pickings']:
  tid=maps['stock.picking'].get(sp['id']);tp=target_picks.get(tid,{})
  old_so.append(dict(order=sp['origin'],source_order_id=sodates.get(sp['origin'],{}).get('id'),source_order_date_utc=sodates.get(sp['origin'],{}).get('date_order'),source_picking=sp['name'],source_picking_id=sp['id'],target_picking=tp.get('name',''),target_picking_id=tid,date=sp['date_done'],target_state=tp.get('state'),boundary_exception=sp['origin']=='SO-52939'))
 tracking=[]
 for t in templates:
  sid=next((s for s,v in maps['product.product'].items() if v==t),None)
  before='serial' if t==130306 else 'lot'
  tracking.append(dict(product=target_products[t]['name'],source_product_id=sid,source_tracking=source_products.get(sid,{}).get('tracking'),target_product_id=t,target_template_id=rid(target_products[t]['product_tmpl_id']),target_before=before,target_current=target_products[t]['tracking'],operator='Bruce' if t in [130306,118397] else 'Codex theo quyền Bruce',exception_type='serial_to_lot' if t==130306 else 'lot_to_quantity'))
 # All categories referenced by the migrated product mapping; read available fields.
 category_method=[]
 for reader,side,products in [(a,'v14',source_products),(b,'v19',target_products)]:
  schema=reader.call('product.category','fields_get',[],{'attributes':['type']})
  fields=['name']+[f for f in ['property_cost_method','property_valuation'] if f in schema]
  cats=reader.read('product.category',{rid(x['categ_id']) for x in products.values() if x['categ_id']},fields)
  for c in cats:category_method.append(dict(version=side,category_id=c['id'],category=c['name'],cost_method=c.get('property_cost_method','field_unavailable'),valuation=c.get('property_valuation','field_unavailable'),product_count=sum(rid(x['categ_id'])==c['id'] for x in products.values())))
 # Identify transfer/MO records affected by a changed tracking setting from canonical snapshots.
 snapshots=[load('v14-prod-snapshot.json'),load('supporting-stock-source-moves.json')]
 source_move_rows={}
 def collect(obj):
  if isinstance(obj,dict):
   if isinstance(obj.get('id'),int) and 'product_id' in obj and 'picking_id' in obj and ('product_uom_qty' in obj or 'quantity_done' in obj):source_move_rows[obj['id']]=obj
   for v in obj.values():
    if isinstance(v,(dict,list)):collect(v)
  elif isinstance(obj,list):
   for v in obj:collect(v)
 for s in snapshots+[mo,gap]:collect(s)
 linked=[]
 tracked_sources={x['source_product_id']:x['target_product_id'] for x in tracking}
 for mid,s in source_move_rows.items():
  sid=rid(s['product_id'])
  if sid not in tracked_sources:continue
  linked.append(dict(source_product_id=sid,target_product_id=tracked_sources[sid],source_move=mid,target_move=maps['stock.move'].get(mid),source_picking=s.get('picking_id'),target_picking_id=maps['stock.picking'].get(rid(s.get('picking_id'))),source_mo=s.get('raw_material_production_id') or s.get('production_id'),date=s.get('date')))
 product_differences=[x for x in recon['product_rows'] if abs(x.get('closing_delta',0))>.00501]
 report=dict(company_id=1,source_database=a.db,target_database=b.db,generated_date='2026-10-14',readonly=True,decimal_records=decimals,temporary_records=negatives,closing_product_differences=product_differences,old_po_receipt_records=old_po,additional_so_delivery_records=old_so,tracking_products=tracking,tracking_linked_moves=linked,category_methods=category_method,notes=['Cấu hình DB đọc ngày 14/10: 14 nhóm v14 FIFO, 6 nhóm v14 Standard Price; 28 nhóm v19 AVCO. Nhận định v14 AVCO/v19 FIFO trước đó không đúng cấu hình hiện tại. Không yêu cầu valuation khớp.','Negative amount ở đây là âm số lượng theo lot/vị trí, không phải số tiền âm.','0,972 làm tròn thành 0,97, không phải 0,07 như ảnh.','SO-52939 là ngoại lệ UTC cuối tháng 6 nhưng Malaysia 01/07; không xếp vào SO trước tháng 7.','49 record điều chỉnh tạm gồm cả khoản cấp và đối ứng; không đồng nghĩa 49 sản phẩm nguồn âm.','Linked move tracking là danh sách liên quan lấy từ snapshot, không có nghĩa mỗi move đều từng bị chặn vì tracking.'])
 save(OUT/'PYSB_Stock_Exception_Record_Index.json',report)
 def link(side,model,id,label=None):
  return f'<a href="{escape(url(side,model,id))}">{escape(str(label if label is not None else id))}</a>' if id else '—'
 def table(headers,rows):return '<table><thead><tr>'+''.join('<th>'+escape(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(c)+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table>'
 body='<h1>PYSB — record liên quan 5 nhóm ngoại lệ kho</h1><p>Chỉ Pao Yeang, v19 staging. Record đích và cấu hình được đọc lại ngày 14/10/2026; chi tiết nguồn từ nhật ký/snapshot chuyển dữ liệu. Link cần đăng nhập đúng hệ thống.</p><ul>'+''.join('<li>'+escape(n)+'</li>' for n in report['notes'])+'</ul>'
 body+='<h2>1. Làm tròn — 7 dòng MO</h2>'+table(['MO v14','MO v19','Sản phẩm','Đơn vị','Lượng v14 → v19','Move v14','Move v19'],[[link('v14','mrp.production',x['source_mo_id'],x['source_mo']),link('v19','mrp.production',x['target_mo_id'],x['target_mo']),escape(x['product']),escape(x['uom']),f"{x['source_qty']} → {x['target_qty']}",link('v14','stock.move',x['source_move']),link('v19','stock.move',x['target_move'])] for x in decimals])
 body+='<h2>2. Phương pháp định giá — record cấu hình nhóm sản phẩm</h2><p>Không phải một phiếu lỗi riêng. Danh sách dưới là các nhóm của sản phẩm đã ánh xạ, thể hiện cấu hình hiện tại từng nhóm; không đổi cấu hình trong lượt xuất này.</p>'+table(['Phiên bản','Nhóm sản phẩm','Phương pháp','Valuation','Số sản phẩm liên quan'],[[x['version'],link(x['version'],'product.category',x['category_id'],x['category']),escape(x['cost_method']),escape(x['valuation']),x['product_count']] for x in category_method])
 body+='<h2>3. Tồn tạm — toàn bộ 49 record cấp/đối ứng</h2><p>Có '+str(sum(x['effective_at_july_cutoff'] for x in negatives))+' record có ngày trước mốc cuối tháng 7. Khoản tháng 8/tháng 10 không làm tăng báo cáo cuối tháng 7. Xem reference để phân biệt nguồn âm, cấp tạm UV WHITE và cặp cấp–trừ.</p>'+table(['Ngày UTC','Sản phẩm','Lot v19','Cấp / trừ','Phiếu nguồn','Phiếu v19','Điều chỉnh v19','Reference'],[[escape(x['date']),link('v19','product.product',x['target_product_id'],x['product']),link('v19','stock.lot',x['lot_id']),x['delta'],'<br>'.join(link('v14','stock.picking',i,x['source_document'] or i) for i in x['source_picking_ids']) or escape(str(x['source_document'])),link('v19','stock.picking',x['target_picking_id'],x['target_picking_name']),link('v19','stock.move',x['target_move']),escape(x['reference'])] for x in negatives])
 body+='<h2>4a. PO cũ — 308 dòng nhập/chuyển vào kho, 125 phiếu lẻ</h2><p>Không tạo lại PO. Nhiều dòng chung một phiếu; không cộng số dòng thành số phiếu.</p>'+table(['PO nguồn / origin','Phiếu v14','Phiếu lẻ v19','Sản phẩm','Lượng v14 → v19','Move v14','Move v19','Ngày UTC'],[[escape(x['order']),link('v14','stock.picking',x['source_picking_id'],x['source_picking']),link('v19','stock.picking',x['target_picking_id'],x['target_picking']),escape(x['product']),f"{x['source_qty']} → {x['target_qty']}",link('v14','stock.move',x['source_move']),link('v19','stock.move',x['target_move']),escape(x['date'])] for x in old_po])
 body+='<h2>4b. SO ngoài danh sách ban đầu — 24 phiếu xuất bổ sung</h2><p>Gồm 6 SO. Riêng SO-52939 là ngày 01/07 theo Malaysia, không phải SO cũ; được ghi riêng để tránh nhầm phạm vi.</p>'+table(['SO v14','Ngày SO UTC','Phiếu v14','Phiếu lẻ v19','Ngày hoàn tất UTC','Ngoại lệ ngày'],[[link('v14','sale.order',x['source_order_id'],x['order']),escape(str(x['source_order_date_utc'])),link('v14','stock.picking',x['source_picking_id'],x['source_picking']),link('v19','stock.picking',x['target_picking_id'],x['target_picking']),escape(x['date']),'01/07 Malaysia' if x['boundary_exception'] else ''] for x in old_so])
 body+='<h2>5. Tracking — 4 sản phẩm</h2>'+table(['Sản phẩm v14','Sản phẩm v19','Tracking v14 hiện tại','v19 trước → hiện tại','Người thực hiện'],[[link('v14','product.product',x['source_product_id'],x['product']),link('v19','product.product',x['target_product_id'],x['product']),escape(str(x['source_tracking'])),f"{x['target_before']} → {x['target_current']}",escape(x['operator'])] for x in tracking])
 body+='<h3>Phiếu/MO liên quan sản phẩm đổi tracking</h3><p>Danh sách liên quan theo snapshot, không phải danh sách toàn bộ dòng từng bị chặn. Software là serial → lot, khác ba sản phẩm lot → quantity.</p>'+table(['Sản phẩm v19','Move v14','Move v19','Phiếu v14','Phiếu v19','MO nguồn','Ngày UTC'],[[link('v19','product.product',x['target_product_id']),link('v14','stock.move',x['source_move']),link('v19','stock.move',x['target_move']),link('v14','stock.picking',rid(x['source_picking']),x['source_picking'][1] if x['source_picking'] else None),link('v19','stock.picking',x['target_picking_id']),link('v14','mrp.production',rid(x['source_mo']),x['source_mo'][1] if x['source_mo'] else None),escape(str(x['date']))] for x in linked])
 html='<!doctype html><html lang="vi"><meta charset="utf-8"><title>PYSB ngoại lệ — record liên quan</title><style>body{font:15px/1.5 Arial;color:#16324b;padding:24px}table{border-collapse:collapse;width:100%;margin:18px 0}th,td{border:1px solid #ccd7df;padding:8px;text-align:left;vertical-align:top}th{background:#e7f1f7}a{color:#126897}h2{margin-top:38px}td{overflow-wrap:anywhere}@media print{thead{display:table-header-group}tr{break-inside:avoid}}</style>'+body+'</html>'
 (OUT/'PYSB_Stock_Exception_Record_Index.html').write_text(html,encoding='utf8')
 print(json.dumps(dict(decimal=len(decimals),temporary=len(negatives),old_po_rows=len(old_po),old_po_pickings=len({x['target_picking_id'] for x in old_po}),old_so_pickings=len(old_so),tracking_products=len(tracking),tracking_linked_moves=len(linked),category_methods=dict(Counter(x['version']+'/'+x['cost_method'] for x in category_method))),ensure_ascii=False),flush=True)
if __name__=='__main__':main()
