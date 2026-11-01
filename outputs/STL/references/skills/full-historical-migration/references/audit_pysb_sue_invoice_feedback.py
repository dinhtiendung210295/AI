"""Read-only independent Invoice/Bill audit. Offline by default; no mutation RPCs.

Compare complete July scope as well as the durable migration journals. Never import
Migration/Run: their initialization loads unrelated operational journals.
"""
from pathlib import Path
import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import re
import runpy
import socket

ROOT = Path(__file__).resolve().parents[6]
RUNS = ['pysb-invoice-migration-20261013', 'pysb-invoice-july-supplement-20261014']
DEFAULT = ROOT/'outputs/pysb-sue-invoice-review-20261016'
HELPER = ROOT/'.agents/skills/FC+TC/6-Data migration/so-po-migration/scripts/test_prepare_july_2026_so_po_migration.py'
MOVE_FIELDS = ['name','state','move_type','company_id','company_currency_id','partner_id','commercial_partner_id','invoice_user_id','currency_id','journal_id','invoice_date','date','invoice_date_due','invoice_origin','ref','amount_untaxed','amount_tax','amount_total','amount_total_signed','amount_total_in_currency_signed','invoice_currency_rate','invoice_line_ids','line_ids','write_date','create_date','write_uid','create_uid','x_studio_v14_refererce','x_studio_v14_reference_studio']

def load(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))

def save(p,d):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8')

def rid(v):
    return v[0] if isinstance(v,(list,tuple)) and v else v or False

def label(v):
    return v[1] if isinstance(v,(list,tuple)) and len(v)>1 else ''

def ix(rows):
    return {r['id']:r for r in rows}

def norm(v):
    return re.sub(r'\W','',str(v or '').casefold())

def money_equal(a,b,rounding=0.01):
    unit=Decimal(str(rounding or 0.01))
    return (Decimal(str(a))/unit).quantize(Decimal('1'),rounding=ROUND_HALF_UP)==(Decimal(str(b))/unit).quantize(Decimal('1'),rounding=ROUND_HALF_UP)

def user_equal(source,target):
    if not source or not target:return not source and not target
    # Login is unique within each database; compare cross-version identity, not IDs.
    a=str(source.get('login') or '').strip().casefold()
    b=str(target.get('login') or '').strip().casefold()
    if a and b:return a==b
    return None  # Matching display names alone is not identity evidence.

def signed_native(move):
    """Reconstruct signed invoice currency amount when old schema lacks a field."""
    if move['move_type'] not in {'out_invoice','in_invoice','out_refund','in_refund'}:
        raise ValueError('Only invoice/refund sign conventions supported')
    return move['amount_total'] * (-1 if move['move_type'] in {'in_invoice','out_refund'} else 1)

def history():
    rows={}; runs=[]
    for name in RUNS:
        path=ROOT/'outputs'/name
        manifest=load(path/'invoice-draft-manifest.json');journal=load(path/'invoice-execution-journal.json')
        for d in manifest['documents']:
            key=d['source_id']
            if key in rows:raise ValueError('Duplicate source in historical runs')
            rows[key]={'run':name,'manifest':d,'journal':journal['documents'][str(key)]}
        runs.append({'run':name,'documents':len(manifest['documents']),'types':dict(Counter(d['source']['move_type'] for d in manifest['documents'])),'july_types':dict(Counter(d['source']['move_type'] for d in manifest['documents'] if '2026-07-01'<=str(d['source']['invoice_date'])<='2026-07-31'))})
    return rows,runs

