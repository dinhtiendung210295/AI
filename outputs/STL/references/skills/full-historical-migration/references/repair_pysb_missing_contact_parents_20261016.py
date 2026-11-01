"""Incident-specific repair of empty parents from the 28 July import; staging only."""
import argparse,json,runpy,re,socket
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[6]
OUT=ROOT/'outputs/pysb-sue-invoice-review-20261016/contact-parent-repair'
def save(name,value):
 OUT.mkdir(parents=True,exist_ok=True)
 (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
def rid(v):return v[0] if isinstance(v,list) and v else v or False
def main():
 p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');args=p.parse_args()
 socket.setdefaulttimeout(60)
 h=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/so-po-migration/scripts/test_prepare_july_2026_so_po_migration.py'))
 readers=[]
 for env,url,db in [('v14-prod','http://175.145.85.151','paoyeang_live'),('v19-staging','https://py-staging.odoo.com','py19-staging-39654560')]:
  path=ROOT/f'mcp-server-odoo/envs/{env}/.env';c=h['load_env'](path)
  assert (c['ODOO_URL'].rstrip('/'),c['ODOO_DB'])==(url,db),'Wrong environment'
  readers.append(h['OdooReader'](path))
 a,b=readers
 assert b.read('res.company',[1],['name'])[0]['name']=='PAO YEANG SDN BHD'
 rows=json.loads((OUT.parent/'import-empty-parent-rows.json').read_text(encoding='utf8'))
 fs=['name','active','parent_id','commercial_partner_id','company_id','is_company','write_date','user_id','vat','street','street2','city','zip','country_id','state_id','email','phone','property_payment_term_id','property_supplier_payment_term_id']
 plan=[]
 for row in rows:
  sid=int(re.search(r'res_partner_(\d+)_',row['source_external_id'])[1]);spid=int(re.search(r'res_partner_(\d+)_',row['parent_source'])[1])
  try:s=a.read('res.partner',[sid],['name','parent_id','company_id'])[0]
  except Exception as exc:
   plan.append({'row':row['row'],'source_id':sid,'target_id':None,'status':'source_read_unavailable','error_type':type(exc).__name__});continue
  item={'row':row['row'],'source':s,'source_parent_expected':spid}
  def lookup(ex):
   module,name=('v14_v2_'+ex).split('.',1)
   hits=b.search_read('ir.model.data',[['model','=','res.partner'],['module','=',module],['name','=',name]],['res_id'])
   return hits[0]['res_id'] if len(hits)==1 else None
  tid=lookup(row['source_external_id']);pid=lookup(row['parent_source']);item.update(target_id=tid,parent_id=pid)
  if rid(s['parent_id'])!=spid or not tid or not pid:item['status']='mapping_or_source_conflict'
  else:
   t=b.read('res.partner',[tid],fs)[0];parent=b.read('res.partner',[pid],fs)[0];item.update(before=t,parent=parent)
   if rid(t['parent_id'])==pid:item['status']='already_correct'
   elif t['parent_id']:item['status']='existing_parent_conflict'
   elif tid==pid or rid(t['company_id']) not in [False,1] or rid(parent['company_id']) not in [False,1] or not t['active'] or not parent['active']:item['status']='scope_or_active_conflict'
   else:item['status']='ready'
  plan.append(item)
 save('preflight.json',plan)
 print(json.dumps({'preflight':{status:sum(x['status']==status for x in plan) for status in sorted({x['status'] for x in plan})}},ensure_ascii=False),flush=True)
 if not args.apply:return
 journalpath=OUT/'journal.json';journal=json.loads(journalpath.read_text(encoding='utf8')) if journalpath.exists() else []
 for item in sorted(plan,key=lambda x:x['target_id']!=106228):
  if item['status']!='ready':continue
  tid,pid=item['target_id'],item['parent_id']
  current=b.read('res.partner',[tid],fs)[0]
  if current['parent_id']:raise RuntimeError('State changed: rerun preflight')
  op={'target_id':tid,'parent_id':pid,'before':current,'intended_values':{'parent_id':pid},'started_utc':datetime.now(timezone.utc).isoformat(),'status':'intent'};journal.append(op);save('journal.json',journal)
  try:b.call('res.partner','write',[[tid],{'parent_id':pid}])
  except Exception:
   op['status']='rpc_error_readback_required';save('journal.json',journal)
   actual=b.read('res.partner',[tid],fs)[0]
   if rid(actual['parent_id'])!=pid:raise RuntimeError('Write not confirmed; no retry')
  actual=b.read('res.partner',[tid],fs)[0];op['after']=actual
  op['changed_fields']={k:{'before':current.get(k),'after':actual.get(k)} for k in fs if current.get(k)!=actual.get(k)}
  assert rid(actual['parent_id'])==pid,'Parent readback mismatch'
  assert rid(actual['commercial_partner_id'])==rid(item['parent']['commercial_partner_id']),'Commercial partner mismatch'
  op['status']='verified';save('journal.json',journal)
  print(json.dumps({'verified':tid,'parent_id':pid,'changed_fields':list(op['changed_fields'])}),flush=True)
 final=b.read('res.partner',[x['target_id'] for x in plan if x.get('target_id')],fs);save('final-readback.json',final)
 print('COMPLETE',flush=True)
if __name__=='__main__':main()
