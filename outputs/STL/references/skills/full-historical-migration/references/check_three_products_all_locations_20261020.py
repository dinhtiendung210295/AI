"""Read-only quantities across real and virtual locations, current and July cutoff."""
import json,runpy,socket
from pathlib import Path
from collections import defaultdict
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[6];OUT=ROOT/'outputs/pysb-sue-stock-review-20261020'
socket.setdefaulttimeout(60)
Reader=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/so-po-migration/scripts/test_prepare_july_2026_so_po_migration.py'))['OdooReader']
CUTOFF='2026-07-31 15:00:00'
report={'writes_performed':False,'checked_utc':datetime.now(timezone.utc).isoformat(),'cutoff_utc':CUTOFF,'cutoff_local':'31/07/2026 23:00 Malaysia'}
for side,env,ids in [('v14','v14-prod',[43594,51469,51470]),('v19','v19-staging',[113358,112635,114965])]:
 r=Reader(ROOT/f'mcp-server-odoo/envs/{env}/.env')
 if side=='v19':assert (r.url,r.db)==('https://py-staging.odoo.com','py19-staging-39654560')
 products=r.read('product.product',ids,['name','uom_id','company_id'])
 qs=r.call('stock.quant','fields_get',[],{'attributes':['type']});qfs=[f for f in ['product_id','location_id','lot_id','package_id','owner_id','quantity','reserved_quantity','company_id'] if f in qs]
 quants=r.search_read('stock.quant',[['product_id','in',ids]],qfs)
 ls=r.call('stock.move.line','fields_get',[],{'attributes':['type']})
 lfs=[f for f in ['product_id','product_uom_id','qty_done','quantity','quantity_product_uom','location_id','location_dest_id','lot_id','date','company_id','owner_id','package_id','result_package_id','move_id'] if f in ls]
 later=r.search_read('stock.move.line',[['product_id','in',ids],['state','=','done'],['date','>',CUTOFF]],lfs)
 assert len(later)<100000
 locids=sorted({q['location_id'][0] for q in quants}|{x[f][0] for x in later for f in ['location_id','location_dest_id']})
 locations={x['id']:x for x in r.read('stock.location',locids,['complete_name','usage','company_id','active'])}
 uoms={x['id']:x for x in r.read('uom.uom',sorted({p['uom_id'][0] for p in products}|{x['product_uom_id'][0] for x in later}),['name','factor','rounding'])}
 pi={x['id']:x for x in products};now=defaultdict(float);reserved=defaultdict(float)
 for q in quants:
  k=(q['product_id'][0],q['location_id'][0],q['lot_id'][0] if q['lot_id'] else False);now[k]+=q['quantity'];reserved[k]+=q.get('reserved_quantity',0)
 historical=defaultdict(float,now)
 for x in later:
  pid=x['product_id'][0];lot=x['lot_id'][0] if x['lot_id'] else False
  qty=x.get('quantity_product_uom') if side=='v19' and 'quantity_product_uom' in x else x['qty_done' if side=='v14' else 'quantity']/uoms[x['product_uom_id'][0]]['factor']*uoms[pi[pid]['uom_id'][0]]['factor']
  historical[(pid,x['location_id'][0],lot)]+=qty;historical[(pid,x['location_dest_id'][0],lot)]-=qty
 lotnames={q['lot_id'][0]:q['lot_id'][1] for q in quants if q['lot_id']};lotnames.update({x['lot_id'][0]:x['lot_id'][1] for x in later if x['lot_id']})
 rows=[]
 for k in sorted(set(now)|set(historical),key=str):
  pid,lid,lot=k
  if max(abs(now[k]),abs(historical[k]),abs(reserved[k]))<1e-6:continue
  loc=locations[lid]
  rows.append({'product_id':pid,'product':pi[pid]['name'],'uom':pi[pid]['uom_id'][1],'location_id':lid,'location':loc['complete_name'],'usage':loc['usage'],'location_company':loc['company_id'],'lot_id':lot,'lot':lotnames.get(lot,'Không lot'),'current_quantity':round(now[k],6),'current_reserved':round(reserved[k],6),'july_quantity':round(historical[k],6)})
 # Cross-check reconstruction against Odoo's own as-of quantities at every real stock location.
 checks=[]
 real=[x['id'] for x in r.search_read('stock.location',[['usage','in',['internal','transit']],'|',['company_id','=',1],['company_id','=',False]],['id'])]
 if real:
  native=r.call('product.product','read',[ids],{'fields':['qty_available'],'context':{'to_date':CUTOFF,'location':real,'compute_child':False,'force_company':1}})
  for x in native:
   calculated=sum(v for (pid,lid,lot),v in historical.items() if pid==x['id'] and lid in real)
   assert abs(calculated-x['qty_available'])<1e-5,(side,x,calculated)
   checks.append({'product_id':x['id'],'native_july_quantity':x['qty_available'],'reconstructed_july_quantity':calculated})
 report[side]={'database':r.db,'products':products,'quants':quants,'later_lines':later,'locations':list(locations.values()),'rows':rows,'native_checks':checks}
 (OUT/'three-products-all-locations.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 print(side,json.dumps({'rows':rows,'native_checks':checks},ensure_ascii=True),flush=True)

def fmt(v):return str(round(v,6))
text='# Tồn ba sản phẩm trên mọi vị trí — v14 và v19 staging\n\nChỉ đọc dữ liệu ngày 20/10/2026. Cột tháng 7 tại 31/07/2026 23:00 giờ Malaysia. Lượng giữ chỗ chỉ là hiện tại. Số lượng quy về đơn vị tồn kho của sản phẩm.\n\n'
for side in ['v14','v19']:
 text+='## '+side+'\n\n'
 for product in report[side]['products']:
  text+='### '+product['name']+'\n\n| Vị trí | Loại | Lot | Tồn tháng 7 | Tồn hiện tại | Giữ chỗ hiện tại |\n|---|---|---|---:|---:|---:|\n'
  rows=[x for x in report[side]['rows'] if x['product_id']==product['id']]
  for x in rows:text+='| '+' | '.join([x['location'],x['usage'],x['lot'],fmt(x['july_quantity']),fmt(x['current_quantity']),fmt(x['current_reserved'])])+' |\n'
  if not rows:text+='| Tất cả vị trí được kiểm tra | — | — | 0 | 0 | 0 |\n'
  text+='\n'
text+='Vị trí internal/transit là kho thực/gửi bán/chuyển tiếp. Inventory adjustment, Production, Customers hoặc Vendors là vị trí ảo/đối tác; số dư tại đó không cộng vào tồn kho thực. Bảng chỉ hiện các dòng có tồn hoặc giữ chỗ khác 0 ở ít nhất một mốc; JSON lưu cả quant 0 và dữ liệu chi tiết. Tồn tháng 7 được dựng từ quant hiện tại, đảo các move line done sau mốc; tổng kho thực đã kiểm chứng độc lập bằng qty_available lịch sử của Odoo. Không sửa dữ liệu.\n'
(OUT/'Ton_ba_san_pham_theo_location.md').write_text(text,encoding='utf8')