def collect(output):
    helper=runpy.run_path(str(HELPER))
    envs=[ROOT/'mcp-server-odoo/envs/v14-prod/.env',ROOT/'mcp-server-odoo/envs/v19-staging/.env']
    expected=[('http://175.145.85.151','paoyeang_live'),('https://py-staging.odoo.com','py19-staging-39654560')]
    for env,identity in zip(envs,expected):
        config=helper['load_env'](env)
        if (config['ODOO_URL'].rstrip('/'),config['ODOO_DB'])!=identity:
            raise RuntimeError('Environment identity differs from historical run; no live extraction')
    class ReadOnly(helper['OdooReader']):
        def call(self,model,method,args,kwargs=None):
            if method not in {'read','search_read','search_count','fields_get'}:
                raise RuntimeError('Read-only audit rejected RPC method '+method)
            return super().call(model,method,args,kwargs)
        def search_read(self,model,domain,fields,order='id asc'):
            result=[];offset=0
            while True:
                page=self.call(model,'search_read',[domain],{'fields':fields,'order':order,'offset':offset,'limit':500})
                result.extend(page)
                if len(page)<500:return result
                offset+=len(page)
    hist,_=history();data={'started_utc':datetime.now(timezone.utc).isoformat(),'sides':{}}
    for side,env in zip(['source','target'],envs):
        reader=ReadOnly(env)
        company=reader.read('res.company',[1],['name','currency_id','partner_id'])[0]
        if company['name']!='PAO YEANG SDN BHD':raise RuntimeError('Wrong company')
        def fields(model,wanted):
            schema=reader.call(model,'fields_get',[],{'attributes':['type','string','relation','selection']})
            return schema,[f for f in wanted if f in schema]
        schema,fs=fields('account.move',MOVE_FIELDS)
        domain=[['company_id','=',1],['move_type','in',['out_invoice','in_invoice']],['invoice_date','>=','2026-07-01'],['invoice_date','<=','2026-07-31'],['state','=','posted']]
        july=reader.search_read('account.move',domain,fs)
        ids=list(hist) if side=='source' else [r['journal']['target_id'] for r in hist.values()]
        records=ix(reader.read('account.move',ids,fs));records.update(ix(july))
        line_schema,linefs=fields('account.move.line',['move_id','name','display_type','account_id','product_id','quantity','price_unit','discount','price_subtotal','price_total','balance','debit','credit','amount_currency','currency_id','date_maturity','tax_ids','sale_line_ids','purchase_line_id'])
        lines=reader.read('account.move.line',sorted({i for r in records.values() for i in r['line_ids']}),linefs)
        masters={}
        for model,key,ids,wanted in [
            ('res.partner','partners',sorted({rid(r[k]) for r in records.values() for k in ['partner_id','commercial_partner_id'] if r.get(k)}),['name','ref','vat','parent_id','commercial_partner_id','active','write_date']),
            ('res.users','users',sorted({rid(r['invoice_user_id']) for r in records.values() if r.get('invoice_user_id')}),['name','login','active','partner_id']),
            ('res.currency','currencies',sorted({rid(r['currency_id']) for r in records.values()}|{rid(company['currency_id'])}),['name','rounding','active']),
            ('account.journal','journals',sorted({rid(r['journal_id']) for r in records.values()}),['name','code','type','currency_id'])]:
            _,mfs=fields(model,wanted);masters[key]=reader.read(model,ids,mfs)
        _,rfs=fields('res.currency.rate',['name','currency_id','company_id','rate','company_rate','inverse_company_rate'])
        rates=reader.search_read('res.currency.rate',[['currency_id','in',[r['id'] for r in masters['currencies']]],['name','<=','2026-09-30'],['company_id','in',[False,1]]],rfs)
        external=reader.search_read('ir.model.data',[['model','in',['account.move','res.partner','res.users','res.currency']],['module','ilike','v14']],['module','name','model','res_id']) if side=='target' else []
        data['sides'][side]={'database':reader.db,'company':company,'schema':schema,'line_schema':line_schema,'july_ids':[r['id'] for r in july],'records':list(records.values()),'lines':lines,'rates':rates,'external_ids':external,**masters,'extracted_utc':datetime.now(timezone.utc).isoformat()}
        # A partial extraction is never presented as a complete comparison.
        save(output/'partial-extraction.json',data)
        print(side+' extracted '+str(len(records))+' documents',flush=True)
    data['completed_utc']=datetime.now(timezone.utc).isoformat()
    save(output/'snapshot.json',data)
    return data

