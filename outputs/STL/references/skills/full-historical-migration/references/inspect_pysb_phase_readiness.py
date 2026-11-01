"""M0: source dependency closure and full commercial readback; never writes ERP."""
import argparse
import hashlib
import json
import runpy
from collections import Counter,defaultdict
from datetime import datetime,timezone,timedelta
from decimal import Decimal,ROUND_HALF_UP
from pathlib import Path

BASE=Path(__file__).parent
I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'))

def rid(value):return value[0] if isinstance(value,(list,tuple)) and value else value or False
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf8')).hexdigest()
def load(path):return json.loads(path.read_text(encoding='utf8'))
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8');temp.replace(path)

def build_scope(frozen_moves,frozen_invoices,source_order_lines,mappings):
    """source_order_lines contains invoice lines plus complete referenced SOL/POL."""
    sale=defaultdict(list);purchase=defaultdict(list)
    for move in frozen_moves:
        for field,store in [('sale_line_id',sale),('purchase_line_id',purchase)]:
            if move.get(field):store[rid(move[field])].append({'model':'stock.move','id':move['id']})
    invoices={x['id'] for x in frozen_invoices}
    for line in source_order_lines['account.move.line']:
        if rid(line.get('move_id')) not in invoices:continue
        for sid in line.get('sale_line_ids',[]):sale[sid].append({'model':'account.move.line','id':line['id'],'invoice':rid(line['move_id'])})
        if line.get('purchase_line_id'):purchase[rid(line['purchase_line_id'])].append({'model':'account.move.line','id':line['id'],'invoice':rid(line['move_id'])})
    result={};missing=[]
    for model,refs in [('sale.order',sale),('purchase.order',purchase)]:
        lines={x['id']:x for x in source_order_lines[model+'.line']};orders={}
        for lid,origins in refs.items():
            row=lines.get(lid)
            if not row or not row.get('order_id'):missing.append({'model':model+'.line','source_line':lid,'origins':origins});continue
            sid=rid(row['order_id']);item=orders.setdefault(sid,{'source_id':sid,'source_line_ids':[],'origins':[],'mapped_target':mappings.get(model,{}).get(sid)})
            item['source_line_ids'].append(lid);item['origins'].extend(origins)
        result[model]=[dict(x,source_line_ids=sorted(x['source_line_ids'])) for _,x in sorted(orders.items())]
    result['unresolved_source_line_dependencies']=missing
    result['frozen_move_ids']=sorted(x['id'] for x in frozen_moves)
    result['frozen_invoice_ids']=sorted(invoices)
    return result

def same_number(left,right,step=None):
    if left is None or right is None:return False
    a=Decimal(str(left));b=Decimal(str(right))
    if step:
        q=Decimal(str(step));return (a/q).quantize(Decimal('1'),rounding=ROUND_HALF_UP)==(b/q).quantize(Decimal('1'),rounding=ROUND_HALF_UP)
    return a==b

