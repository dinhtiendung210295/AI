"""Isolated July-date supplement reusing verified invoice tools, never old outputs."""
from pathlib import Path
import json,sys,re
ROOT=Path(__file__).resolve().parents[6]
import inspect_pysb_historical_invoices as inspection
OUT=ROOT/'outputs/pysb-invoice-july-supplement-20261014'
inspection.OUT=OUT
def run_script(filename,replacements=()):
 code=(Path(__file__).resolve().parent/filename).read_text(encoding='utf8')
 for old,new in replacements:
  assert old in code,old;code=code.replace(old,new)
 exec(compile(code,filename,'exec'),{'__name__':'__main__','__file__':str(Path(__file__).resolve().parent/filename)})
def main():
 phase=sys.argv[1];sys.argv=sys.argv[1:]
 if phase=='inspect':
  from execute_pysb_stock_migration import Migration,save
  m=Migration();old=json.loads((ROOT/'outputs/pysb-invoice-migration-20261013/invoice-execution-journal.json').read_text(encoding='utf8'));scope=m.a.search_read('account.move',[['company_id','=',1],['move_type','in',['out_invoice','in_invoice']],['invoice_date','>=','2026-07-01'],['invoice_date','<=','2026-07-31']],['name','move_type','state','invoice_date']);ids=[s['id'] for s in scope if s['state']=='posted' and str(s['id']) not in old['documents']];OUT.mkdir(exist_ok=True);assert not (OUT/'invoice-preflight-snapshot.json').exists(),'Existing immutable snapshot; use next phase';save(OUT/'july-source-coverage.json',{'all_july_documents':scope,'already_migrated_source_ids':[s['id'] for s in scope if str(s['id']) in old['documents']],'additional_source_ids':ids,'excluded_cancelled':[s for s in scope if s['state']=='cancel']})
  code=(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/inspect_pysb_historical_invoices.py').read_text(encoding='utf8');oldline="ids=sorted({i for x in so+po for i in x['invoice_ids']})";assert oldline in code;code=code.replace(oldline,'ids='+repr(ids)).replace("OUT=ROOT/'outputs/pysb-invoice-migration-20261013'","OUT=ROOT/'outputs/pysb-invoice-july-supplement-20261014'");exec(compile(code,'<july-supplement-inspect>','exec'),{'__name__':'__main__','__file__':str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/inspect_pysb_historical_invoices.py')});d=json.loads((OUT/'invoice-preflight-snapshot.json').read_text(encoding='utf8'));save(OUT/'invoice-order-scope.json',{'source_moves':d['source_moves'],'scope':'Additional July Invoice/Bill regardless of order links, excluding prior migrated ids'})
 elif phase=='prepare':run_script('prepare_pysb_historical_invoices.py')
 elif phase=='create':run_script('create_pysb_historical_invoice_drafts.py')
 elif phase=='post':
  n=sum(not d['errors'] for d in json.loads((OUT/'invoice-draft-manifest.json').read_text(encoding='utf8'))['documents']);run_script('post_pysb_historical_invoices.py',[("docs=manifest['documents'];require","docs=[d for d in manifest['documents'] if not d['errors']];require"),('len(docs)==1057','len(docs)=='+str(n)),('1057-len(final)',str(n)+'-len(final)'),('len(final)<1057','len(final)<'+str(n))])
 elif phase=='einvoice':
  from create_pysb_historical_invoice_drafts import Run
  from execute_pysb_stock_migration import save
  m=Run();d=json.loads((OUT/'invoice-draft-manifest.json').read_text(encoding='utf8'));fields=['x_submission_uid','x_my_einvoice_longid','x_my_einvoice_link_to_portal','x_validation_time','x_einvoice_state'];rows=m.a.read('account.move',[x['source_id'] for x in d['documents'] if str(x['source_id']) in m.j['documents']],fields);save(OUT/'einvoice-source-metadata.json',{'fields':fields,'records':rows});n=len(rows);run_script('preserve_pysb_einvoice_reference.py',[('len(rows)==1057','len(rows)=='+str(n)),('documents=1057','documents='+str(n))])
 else:raise ValueError(phase)
if __name__=='__main__':main()