def compare(data):
    hist,runs=history();source=data['sides']['source'];target=data['sides']['target']
    ss,tt=ix(source['records']),ix(target['records'])
    su,tu=ix(source['users']),ix(target['users']);sc,tc=ix(source['currencies']),ix(target['currencies'])
    source_base=rid(source['company']['currency_id']);target_base=rid(target['company']['currency_id'])
    base_equal=sc[source_base]['name']==tc[target_base]['name']
    mapped={};reverse={}
    for e in target['external_ids']:
        m=re.match(r'^account_move_(\d+)(?:_|$)',e['name']) if e['model']=='account.move' else None
        if m:mapped.setdefault(int(m[1]),set()).add(e['res_id']);reverse.setdefault(e['res_id'],set()).add(int(m[1]))
    for sid,h in hist.items():mapped.setdefault(sid,set()).add(h['journal']['target_id'])
    rows=[]
    for sid in sorted(set(hist)|set(source['july_ids'])):
        s=ss.get(sid);h=hist.get(sid);matches=sorted(mapped.get(sid,set()))
        row={'source_id':sid,'target_ids':matches,'run':h['run'] if h else None,'in_july':sid in source['july_ids'],'differences':{},'unverified':[]}
        if not s:row['status']='missing_source';rows.append(row);continue
        row.update(source_name=s['name'],move_type=s['move_type'],source=s)
        if len(matches)!=1:row['status']='duplicate_target' if matches else 'missing_target';rows.append(row);continue
        t=tt.get(matches[0]);row['target_id']=matches[0]
        if not t:row['status']='target_not_extracted';rows.append(row);continue
        row.update(status='matched',target=t)
        def diff(k,a,b,ok):
            if ok is None:row['unverified'].append(k)
            elif not ok:row['differences'][k]={'source':a,'target':b}
        for k in ['state','move_type','invoice_date','date','invoice_date_due','invoice_origin','ref']:
            diff(k,s.get(k),t.get(k),s.get(k)==t.get(k))
        sround=sc[rid(s['currency_id'])]['rounding'];tround=tc[rid(t['currency_id'])]['rounding']
        for k in ['amount_untaxed','amount_tax','amount_total']:
            diff(k,s[k],t[k],money_equal(s[k],t[k],sround) if sround==tround else None)
        sn=sc[rid(s['currency_id'])]['name'];tn=tc[rid(t['currency_id'])]['name']
        # CNH -> CNY is recorded separately, never silently treated as equal.
        diff('currency',sn,tn,sn==tn)
        diff('amount_total_signed',s['amount_total_signed'],t['amount_total_signed'],money_equal(s['amount_total_signed'],t['amount_total_signed'],sc[source_base]['rounding']) if base_equal else None)
        if 'amount_total_in_currency_signed' in s and 'amount_total_in_currency_signed' in t:
            diff('amount_total_in_currency_signed',s['amount_total_in_currency_signed'],t['amount_total_in_currency_signed'],money_equal(s['amount_total_in_currency_signed'],t['amount_total_in_currency_signed'],sround))
        else:
            row['derived_source_signed_native']=signed_native(s)
            row['signed_native_method']='derived_from_source_move_type_and_amount_total; not original paper invoice'
            diff('derived_signed_native',signed_native(s),t.get('amount_total_in_currency_signed'),money_equal(signed_native(s),t['amount_total_in_currency_signed'],sround) if 'amount_total_in_currency_signed' in t else None)
        a=su.get(rid(s.get('invoice_user_id')));b=tu.get(rid(t.get('invoice_user_id')))
        diff('salesperson',label(s.get('invoice_user_id')),label(t.get('invoice_user_id')),user_equal(a,b))
        diff('partner_name',label(s['partner_id']),label(t['partner_id']),label(s['partner_id'])==label(t['partner_id']))
        diff('partner_name_ignore_case',label(s['partner_id']),label(t['partner_id']),label(s['partner_id']).strip().casefold()==label(t['partner_id']).strip().casefold())
        if s['move_type']=='out_invoice':row['unverified'].append('approved_sequence_policy_required')
        if h:
            d=h['manifest'];expected=d['header']['partner_id']
            diff('partner_mapping',expected,rid(t['partner_id']),expected==rid(t['partner_id']))
            row['historical_source']=d['source'];row['historical_target_after_create']=h['journal'].get('after',{})
            row['manifest_header']=d['header']
            row['historical_source_changed_fields']={k:[d['source'].get(k),s.get(k)] for k in ['amount_total','amount_total_signed','invoice_user_id','partner_id','currency_id','write_date'] if k in d['source'] and d['source'][k]!=s.get(k)}
        else:row['unverified'].append('no_manifest_partner_mapping')
        rows.append(row)
    used={r['target_id'] for r in rows if r.get('target_id')}
    result={'source_database':source['database'],'target_database':target['database'],'source_company':source['company'],'target_company':target['company'],'completed_utc':data.get('completed_utc'),'runs':runs,'summary':{'historical_documents':len(hist),'source_july_documents':len(source['july_ids']),'target_july_documents':len(target['july_ids']),'pair_states':dict(Counter(r['status'] for r in rows)),'differences_all':dict(Counter(k for r in rows for k in r['differences'])),'differences_july':dict(Counter(k for r in rows if r['in_july'] for k in r['differences'])),'differences_july_by_type':{typ:dict(Counter(k for r in rows if r['in_july'] and r.get('move_type')==typ for k in r['differences'])) for typ in ['out_invoice','in_invoice']},'july_unmatched_target_ids':sorted(set(target['july_ids'])-used),'sue_exact_sets_verified':False,'original_invoices_verified':False},'rows':rows}
    return result

