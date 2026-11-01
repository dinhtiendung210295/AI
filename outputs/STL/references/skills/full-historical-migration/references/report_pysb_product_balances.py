"""Native as-of-date quantity comparison for mapped migration products; no valuation."""
import json,runpy,socket,html
from pathlib import Path
ROOT=Path(__file__).resolve().parents[6];OUT=ROOT/'outputs/pysb-stock-migration-20261012'
H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/confirm_pysb_july_po_staging.py'))
def main():
 socket.setdefaulttimeout(120);manifest=json.loads((OUT/'execution-manifest.json').read_text(encoding='utf8'));mapping={int(k):v for k,v in manifest['maps']['product.product'].items()};allresults={}
 for version in ['v14-prod','v19-staging']:
  r=H['Reader'](ROOT/f'mcp-server-odoo/envs/{version}/.env');ids=list(mapping) if version=='v14-prod' else sorted(set(mapping.values()));result={}
  for period,cutoff in [('opening','2026-06-30 15:59:59'),('closing','2026-07-31 15:59:59')]:
   rows=[]
   for start in range(0,len(ids),300):rows+=r.call('product.product','read',[ids[start:start+300]],{'fields':['name','qty_available','uom_id'],'context':{'to_date':cutoff,'allowed_company_ids':[1],'force_company':1}})
   result[period]={x['id']:x for x in rows};print(version,period,len(rows),flush=True)
  allresults[version]=result
 rows=[]
 for s,t in mapping.items():
  source=allresults['v14-prod'];target=allresults['v19-staging'];so=source['opening'][s]['qty_available'];sc=source['closing'][s]['qty_available'];to=target['opening'][t]['qty_available'];tc=target['closing'][t]['qty_available']
  rows.append({'source_product':s,'target_product':t,'product':source['opening'][s]['name'],'source_unit':source['opening'][s]['uom_id'][1],'target_unit':target['opening'][t]['uom_id'][1],'source_opening':so,'target_opening':to,'opening_delta':to-so,'source_closing':sc,'target_closing':tc,'closing_delta':tc-sc,'source_july_net':sc-so,'target_july_net':tc-to,'july_net_delta':(tc-to)-(sc-so)})
 summary={'scope':'Mapped products only; never use as full-company stock coverage. Run scan_pysb_july_other_stock_coverage.py independently before and after migration.','products':len(rows),'opening_mismatch':sum(abs(x['opening_delta'])>0.00501 for x in rows),'closing_mismatch':sum(abs(x['closing_delta'])>0.00501 for x in rows),'july_net_mismatch':sum(abs(x['july_net_delta'])>0.00501 for x in rows),'note':'Native qty_available with to_date in source timezone Asia/Singapore (+08). Differences include opening balances and July transactions outside selected SO/PO/MO scope. No valuation compared.'}
 H['save'](OUT/'product-opening-closing-report.json',{'summary':summary,'rows':rows,'raw':allresults});print(json.dumps(summary,ensure_ascii=False),flush=True)
 fields=['product','source_unit','source_opening','target_opening','opening_delta','source_closing','target_closing','closing_delta','july_net_delta']
 table=''.join('<tr>'+''.join('<td>'+html.escape(str(x[k]))+'</td>' for k in fields)+'</tr>' for x in rows if abs(x['opening_delta'])>0.00501 or abs(x['closing_delta'])>0.00501)
 (OUT/'product-opening-closing-report.html').write_text('<!doctype html><meta charset="utf-8"><title>Pao Yeang – tồn số lượng tháng 7</title><style>body{font:14px Arial;margin:24px}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:6px}th{background:#edf5fa}</style><h1>Pao Yeang – tồn số lượng đầu/cuối tháng 7/2026</h1><p>Đọc báo cáo tồn theo ngày chuẩn Odoo. Chỉ đối chiếu số lượng trên các sản phẩm đã ánh xạ; không đối chiếu valuation. Chênh lệch bao gồm tồn đầu kỳ và giao dịch ngoài phạm vi SO/PO/MO đã chọn.</p><pre>'+html.escape(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre><table><tr>'+''.join('<th>'+k+'</th>' for k in fields)+'</tr>'+table+'</table>',encoding='utf8')
if __name__=='__main__':main()