def compare_order(model,source,target,source_lines,target_lines,maps,source_units,target_units,currency_rounding,source_end):
    issues=[];details=[]
    if rid(source.get('company_id'))!=1:issues.append({'reason':'wrong_source_company'})
    if source.get('state')=='cancel':return {'classification':'source_cancelled_do_not_confirm','issues':issues,'line_results':[],'commercially_matched':False,'writer_eligible':False}
    if source.get('state') not in (['sale','done'] if model=='sale.order' else ['purchase','done']):issues.append({'reason':'source_not_confirmed','state':source.get('state')})
    if not target:
        return {'classification':'missing_target_order','issues':issues+[{'reason':'missing_target_order'}],'line_results':[{'source_line':x['id'],'target_line':None,'issues':[{'reason':'missing_target_order'}]} for x in source_lines],'commercially_matched':False,'writer_eligible':False}
    if rid(target.get('company_id'))!=1:issues.append({'reason':'wrong_target_company'})
    headers=[('partner_id','res.partner'),('currency_id','res.currency')]
    headers+=([('partner_invoice_id','res.partner'),('partner_shipping_id','res.partner'),('warehouse_id','stock.warehouse')] if model=='sale.order' else [('picking_type_id','stock.picking.type')])
    for field,relation in headers:
        if field not in source or field not in target:issues.append({'reason':'header_field_missing','field':field});continue
        sid=rid(source[field]);expected=maps.get(relation,{}).get(sid) if sid else False
        if expected is None or expected!=rid(target[field]):issues.append({'reason':'header_identity_mismatch','field':field,'source':sid,'expected_target':expected,'target':rid(target[field])})
    step=currency_rounding.get(rid(source.get('currency_id')))
    if not step:issues.append({'reason':'unverified_currency_rounding'})
    for field in ['amount_untaxed','amount_tax','amount_total']:
        if not same_number(source.get(field),target.get(field),step):issues.append({'reason':'header_amount_mismatch','field':field,'source':source.get(field),'target':target.get(field),'rounding':step})
    source_line_model=model+'.line';index={x['id']:x for x in target_lines};used=[]
    quantity='product_uom_qty' if model=='sale.order' else 'product_qty'
    target_unit_field='product_uom_id'
    duplicates=Counter(maps.get(source_line_model,{}).get(x['id']) for x in source_lines if maps.get(source_line_model,{}).get(x['id']))
    for line in source_lines:
        tid=maps.get(source_line_model,{}).get(line['id']);other=index.get(tid);errors=[]
        item={'source_line':line['id'],'target_line':tid,'source_display_type':line.get('display_type'),'issues':errors};details.append(item)
        if not other:errors.append({'reason':'missing_line_mapping_or_target'});continue
        used.append(tid)
        if duplicates[tid]>1:errors.append({'reason':'target_line_shared_by_sources'})
        if rid(other.get('order_id'))!=target['id']:errors.append({'reason':'target_line_wrong_order'})
        if line.get('display_type')!=other.get('display_type'):errors.append({'reason':'display_type_mismatch'})
        if line.get('display_type') in ['line_note','line_section']:
            if (line.get('name') or '')!=(other.get('name') or ''):errors.append({'reason':'note_or_section_text_mismatch'})
            continue
        for field,relation in [('product_id','product.product')]:
            sid=rid(line.get(field));expected=maps.get(relation,{}).get(sid) if sid else False
            if expected is None or expected!=rid(other.get(field)):errors.append({'reason':'line_product_identity_mismatch','source':sid,'expected_target':expected,'target':rid(other.get(field))})
        su=rid(line.get('product_uom') or line.get('product_uom_id'));tu=rid(other.get(target_unit_field) or other.get('product_uom'));expected=maps.get('uom.uom',{}).get(su)
        if not expected or expected!=tu:errors.append({'reason':'line_unit_identity_mismatch','source':su,'expected_target':expected,'target':tu})
        sr=source_units.get(su,{}).get('rounding');tr=target_units.get(tu,{}).get('rounding');precision=min(sr,tr) if sr and tr and sr>0 and tr>0 else None
        if not precision:errors.append({'reason':'unverified_quantity_precision'})
        if not same_number(line.get(quantity),other.get(quantity),precision):errors.append({'reason':'ordered_quantity_mismatch','source':line.get(quantity),'target':other.get(quantity),'rounding':precision})
        for field in ['price_unit','discount']:
            if field in line or field in other:
                # v14 purchase has no native discount field. Absence means no
                # discount only; a nonzero v19 discount must still be held.
                source_value=line.get(field,0) if field=='discount' and model=='purchase.order' else line.get(field)
                if not same_number(source_value,other.get(field)):errors.append({'reason':'commercial_value_mismatch','field':field,'source':source_value,'target':other.get(field)})
        for field in ['price_subtotal','price_total']:
            if not same_number(line.get(field),other.get(field),step):errors.append({'reason':'line_amount_mismatch','field':field,'source':line.get(field),'target':other.get(field),'rounding':step})
        source_taxes=line.get('tax_id',line.get('taxes_id',[]));target_taxes=other.get('tax_ids',other.get('taxes_id',[]));taxmap=maps.get('account.tax',{})
        if any(t not in taxmap for t in source_taxes) or {taxmap.get(t) for t in source_taxes}!=set(target_taxes):errors.append({'reason':'tax_identity_unverified','source':source_taxes,'target':target_taxes})
        item['quantity_basis']={'source':sr,'target':tr,'comparison':precision}
    if set(used)!=set(target.get('order_line',[])):issues.append({'reason':'extra_or_unmatched_target_lines','target_line_ids':sorted(set(target.get('order_line',[]))-set(used))})
    if source.get('write_date','')>=source_end:issues.append({'reason':'source_header_written_after_snapshot','write_date':source['write_date']})
    if any(x['issues'] for x in details):issues.append({'reason':'commercial_line_issues','count':sum(bool(x['issues']) for x in details)})
    state=target.get('state');confirmed=state in (['sale','done'] if model=='sale.order' else ['purchase','done'])
    classification=('confirmed_commercially_matched' if confirmed else 'draft_matched_pending_workflow_preflight') if not issues else ('confirmed_requires_review' if confirmed else 'draft_commercial_hold')
    if state not in ['draft','sent','sale','purchase','done']:classification='target_state_requires_review';issues.append({'reason':'unexpected_target_state','state':state})
    return {'classification':classification,'issues':issues,'line_results':details,'commercially_matched':not issues,'writer_eligible':False,'workflow_preflight':'M1/M2/M3 required before mutation'}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--evidence-dir',default=str(I['OUT']));args=parser.parse_args();out=Path(args.evidence_dir).resolve();phase=out/'phases';phase.mkdir(exist_ok=True)
    lock=runpy.run_path(str(BASE/'production_write_lock.py'))['acquire'](out)
    started=datetime.now(timezone.utc).isoformat();scope=load(out/'scope.json');approval=load(out/'execplan-approval.json')
    if not approval.get('approved'):raise RuntimeError('ExecPlan approval missing')
    if approval['scope_sha256']!=hashlib.sha256((out/'scope.json').read_bytes()).hexdigest():raise RuntimeError('Approved frozen scope changed')
    unknown=[]
    for path in out.glob('*journal.json'):
        data=load(path);ops=data.get('operations',[]) if isinstance(data,dict) else data if isinstance(data,list) else []
        unknown.extend({'journal':path.name,'operation':op} for op in ops if isinstance(op,dict) and op.get('status') in ['intent','uncertain'])
    if unknown:write(phase/'unresolved-operations.json',unknown);raise RuntimeError('Uncertain prior writes; M0 stopped')
    a=I['ReadOnly']('v14-prod',('http://175.145.85.151','paoyeang_live'));b=I['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    metrics=runpy.run_path(str(BASE/'production_rpc_metrics.py'))['Metrics']()
    class MeasuredCalls:
        def __init__(self,call):self.call=call
    for reader in (a,b):
        original=MeasuredCalls(reader.call)
        reader.call=lambda model,method,args,kwargs=None,original=original:metrics.call(original,model,method,args,kwargs)
    maps={m:{int(k):v for k,v in pairs.items()} for m,pairs in load(out/'resolved-master-evidence.json')['maps'].items()}
    maps,currency_proof=runpy.run_path(str(BASE/'approved_order_currency_mapping.py'))['apply'](maps,a.scan('res.currency',[['name','=','CNH']],['name','rounding']),b.scan('res.currency',[['name','=','CNY']],['name','rounding']))
    write(phase/'order-currency-map-evidence.json',currency_proof)
    moves=load(out/'source-moves.json');invoices=load(out/'source-invoices.json');invoice_lines=load(out/'source-invoice-lines.json')
    if len(moves)!=scope['counts']['moves'] or len(invoices)!=scope['counts']['invoices']:raise RuntimeError('Incomplete frozen input')
    source_line_fields=['order_id','name','display_type','product_id','product_uom','product_uom_id','product_uom_qty','product_qty','price_unit','discount','tax_id','taxes_id','price_subtotal','price_total','write_date','route_id']
    order_lines={}
    for model,file in [('sale.order.line','verify-source-sale.order.line.json'),('purchase.order.line','verify-source-purchase.order.line.json')]:order_lines[model]=load(out/file)
    refs={'sale.order.line':{rid(x['sale_line_id']) for x in moves if x.get('sale_line_id')}|{lid for x in invoice_lines for lid in x.get('sale_line_ids',[])},'purchase.order.line':{rid(x['purchase_line_id']) for x in moves if x.get('purchase_line_id')}|{rid(x['purchase_line_id']) for x in invoice_lines if x.get('purchase_line_id')}}
    for model,ids in refs.items():
        missing=ids-{x['id'] for x in order_lines[model]}
        if missing:order_lines[model]+=a.read(model,missing,source_line_fields)
    order_lines['account.move.line']=invoice_lines
    closure=build_scope(moves,invoices,order_lines,maps)
    if closure['unresolved_source_line_dependencies']:write(phase/'scope-dependency-errors.json',closure['unresolved_source_line_dependencies']);raise RuntimeError('Missing source dependency')
    closure.update(schema_version=1,stock_scope=scope,source_database=a.r.db,target_database=b.r.db,company_id=1)
    closure['scope_hash']=digest({k:v for k,v in closure.items() if k!='scope_hash'})
    write(phase/'phase-scope.json',closure)
    currency={x['id']:x.get('rounding') for x in a.read('res.currency',sorted({rid(x['currency_id']) for x in invoices}),['rounding'])}
    su={x['id']:x for x in load(out/'source-uom.uom.json')};tu={x['id']:x for x in load(out/'target-uom.uom.json')}
    header_fields=['name','state','company_id','partner_id','partner_invoice_id','partner_shipping_id','currency_id','warehouse_id','picking_type_id','order_line','picking_ids','invoice_ids','date_order','date_approve','amount_untaxed','amount_tax','amount_total','write_date','partner_ref','payment_term_id','carrier_id']
    results={};exceptions=[];baseline=load(out/'execplan-current-state-20261025.json')
    for model in ['purchase.order','sale.order']:
        ids=[x['source_id'] for x in closure[model]];source=a.read(model,ids,header_fields);source_index={x['id']:x for x in source}
        target=b.read(model,[maps.get(model,{}).get(sid) for sid in ids if maps.get(model,{}).get(sid)],header_fields);target_index={x['id']:x for x in target}
        sl=a.read(model+'.line',[lid for x in source for lid in x['order_line']],source_line_fields);tl=b.read(model+'.line',[lid for x in target for lid in x['order_line']],source_line_fields+['tax_ids','route_ids','is_expense'])
        sg=defaultdict(list);tg=defaultdict(list)
        for x in sl:sg[rid(x['order_id'])].append(x)
        for x in tl:tg[rid(x['order_id'])].append(x)
        # Metadata must be stable across the commercial snapshot.
        source_after=a.read(model,ids,['write_date']);target_after=b.read(model,list(target_index),['write_date'])
        if any(x['write_date']!=source_index[x['id']]['write_date'] for x in source_after) or any(x['write_date']!=target_index[x['id']]['write_date'] for x in target_after):raise RuntimeError('Orders changed during M0 capture')
        write(phase/('source-'+model+'.json'),source);write(phase/('target-'+model+'.json'),target);write(phase/('source-'+model+'.line.json'),sl);write(phase/('target-'+model+'.line.json'),tl)
        rows=[]
        for item in closure[model]:
            s=source_index[item['source_id']];t=target_index.get(item['mapped_target']);row={'source_id':s['id'],'source_name':s['name'],'target_id':t['id'] if t else None,'target_name':t['name'] if t else None,'source_state':s['state'],'target_state':t['state'] if t else None,'date_order':s.get('date_order'),'origins':item['origins']}
            row.update(compare_order(model,s,t,sg[s['id']],tg[t['id']] if t else [],maps,su,tu,currency,scope['end_utc_exclusive']));rows.append(row)
            if row['issues'] or row['classification']=='source_cancelled_do_not_confirm':exceptions.append({'model':model,**row})
        old_ids={x['source']['id'] for x in baseline[model]['rows']};new_ids=set(ids)
        results[model]={'rows':rows,'source_lines':len(sl),'target_lines':len(tl),'summary':dict(Counter(x['classification'] for x in rows)),'scope_delta':{'baseline_count':len(old_ids),'current_count':len(new_ids),'added':sorted(new_ids-old_ids),'removed':sorted(old_ids-new_ids),'basis':'Explicit frozen move and invoice line dependencies, not all order lines in earlier verification snapshots'}}
        print(json.dumps({'model':model,'orders':len(rows),'classifications':results[model]['summary'],'scope_delta':results[model]['scope_delta']}),flush=True)
    completed=datetime.now(timezone.utc).isoformat()
    report={'schema_version':1,'read_only':True,'started_utc':started,'completed_utc':completed,'company_id':1,'source_database':a.r.db,'target_database':b.r.db,'scope_hash':closure['scope_hash'],'unclassified':0,'writer_eligible_count':0,'workflow_preflight_complete':False,'models':results,'local_readiness':load(phase/'m0-local-readiness.json'),'note':'M0 classifies commercial identity only; no controller or workflow approval has been implied.'}
    write(phase/'phase-readiness.json',report);write(phase/'exceptions.json',exceptions)
    write(phase/'performance-baseline.json',{'schema_version':1,'kind':'M0_read_only_capture','started_utc':started,'completed_utc':completed,'scope_hash':closure['scope_hash'],'rpc_calls':metrics.rows,'note':'Read capture baseline only; not confirmation throughput or an optimization comparison.'})
    text=['# M0 - Ra soat pham vi va xac nhan don','', 'Read-only XML-RPC; khong ghi Odoo. Bao cao chi la soat thuong mai, chua cho phep writer chay.','', 'Scope hash: '+closure['scope_hash'],'', '| Model | Don nguon | Phan loai |','|---|---:|---|']
    for model,data in results.items():text.append('| '+model+' | '+str(len(data['rows']))+' | '+json.dumps(data['summary'],ensure_ascii=False)+' |')
    text+=['','Chi tiet tung dong: [phase-readiness.json](phase-readiness.json).','Ngoai le: [exceptions.json](exceptions.json).','Khong co mutation_started; unclassified=0. Workflow/route/supplier/approval checks se thuc hien truoc confirm trong M1/M2/M3.']
    (phase/'BAO_CAO_XAC_NHAN_DON.md').write_text('\n'.join(text)+'\n',encoding='utf8')
    print(json.dumps({'m0_capture_complete':True,'unclassified':0,'erp_mutations':0,'scope_hash':closure['scope_hash']}),flush=True)

if __name__=='__main__':main()