def compare_sue_workbook(path,result):
    """Extract existing workbook only. Never save or recalculate the source file."""
    from openpyxl import load_workbook
    wb=load_workbook(path,data_only=True,read_only=True)
    formulas=load_workbook(path,data_only=False,read_only=True)
    source={};target={};issues=[]
    for cells in wb['v14'].iter_rows(min_row=2,values_only=True):
        if not cells[0]:continue
        if cells[0] in source:raise ValueError('Duplicate v14 reference in Sue workbook')
        source[cells[0]]={'partner':cells[1],'invoice_date':cells[3],'due_date':cells[5],'origin':cells[6],'ref':cells[7],'total_signed':cells[12]}
    for number,cells in enumerate(wb['v19'].iter_rows(min_row=4,values_only=True),4):
        if not cells[1]:continue
        ref=cells[1]
        if ref in target:raise ValueError('Duplicate v19 source reference in Sue workbook')
        target[ref]={'sheet_row':number,'name':cells[0],'partner':cells[2],'total_in_currency_signed':cells[8],'total_signed':cells[9],'cached_comparisons':dict(zip(['reference','partner','invoice_date','due_date','origin','ref','total_signed'],cells[15:22]))}
    live={r['source_name']:r for r in result['rows'] if r.get('move_type')=='in_invoice' and r.get('in_july')}
    value_refs=[]
    for number,cells in enumerate(wb['Value not tie'].iter_rows(min_row=4,values_only=True),4):
        if not cells[0]:continue
        ref=cells[0];value_refs.append(ref);s=source.get(ref);t=target.get(ref);r=live.get(ref)
        issues.append({'source_reference':ref,'sue_cell':f"'Value not tie'!A{number}:F{number}",'source_sheet_total':s['total_signed'] if s else None,'target_sheet_total':t['total_signed'] if t else None,'cached_lookup':cells[4],'cached_variance':cells[5],'formula_lookup':formulas['Value not tie'].cell(number,5).value,'live_source_id':r.get('source_id') if r else None,'live_target_id':r.get('target_id') if r else None,'live_source_total_signed':r['source']['amount_total_signed'] if r else None,'live_target_total_signed':r['target']['amount_total_signed'] if r else None,'live_matches_sue_values':bool(r and s and t and money_equal(r['source']['amount_total_signed'],s['total_signed']) and money_equal(r['target']['amount_total_signed'],t['total_signed']))})
    foreign=[]
    for number,cells in enumerate(wb['foreign bills to confirm'].iter_rows(min_row=4,values_only=True),4):
        if cells[1]:foreign.append({'sheet_row':number,'source_reference':cells[1],'target_name':cells[0],'total_in_currency_signed':cells[3],'total_signed':cells[4]})
    independent={r['source_name'] for r in live.values() if 'amount_total_signed' in r['differences']}
    outcome={'file':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'source_rows':len(source),'target_rows':len(target),'coverage_matches_live':set(source)==set(live)==set(target),'value_not_tie_rows':len(value_refs),'exact_bill_mismatch_set_matches':set(value_refs)==independent,'all_nine_values_match_live':all(r['live_matches_sue_values'] for r in issues),'issues':issues,'foreign_bills_to_confirm':foreign,'foreign_count':len(foreign),'original_invoice_currency_confirmed':False,'note':'X compares native to company currency; FALSE identifies a foreign bill, not automatically an error.'}
    wb.close();formulas.close()
    return outcome

