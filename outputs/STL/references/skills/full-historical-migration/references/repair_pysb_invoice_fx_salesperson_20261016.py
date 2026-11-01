"""Incident preflight and authorized salesperson repair; staging only."""
from pathlib import Path
import runpy,json,socket,argparse
ROOT=Path(__file__).resolve().parents[6]
OUT=ROOT/'outputs/pysb-sue-invoice-review-20261016/fx-salesperson-repair'
OUT.mkdir(exist_ok=True)
def save(n,d): (OUT/n).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8')
def rid(x): return x[0] if x else False
socket.setdefaulttimeout(90)
a=argparse.ArgumentParser();a.add_argument('--apply-salesperson',action='store_true');a.add_argument('--apply-fx',action='store_true');a.add_argument('--apply-fx-outside-july',action='store_true');args=a.parse_args()
if sum([args.apply_salesperson,args.apply_fx,args.apply_fx_outside_july])>1:raise RuntimeError('Choose only one write mode')
if args.apply_salesperson and (OUT/'salesperson-journal.json').exists():raise RuntimeError('Existing salesperson journal: inspect and reconcile; do not repeat writes')
if args.apply_fx and (OUT/'fx-journal.json').exists():raise RuntimeError('Existing FX journal: inspect and reconcile; do not repeat writes')
if args.apply_fx_outside_july and (OUT/'fx-outside-july-journal.json').exists():raise RuntimeError('Existing outside-July journal: inspect and reconcile; do not repeat writes')
audit=runpy.run_path(str(Path(__file__).with_name('audit_pysb_sue_invoice_feedback.py')))
h=runpy.run_path(str(audit['HELPER']));readers=[]
for env,url,db in [('v14-prod','http://175.145.85.151','paoyeang_live'),('v19-staging','https://py-staging.odoo.com','py19-staging-39654560')]:
 p=ROOT/f'mcp-server-odoo/envs/{env}/.env';cfg=h['load_env'](p)
 assert (cfg['ODOO_URL'].rstrip('/'),cfg['ODOO_DB'])==(url,db)
 readers.append(h['OdooReader'](p))
s,t=readers;hist,_=audit['history']()
fields=['name','state','company_id','move_type','invoice_date','currency_id','amount_total','amount_total_signed','invoice_user_id','line_ids','invoice_line_ids','payment_state','invoice_origin']
sm={x['id']:x for x in s.read('account.move',list(hist),fields)}
tm={x['id']:x for x in t.read('account.move',[x['journal']['target_id'] for x in hist.values()],fields+['invoice_currency_rate','x_foreign_to_company_rate','restrict_mode_hash_table','secured'])}
su={x['id']:x for x in s.search_read('res.users',[],['name','login','active'])}
tu=t.search_read('res.users',[],['name','login','active']);bylogin={x['login'].casefold():x for x in tu}
siti=[x for x in tu if x['name'].strip().casefold()=='siti' and x['active']];assert len(siti)==1,siti
def mapped(uid):
 if not uid:return False
 u=su[uid];return siti[0]['id'] if 'warehouse' in (u['login']+' '+u['name']).casefold() else bylogin[u['login'].casefold()]['id']
fx=[];sales=[];so=[]
for sid,histrow in hist.items():
 src=sm[sid];dst=tm[histrow['journal']['target_id']]
 assert rid(src['company_id'])==rid(dst['company_id'])==1
 if abs(src['amount_total_signed']-dst['amount_total_signed'])>0.011:
  fx.append({'source':src,'target':dst,'desired_invoice_currency_rate':abs(src['amount_total']/src['amount_total_signed'])})
 if src['move_type']=='out_invoice' and mapped(rid(src['invoice_user_id']))!=rid(dst['invoice_user_id']):
  sales.append({'source':src,'target':dst,'desired_user_id':mapped(rid(src['invoice_user_id']))})
