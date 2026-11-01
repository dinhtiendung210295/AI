"""Copy historical MyInvois metadata only, without sending or validating externally."""
from create_pysb_historical_invoice_drafts import Run
from inspect_pysb_historical_invoices import OUT
from execute_pysb_stock_migration import require,index,save
import json
def main():
 m=Run();source=json.loads((OUT/'einvoice-source-metadata.json').read_text(encoding='utf8'));fields=source['fields'];rows=source['records'];require(len(rows)==1057,'Unexpected e-invoice scope');ids=[m.j['documents'][str(s['id'])]['target_id'] for s in rows];before=m.b.read('account.move',ids,['state','date','invoice_date','amount_total','partner_id','currency_id']+fields);operation=m.j.setdefault('einvoice_reference_preservation',{'status':'intent','approved_by':'Bruce','purpose':'Preserve historical E-invoice reference from v14; no submission or external validation','before':before});m.persist()
 data=[[m.j['documents'][str(s['id'])]['target_id']]+[s[k] for k in fields] for s in rows];m.matrix('account.move',['.id']+fields,data,100)
 after=index(m.b.read('account.move',ids,['state','date','invoice_date','amount_total','partner_id','currency_id']+fields));old=index(before);require(all(all(after[t][k]==old[t][k] for k in ['state','date','invoice_date','amount_total','partner_id','currency_id']) for t in ids),'Commercial/posting data changed')
 mismatch=[]
 for s in rows:
  t=m.j['documents'][str(s['id'])]['target_id']
  for k in fields:
   if after[t][k]!=s[k]:mismatch.append({'source_id':s['id'],'target_id':t,'field':k})
 require(not mismatch,'E-invoice reference differs');operation.update(status='verified',documents=1057,with_uuid=sum(bool(s['x_submission_uid']) for s in rows),with_longid=sum(bool(s['x_my_einvoice_longid']) for s in rows),source_valid_without_uuid=sum(s['x_einvoice_state']=='valid' and not s['x_submission_uid'] for s in rows),external_submission_performed=False);m.persist();save(OUT/'einvoice-reference-reconciliation.json',{'summary':{k:v for k,v in operation.items() if k!='before'},'rows':[{'source_id':s['id'],'source_reference':m.j['documents'][str(s['id'])]['source_name'],'target_id':m.j['documents'][str(s['id'])]['target_id'],**{k:s[k] for k in fields}} for s in rows]});print(json.dumps({k:v for k,v in operation.items() if k!='before'}),flush=True)
if __name__=='__main__':main()