def collect_details(data,output):
    """Small supplementary read of current target defaults, rates and sequence."""
    helper=runpy.run_path(str(HELPER));env=ROOT/'mcp-server-odoo/envs/v19-staging/.env'
    config=helper['load_env'](env)
    if (config['ODOO_URL'].rstrip('/'),config['ODOO_DB'])!=('https://py-staging.odoo.com','py19-staging-39654560'):
        raise RuntimeError('Wrong details environment')
    class ReadOnly(helper['OdooReader']):
        def call(self,model,method,args,kwargs=None):
            if method not in {'read','search_read','fields_get'}:raise RuntimeError('Forbidden RPC')
            return super().call(model,method,args,kwargs)
    reader=ReadOnly(env)
    if reader.read('res.company',[1],['name'])[0]['name']!='PAO YEANG SDN BHD':raise RuntimeError('Wrong company')
    ids={rid(r[k]) for r in data['sides']['target']['records'] for k in ['partner_id','commercial_partner_id'] if r.get(k)}
    partners=reader.read('res.partner',sorted(ids),['name','parent_id','commercial_partner_id','user_id','write_date'])
    users=reader.search_read('res.users',[],['name','login','active'])
    foreign=[r['id'] for r in data['sides']['target']['records'] if rid(r['currency_id'])!=34]
    schema=data['sides']['target']['schema']
    fields=[k for k in ['name','invoice_date','date','invoice_currency_rate','expected_currency_rate','x_foreign_to_company_rate','x_rate_sync_lock','amount_total','amount_total_signed','write_date','create_date'] if k in schema]
    moves=reader.read('account.move',foreign,fields)
    seqschema=reader.call('account.journal','fields_get',[],{'attributes':['type']})
    journals=reader.read('account.journal',sorted({rid(r['journal_id']) for r in data['sides']['target']['records']}),[k for k in ['name','code','type','sequence_override_regex','refund_sequence'] if k in seqschema])
    result={'database':reader.db,'extracted_utc':datetime.now(timezone.utc).isoformat(),'partners':partners,'users':users,'foreign_moves':moves,'journals':journals}
    save(output/'supplemental-details.json',result)
    print('Supplementary read complete; no Odoo writes.')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--live',action='store_true',help='Only authenticated read RPCs; writes a new local immutable snapshot')
    ap.add_argument('--evidence-dir',type=Path,default=DEFAULT/'live')
    ap.add_argument('--output-dir',type=Path,required=True)
    ap.add_argument('--sue-workbook',type=Path,help='Read-only comparison of Sue Bill workbook; no source edits')
    ap.add_argument('--details',action='store_true',help='Supplement existing snapshot with small target-only read; no mutation')
    args=ap.parse_args();socket.setdefaulttimeout(45)
    if args.live and (args.output_dir/'snapshot.json').exists():ap.error('Snapshot exists: choose a new output directory')
    try:
        if args.details:
            if args.live:ap.error('--details and --live are separate extraction modes')
            collect_details(load(args.evidence_dir/'snapshot.json'),args.output_dir)
            return 0
        data=collect(args.output_dir) if args.live else load(args.evidence_dir/'snapshot.json')
        result=compare(data);save(args.output_dir/'claim-results.json',result)
        if args.sue_workbook:
            sue=compare_sue_workbook(args.sue_workbook,result)
            save(args.output_dir/'sue-workbook-comparison.json',sue)
            result['summary']['sue_exact_bill_set_verified']=sue['exact_bill_mismatch_set_matches'] and sue['all_nine_values_match_live']
            save(args.output_dir/'claim-results.json',result)
        print(json.dumps(result['summary'],ensure_ascii=False,indent=2))
        return 1 if result['summary']['differences_all'] or any(r['status']!='matched' for r in result['rows']) else 2 if any(r['unverified'] for r in result['rows']) else 0
    except Exception as e:
        # Do not expose raw XML-RPC exceptions: some contain credential-bearing request data.
        save(args.output_dir/'audit-error.json',{'error_type':type(e).__name__,'stage':'read_only_audit','complete':False})
        print('Audit incomplete: '+type(e).__name__+'. See audit-error.json; no Odoo writes.')
        return 2

if __name__=='__main__':
    raise SystemExit(main())