# Check actual SO relationships on both databases, not origin text alone.
for row in sales:
 linked=[]
 for r,m in [(s,row['source']),(t,row['target'])]:
  lines=r.read('account.move.line',m['invoice_line_ids'],['sale_line_ids'])
  lids=sorted({i for l in lines for i in l['sale_line_ids']})
  ol=r.read('sale.order.line',lids,['order_id']) if lids else []
  ids=sorted({rid(l['order_id']) for l in ol})
  linked.append(r.read('sale.order',ids,['name','user_id','company_id','state']) if ids else [])
 srcorders,dstorders=linked
 row['source_orders']=srcorders;row['target_orders']=dstorders
 for dst in dstorders:
  matches=[x for x in srcorders if x['name']==dst['name']]
  if len(matches)!=1:
   so.append({'target':dst,'blocked':'SO name mapping not unique','source_orders':srcorders});continue
  src=matches[0];desired=mapped(rid(src['user_id']))
  so.append({'source':src,'target':dst,'desired_user_id':desired,'needs_write':desired!=rid(dst['user_id'])})
schema=t.call('account.move','fields_get',[],{'attributes':['type','readonly','store','help']})
save('fx-outside-july-preflight.json' if args.apply_fx_outside_july else ('fx-preflight.json' if args.apply_fx else ('preflight.json' if not (OUT/'preflight.json').exists() else 'latest-preflight.json')),{'fx':fx,'salesperson':sales,'sale_orders':so,'target_users':tu,'rate_schema':{k:v for k,v in schema.items() if 'rate' in k}})
print(json.dumps({'fx_count':len(fx),'fx_july':sum(x['source']['invoice_date'].startswith('2026-07') for x in fx),'fx_types':[x['source']['move_type'] for x in fx],'salesperson_count':len(sales),'so_checks':len(so),'so_changes':sum(x.get('needs_write',False) for x in so)},ensure_ascii=False),flush=True)
if args.apply_salesperson:
 journal=[]
 jobs=[('account.move',x['target'],'invoice_user_id',x['desired_user_id']) for x in sales]
 unique={x['target']['id']:x for x in so if x.get('needs_write')}
 jobs += [('sale.order',x['target'],'user_id',x['desired_user_id']) for x in unique.values()]
 for model,before,field,value in jobs:
  assert rid(before['company_id'])==1
  now=t.read(model,[before['id']],[field,'company_id'])[0];assert now[field]==before[field]
  entry={'model':model,'id':before['id'],'name':before['name'],'before':before,'values':{field:value},'status':'intent'}
  journal.append(entry);save('salesperson-journal.json',journal)
  t.call(model,'write',[[before['id']],{field:value}])
  after=t.read(model,[before['id']],list(before.keys()))[0]
  assert rid(after[field])==value
  if model=='account.move':
   for k in ['state','name','amount_total','amount_total_signed','currency_id']:assert after[k]==before[k]
  entry.update(status='verified',after=after);save('salesperson-journal.json',journal)
 print('Verified salesperson writes:',len(journal))
if args.apply_fx or args.apply_fx_outside_july:
 journal_name='fx-outside-july-journal.json' if args.apply_fx_outside_july else 'fx-journal.json'
 if args.apply_fx_outside_july:
  previous=json.loads((OUT/'final-verification.json').read_text(encoding='utf8'))['remaining_fx_outside_july']
  expected_ids={x['source']['id'] for x in previous}
  assert len(expected_ids)==9
  selected=[x for x in fx if x['source']['id'] in expected_ids]
  assert len(selected)==9 and all('2026-08-01'<=x['source']['invoice_date']<='2026-09-30' for x in selected)
 else:selected=[x for x in fx if x['source']['invoice_date'].startswith('2026-07')]
 journal=[]
 for row in sorted(selected,key=lambda x:x['source']['id']):
  src,dst=row['source'],row['target']
  assert src['move_type']==dst['move_type']=='in_invoice'
  assert dst['state']=='posted' and dst['payment_state']=='not_paid' and not dst['secured']
  rates=s.search_read('res.currency.rate',[['currency_id','=',rid(src['currency_id'])],['company_id','in',[False,1]],['name','<=',src['invoice_date']]],['name','rate','company_id'],order='name desc,id desc')
  rate=rates[0]['rate'];assert rate>0
  assert abs(abs(src['amount_total']/rate)-abs(src['amount_total_signed']))<0.03
  linefields=['display_type','account_id','product_id','quantity','price_unit','discount','tax_ids','amount_currency','balance','debit','credit','reconciled','matched_debit_ids','matched_credit_ids']
  beforelines=t.read('account.move.line',dst['line_ids'],linefields)
  assert all(not x['reconciled'] and not x['matched_debit_ids'] and not x['matched_credit_ids'] for x in beforelines)
  current=t.read('account.move',[dst['id']],fields+['invoice_currency_rate','x_foreign_to_company_rate','secured'])[0]
  for k in ['state','amount_total','amount_total_signed','invoice_currency_rate']:assert current[k]==dst[k]
  vals={'invoice_currency_rate':rate,'x_foreign_to_company_rate':1/rate}
  entry={'source':src,'before':current,'before_lines':beforelines,'rate_evidence':rates[0],'values':vals,'status':'intent'}
  journal.append(entry);save(journal_name,journal)
  # Native ORM recalculates journal balances while preserving the posted document.
  t.call('account.move','write',[[dst['id']],vals])
  after=t.read('account.move',[dst['id']],list(current.keys()))[0]
  lines=t.read('account.move.line',after['line_ids'],linefields)
  entry.update(after=after,after_lines=lines,status='readback');save(journal_name,journal)
  assert abs(after['amount_total_signed']-src['amount_total_signed'])<0.011,(src['name'],after['amount_total_signed'],src['amount_total_signed'])
  for k in ['name','state','currency_id','amount_total','invoice_date','invoice_user_id','invoice_line_ids','line_ids','payment_state']:assert after[k]==current[k],k
  assert abs(sum(x['balance'] for x in lines))<0.005
  bi={x['id']:x for x in beforelines}
  for line in lines:
   for k in ['account_id','product_id','quantity','price_unit','discount','tax_ids','amount_currency']:assert line[k]==bi[line['id']][k],(line['id'],k)
  entry['status']='verified';save(journal_name,journal)
  print('Verified FX:',src['name'],flush=True)
 print('Verified FX writes:',len(journal))
