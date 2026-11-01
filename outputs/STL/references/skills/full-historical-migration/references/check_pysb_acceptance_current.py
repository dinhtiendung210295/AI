"""Read-only current comparison of the user's migration acceptance checklist."""
import json,runpy,socket,html
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[6]; STOCK=ROOT/'outputs/pysb-stock-migration-20261012'; OUT=ROOT/'outputs/pysb-acceptance-20261014'
def load(p):return json.loads(p.read_text(encoding='utf8'))
def ix(rows):return {r['id']:r for r in rows}
def main():
 socket.setdefaulttimeout(120);OUT.mkdir(exist_ok=True)
 H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/confirm_pysb_july_po_staging.py'));a=H['Reader'](ROOT/'mcp-server-odoo/envs/v14-prod/.env');b=H['Reader'](ROOT/'mcp-server-odoo/envs/v19-staging/.env')
 assert b.db=='py19-staging-39654560';p=load(STOCK/'execution-manifest.json');j=load(STOCK/'execution-journal.json');dep=load(STOCK/'v14-prod-dependencies.json');snap=load(STOCK/'v14-prod-snapshot.json');report={'checked_utc':datetime.now(timezone.utc).isoformat(),'database':b.db,'company_id':1,'summary':{},'details':{}}
 for model,key,ids,fields,targetfields in [('sale.order','so',[r['id'] for r in dep['so']],['name','state','company_id'],None),('purchase.order','po',[r['id'] for r in dep['po']],['name','state','company_id'],None),('sale.order.line','sol',[r['id'] for r in snap['sol']],['order_id','display_type','product_uom_qty','qty_delivered','qty_invoiced'],None),('purchase.order.line','pol',[r['id'] for r in dep['pol']],['order_id','display_type','product_qty','qty_received','qty_invoiced'],None)]:
  mp={int(k):v for k,v in p['maps'][model].items()};s=ix(a.read(model,ids,fields));t=ix(b.read(model,[mp[i] for i in ids],fields));rows=[]
  for i,v in s.items():
   w=t[mp[i]];keys=[k for k in fields if k not in ['name','order_id','company_id','display_type']];diff={k:[v[k],w[k]] for k in keys if (abs(v[k]-w[k])>0.00501 if isinstance(v[k],(int,float)) and not isinstance(v[k],bool) else (v[k]!=w[k] and not(k=='state' and {v[k],w[k]}<=({'sale','done'} if key=='so' else {'purchase','done'}))))};rows.append({'source_id':i,'target_id':w['id'],'source':v,'target':w,'differences':diff})
  report['details'][key]=rows;report['summary'][key]={'count':len(rows),'mismatch':sum(bool(r['differences']) for r in rows),'source_states':dict(Counter(v.get('state') for v in s.values())) if key in ['so','po'] else {},'target_states':dict(Counter(v.get('state') for v in t.values())) if key in ['so','po'] else {}};print(key,report['summary'][key],flush=True)
 for model,key,fields in [('stock.picking','transfer',['name','state','company_id']),('mrp.production','mo',['name','state','product_qty','qty_produced','company_id']),('stock.move','stock_move',['state','product_uom_qty','company_id'])]:
  mp={int(k):v for k,v in j['maps'][model].items()};sf=fields+(['quantity_done'] if key=='stock_move' else []);tf=fields+(['quantity'] if key=='stock_move' else []);s=ix(a.read(model,list(mp),sf));t=ix(b.read(model,list(mp.values()),tf));rows=[]
  for i,v in s.items():
   w=t[mp[i]];diff={k:[v[k],w[k]] for k in fields if k not in ['name','company_id'] and (abs(v[k]-w[k])>0.00501 if isinstance(v[k],(int,float)) and not isinstance(v[k],bool) else v[k]!=w[k])}
   if key=='stock_move' and abs(v['quantity_done']-w['quantity'])>0.00501:diff['done_qty']=[v['quantity_done'],w['quantity']]
   rows.append({'source_id':i,'target_id':w['id'],'source':v,'target':w,'differences':diff})
  report['details'][key]=rows;report['summary'][key]={'mapped':len(rows),'source_done':sum(v['state']=='done' for v in s.values()),'target_done':sum(v['state']=='done' for v in t.values()),'mismatch':sum(bool(r['differences']) for r in rows)};print(key,report['summary'][key],flush=True)
 records={}
 for dirname in ['pysb-invoice-migration-20261013','pysb-invoice-july-supplement-20261014']:records.update(load(ROOT/'outputs'/dirname/'invoice-execution-journal.json')['documents'])
 fields=['name','state','move_type','company_id','amount_total','amount_untaxed','amount_tax'];s=ix(a.read('account.move',[int(k) for k in records],fields));t=ix(b.read('account.move',[r['target_id'] for r in records.values()],fields));rows=[];pairs=[pair for r in records.values() for pair in r['source_line_target_pairs']];lf=['quantity','price_unit','discount','price_subtotal','price_total'];sl=ix(a.read('account.move.line',[x['source_line'] for x in pairs],lf));tl=ix(b.read('account.move.line',[x['target_line'] for x in pairs],lf))
 for i,v in s.items():
  w=t[records[str(i)]['target_id']];diff={k:[v[k],w[k]] for k in ['state','move_type','amount_total','amount_untaxed','amount_tax'] if (abs(v[k]-w[k])>0.00501 if isinstance(v[k],(int,float)) else v[k]!=w[k])};rows.append({'source_id':i,'target_id':w['id'],'source':v,'target':w,'differences':diff})
 lines=[]
 for pair in pairs:
  v=sl[pair['source_line']];w=tl[pair['target_line']];lines.append({**pair,'source':v,'target':w,'differences':{k:[v[k],w[k]] for k in lf if abs(v[k]-w[k])> (0.000001 if k in ['price_unit','discount'] else 0.00501)}})
 report['details']['invoice']=rows;report['details']['invoice_lines']=lines;report['summary']['invoice']={'source_types_states':dict(Counter(v['move_type']+'/'+v['state'] for v in s.values())),'target_types_states':dict(Counter(v['move_type']+'/'+v['state'] for v in t.values())),'documents':len(rows),'document_mismatch':sum(bool(r['differences']) for r in rows),'lines':len(lines),'line_mismatch':sum(bool(r['differences']) for r in lines)};print('invoice',report['summary']['invoice'],flush=True)
 (OUT/'current-checklist.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 body='<meta charset="utf-8"><title>PYSB — Kiểm tra nghiệm thu</title><style>body{font:14px Arial;margin:24px}pre{white-space:pre-wrap}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:6px}</style><h1>Pao Yeang — Kiểm tra tiêu chí chuyển dữ liệu</h1><p>Đọc trực tiếp v14 prod và v19 staging; không sửa dữ liệu. Phạm vi theo ánh xạ đã chuyển, không phải toàn database. SO sale/done và PO purchase/done được coi là đã confirm.</p><pre>'+html.escape(json.dumps(report['summary'],ensure_ascii=False,indent=2))+'</pre>'
 for key,rows in report['details'].items():
  bad=[r for r in rows if r['differences']];body+='<h2>'+key+' — '+str(len(bad))+' dòng cần chú ý</h2><pre>'+html.escape(json.dumps(bad,ensure_ascii=False,indent=2))+'</pre>'
 (OUT/'PYSB_Acceptance_Check.html').write_text(body,encoding='utf8')
if __name__=='__main__':main()