if not args.apply_fx and not args.apply_salesperson and not args.apply_fx_outside_july and (OUT/'fx-journal.json').exists():
 wb=json.loads((OUT.parent/'offline/sue-workbook-comparison.json').read_text(encoding='utf8'))
 originals=json.loads((OUT/'preflight.json').read_text(encoding='utf8'))
 foreign=[]
 for item in wb['foreign_bills_to_confirm']:
  candidates=[(sid,h) for sid,h in hist.items() if sm[sid]['name']==item['source_reference']]
  assert len(candidates)==1,item
  sid,histrow=candidates[0];src=sm[sid];dst=tm[histrow['journal']['target_id']]
  foreign.append({'source':src,'target':dst,'native_equal':abs(src['amount_total']-dst['amount_total'])<0.005,'myr_equal':abs(src['amount_total_signed']-dst['amount_total_signed'])<0.011})
 assert len(foreign)==15 and all(x['native_equal'] and x['myr_equal'] for x in foreign)
 orders=[]
 for row in originals['sale_orders']:
  if 'blocked' in row:orders.append(row);continue
  actual=t.read('sale.order',[row['target']['id']],['name','user_id','company_id','state'])[0]
  assert rid(actual['user_id'])==row['desired_user_id']
  orders.append({'source':row['source'],'target':actual,'matches':True})
 for invoice in originals['salesperson']:
  if invoice['target_orders'] or not invoice['source_orders']:continue
  for source_order in invoice['source_orders']:
   found=t.search_read('sale.order',[['company_id','=',1],['name','=',source_order['name']]],['name','user_id','company_id','state'])
   if not found:
    import re
    xids=t.search_read('ir.model.data',[['model','=','sale.order'],['name','ilike',str(source_order['id'])]],['module','name','res_id'])
    ids=sorted({x['res_id'] for x in xids if re.search(r'(?:^|_)'+str(source_order['id'])+r'(?:_|$)',x['name'])})
    found=t.read('sale.order',ids,['name','user_id','company_id','state']) if ids else []
   if not found:
    orders.append({'source':source_order,'target':None,'matches':None,'invoice_line_link_missing':True,'source_invoice':invoice['source']['name'],'exception':'No target SO found by exact name or source External ID'})
    continue
   assert len(found)==1,(source_order,found)
   assert rid(found[0]['user_id'])==mapped(rid(source_order['user_id']))
   orders.append({'source':source_order,'target':found[0],'matches':True,'invoice_line_link_missing':True,'source_invoice':invoice['source']['name']})
 assert not sales
 save('final-verification.json',{'foreign_bills_15':foreign,'sale_orders':orders,'salesperson_remaining':sales,'remaining_fx_outside_july':fx,'original_invoices':originals['salesperson']})
 print('Final verified: 15 foreign bills,',len(orders),'SO checks; no remaining invoice salesperson differences')
