"""Exactly three conditionally approved legacy offsets; native counts, sample first, no retries."""
import argparse,hashlib,json,os,runpy,uuid
from pathlib import Path
from datetime import datetime,timezone
from collections import defaultdict
BASE=Path(__file__).parent
R=runpy.run_path(str(BASE/'migrate_pysb_independent_receipts.py'));I=R['I'];OUT=R['OUT'];rid=R['rid']
DATE='2026-07-31 15:59:59'
KEYS=((116918,5,27979,False,False),(118970,5,26717,False,False),(119904,5,26667,False,False))
DELTAS={KEYS[0]:-1.,KEYS[1]:-1.,KEYS[2]:-5.}
FIELDS=['product_id','location_id','lot_id','package_id','owner_id','quantity','reserved_quantity','inventory_quantity','inventory_quantity_set','user_id']
MOVE_FIELDS='name origin reference date state company_id product_id product_uom product_uom_qty quantity location_id location_dest_id move_line_ids is_inventory inventory_name description_picking_manual value account_move_id'.split()
LINE_FIELDS='move_id product_id product_uom_id quantity lot_id location_id location_dest_id package_id result_package_id owner_id date state'.split()
def now():return datetime.now(timezone.utc).isoformat()
def load(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def key(row,dest=False):return (rid(row['product_id']),rid(row['location_dest_id'] if dest else row['location_id']),rid(row['lot_id']),rid(row['result_package_id'] if dest else row['package_id']),rid(row['owner_id']))
def count_gate(k,delta,quantity,reserved,source_opening,target_opening):
    if k not in DELTAS or delta!=DELTAS[k]:raise RuntimeError('Outside exactly three approved offsets')
    if quantity+delta<-1e-6 or reserved>1e-8:raise RuntimeError('Negative or reserved count is not approved')
    if abs(target_opening+delta-source_opening)>1e-6:raise RuntimeError('Opening delta is not explained')
    return quantity+delta
def historical(reader,pid):return reader.call('product.product','read',[[pid]],{'fields':['qty_available'],'context':{'allowed_company_ids':[1],'active_test':False,'tz':'UTC','to_date':DATE}})[0]['qty_available']
def matching_source_event(source,target,source_product,source_quantity,target_quantity):
    return source['state']=='done' and target['state']=='done' and source['date']==target['date'] and rid(source['company_id'])==1 and rid(target['company_id'])==1 and rid(source['product_id'])==source_product and abs(source_quantity-target_quantity)<=1e-6 and abs(source_quantity)>1e-8

class Run(R['Run']):
    def __init__(self):
        super().__init__();self.path=OUT/'temporary-opening-offset-journal.json'
        self.j=load(self.path.name) if self.path.exists() else dict(database=self.b.r.db,company_id=1,operations=[],entries={},started_utc=now())
        self.uncertain=[x for x in self.j['operations'] if x['status'] in ['intent','uncertain']]
        if self.uncertain:raise RuntimeError('Prior offset mutation needs readback; never apply again')
        self.entry=None
    def persist(self):
        temp=self.path.with_suffix('.tmp')
        with temp.open('w',encoding='utf8') as handle:
            handle.write(json.dumps(self.j,ensure_ascii=False,indent=2));handle.flush();os.fsync(handle.fileno())
        temp.replace(self.path)
    def mutate(self,model,method,args,context=None,jsonrpc=False):
        e=self.entry
        if not e:raise RuntimeError('No approved active offset')
        allowed=False
        if (model,method)==('stock.quant','write'):allowed=args==[[e['quant_id']],{'inventory_quantity':e['count_after'],'user_id':self.b.r.uid}]
        elif (model,method)==('stock.quant','action_apply_inventory'):allowed=args==[[e['quant_id']]]
        elif (model,method)==('stock.move.line','write'):allowed=args==[e.get('target_lines'),{'date':DATE}]
        elif (model,method)==('stock.move','write'):allowed=args==[[e.get('target_move')],{'date':DATE,'origin':e['reference'],'inventory_name':e['reference'],'description_picking_manual':e['note']}]
        elif (model,method)==('ir.model.data','create'):allowed=args==[{'module':'pysb_temporary_offset','name':e['token'],'model':'stock.move','res_id':e.get('target_move'),'noupdate':True}]
        if not allowed:raise RuntimeError('Mutation outside exact native offset allowlist')
        return super().mutate(model,method,args,context={**(context or {}),'inventory_mode':True,'inventory_name':e['reference']},jsonrpc=jsonrpc)
    def quants(self,pid):return self.b.scan('stock.quant',[['company_id','=',1],['product_id','=',pid]],FIELDS)
    def balance(self,rows,loc):
        out=defaultdict(lambda:[0.,0.])
        locations={x['id']:x for x in self.b.read('stock.location',{rid(v['location_id']) for v in rows},['usage'])}
        for x in rows:
            if locations[rid(x['location_id'])]['usage']!='internal':continue
            k=tuple(rid(x[f]) for f in ['product_id','location_id','lot_id','package_id','owner_id']);out[k][0]+=x['quantity'];out[k][1]+=x['reserved_quantity']
        return out
    def source_and_target_opening(self,item,current):
        sp,sloc,slot,_,_=item['source_key'];pid,loc,lot,_,_=item['proposal']['target_key'];tu=self.tu
        su={x['id']:x for x in load('source-uom.uom.json')}
        source_domain=[['company_id','=',1],['state','=','done'],['product_id','=',sp],['lot_id','=',slot],['move_id.date','<',load('scope.json')['start_utc']],'|',['location_id','=',sloc],['location_dest_id','=',sloc]]
        source=self.a.scan('stock.move.line',source_domain,['move_id','product_id','product_uom_id','qty_done','lot_id','location_id','location_dest_id','package_id','result_package_id','owner_id','date'])
        s=0.;base=rid(item['source_product']['uom_id'])
        for x in source:
            if x['owner_id']:continue
            q=x['qty_done']*su[base]['factor']/su[rid(x['product_uom_id'])]['factor']
            if rid(x['location_id'])==sloc and not x['package_id']:s-=q
            if rid(x['location_dest_id'])==sloc and not x['result_package_id']:s+=q
        target_domain=[['company_id','=',1],['state','=','done'],['product_id','=',pid],['lot_id','=',lot],['move_id.date','>=',load('scope.json')['start_utc']],'|',['location_id','=',loc],['location_dest_id','=',loc]]
        target=self.b.scan('stock.move.line',target_domain,LINE_FIELDS);post=0.;base=rid(item['target_product']['uom_id'])
        for x in target:
            if x['owner_id']:continue
            q=x['quantity']*tu[rid(x['product_uom_id'])]['factor']/tu[base]['factor']
            if rid(x['location_id'])==loc and not x['package_id']:post-=q
            if rid(x['location_dest_id'])==loc and not x['result_package_id']:post+=q
        return s,current-post,dict(source_lines=source,target_post_opening_lines=target)
    def history(self,item):
        k=tuple(item['proposal']['target_key']);pid,loc,lot,_,_=k;originals=item['proposal']['temporary_move_ids']
        moves=self.b.scan('stock.move',[['company_id','=',1],['product_id','=',pid],['is_inventory','=',True],['state','!=','cancel']],MOVE_FIELDS)
        lines=self.b.read('stock.move.line',[i for x in moves for i in x['move_line_ids']],LINE_FIELDS);by=defaultdict(list)
        for x in lines:by[rid(x['move_id'])].append(x)
        ids=self.b.scan('ir.model.data',[['model','=','stock.move'],['res_id','in',originals]],['module','name','res_id'])
        found={x['id']:x for x in moves};total=0.
        for mid in originals:
            move=found.get(mid)
            if not move or move['state']!='done' or move['date']>=DATE or not any(x['res_id']==mid and x['module']=='pysb_temporary_inventory' for x in ids):raise RuntimeError('Original temporary provenance no longer proven')
            if 'PYSB-TEMP' not in (move.get('origin') or '').upper():raise RuntimeError('Original temporary label changed')
            for x in by[mid]:
                q=x['quantity']*self.tu[rid(x['product_uom_id'])]['factor']/self.tu[rid(item['target_product']['uom_id'])]['factor']
                if key(x)==k:total-=q
                if key(x,True)==k:total+=q
        if abs(total+DELTAS[k])>1e-6:raise RuntimeError('Original temporary net differs from approved delta')
        first=min(found[mid]['date'] for mid in originals)
        source_map=load('after-run-stock-mapping.json')['maps'].get('stock.move',{});genuine=[];review=[]
        for move in moves:
            if move['id'] in originals or move['date']<first:continue
            relevant=[x for x in by[move['id']] if key(x)==k or key(x,True)==k]
            if relevant and (abs(move['quantity'])>1e-8 or move['state']!='done'):
                source_ids=[int(s) for s,t in source_map.items() if t==move['id']]
                proof=dict(target_move=move,target_lines=relevant,source_ids=source_ids,matched=False)
                if len(source_ids)==1 and move['state']=='done':
                    sm=self.a.read('stock.move',source_ids,['state','date','company_id','product_id','move_line_ids','inventory_id','production_id','raw_material_production_id'])[0]
                    sl=self.a.read('stock.move.line',sm['move_line_ids'],['product_id','product_uom_id','qty_done','location_id','location_dest_id','lot_id','package_id','result_package_id','owner_id'])
                    source_key=tuple(item['source_key']);su={x['id']:x for x in load('source-uom.uom.json')};snet=0.;tnet=0.
                    for x in sl:
                        q=x['qty_done']*su[rid(item['source_product']['uom_id'])]['factor']/su[rid(x['product_uom_id'])]['factor']
                        if key(x)==source_key:snet-=q
                        if key(x,True)==source_key:snet+=q
                    for x in relevant:
                        q=x['quantity']*self.tu[rid(x['product_uom_id'])]['factor']/self.tu[rid(item['target_product']['uom_id'])]['factor']
                        if key(x)==k:tnet-=q
                        if key(x,True)==k:tnet+=q
                    proof.update(source_move=sm,source_lines=sl,source_signed_quantity=snet,target_signed_quantity=tnet,matched=matching_source_event(sm,move,item['source_key'][0],snet,tnet))
                if proof['matched']:genuine.append(proof)
                else:review.append(proof)
            if not by[move['id']] and move['state']!='done' and loc in [rid(move['location_id']),rid(move['location_dest_id'])]:raise RuntimeError('Pending inventory at this product/location requires review')
        history=dict(original_moves=[found[mid] for mid in originals],original_external_ids=ids,inventory_history=moves,inventory_lines=lines,temporary_net=total,genuine_later_source_movements=genuine,unexplained_later_inventory=review)
        I['save']('phases/offset-history-'+str(pid)+'.json',dict(read_only=True,generated_utc=now(),target_key=list(k),history=history))
        if review:raise RuntimeError('Unexplained later inventory or possible prior offset; no duplicate subtraction')
        return history
    def apply(self,item):
        k=tuple(item['proposal']['target_key']);pid,loc,lot,_,_=k;eid=str(pid)+'_'+str(lot)
        old=self.j['entries'].get(eid)
        if old:
            if old['status']=='verified':print(json.dumps(dict(already_verified=eid)),flush=True);return
            raise RuntimeError('Interrupted offset requires readback; no automatic reapplication')
        history=self.history(item)
        product=self.b.read('product.product',[pid],list(item['target_product']))[0]
        if product!=item['target_product']:raise RuntimeError('Master/cost changed after approved preflight')
        before=self.quants(pid);matching=[x for x in before if tuple(rid(x[f]) for f in ['product_id','location_id','lot_id','package_id','owner_id'])==k]
        if len(matching)!=1 or matching[0]['inventory_quantity_set'] or matching[0]['user_id']:raise RuntimeError('Quant missing/ambiguous or another inventory count exists')
        quant=matching[0];s,t,ledger=self.source_and_target_opening(item,quant['quantity']);after=count_gate(k,DELTAS[k],quant['quantity'],quant['reserved_quantity'],s,t)
        source_total=historical(self.a,item['source_key'][0]);target_total=historical(self.b,pid)
        if abs(target_total+DELTAS[k]-source_total)>1e-6:raise RuntimeError('Offset does not fully reconcile this product opening')
        token='july_temporary_'+str(item['proposal']['temporary_move_ids'][0])+'_'+eid
        if self.b.scan('ir.model.data',[['module','=','pysb_temporary_offset'],['name','=',token]],['res_id']):raise RuntimeError('Existing offset identity outside journal; review, never apply twice')
        if set(['date','origin','inventory_name','description_picking_manual'])-set(self.b.fields('stock.move',['date','origin','inventory_name','description_picking_manual'])):raise RuntimeError('Required native trace fields unavailable')
        reference='PYSB-TEMP-OFFSET | original '+','.join(map(str,item['proposal']['temporary_move_ids']))+' | '+eid
        entry=dict(status='preparing',target_key=list(k),delta=DELTAS[k],reference=reference,token=token,quant_id=quant['id'],count_after=after,before_product=product,before_quants=before,source_opening=s,target_opening_before=t,source_total_opening=source_total,target_total_opening_before=target_total,history=history,ledger=ledger,account_count_before=self.b.call('account.move','search_count',[[['company_id','=',1]]]),created_utc=now())
        entry['note']=json.dumps(dict(purpose='Offset evidenced legacy temporary stock; not a new v14 inventory adjustment',original_temporary_moves=item['proposal']['temporary_move_ids'],approved_by='Bruce',target_key=list(k),quantity_delta=DELTAS[k],effective_utc=DATE,source_opening=s,target_opening_before=t,current_count_before=quant['quantity'],current_count_after=after,approval_file='phases/operator-temporary-offset-approval.json',preserve_original_done_history=True),ensure_ascii=False,indent=2)
        self.j['entries'][eid]=entry;self.entry=entry;self.persist()
        self.mutate('stock.quant','write',[[quant['id']],{'inventory_quantity':after,'user_id':self.b.r.uid}])
        staged=self.b.read('stock.quant',[quant['id']],FIELDS)[0]
        if staged['quantity']!=quant['quantity'] or staged['reserved_quantity'] or staged['inventory_quantity']!=after or not staged['inventory_quantity_set']:raise RuntimeError('Staged count differs; do not apply')
        entry['status']='staged';self.persist()
        self.mutate('stock.quant','action_apply_inventory',[[quant['id']]],jsonrpc=True)
        entry['status']='applied_pending_readback';self.persist()
        moves=self.b.scan('stock.move',[['company_id','=',1],['product_id','=',pid],['is_inventory','=',True]],MOVE_FIELDS)
        new=[x for x in moves if x['id'] not in {v['id'] for v in history['inventory_history']}]
        if len(new)!=1:raise RuntimeError('Unexpected native offset move count; readback required')
        move=new[0];inv=rid(product['property_stock_inventory'])
        if move['state']!='done' or rid(move['company_id'])!=1 or rid(move['product_id'])!=pid or rid(move['product_uom'])!=rid(product['uom_id']) or abs(move['quantity']+DELTAS[k])>1e-6 or rid(move['location_id'])!=loc or rid(move['location_dest_id'])!=inv or move['account_move_id']:raise RuntimeError('Native offset direction/quantity/accounting differs')
        expected=abs(DELTAS[k])*product['standard_price']
        if abs(abs(move['value'])-expected)>.011:raise RuntimeError('Native inventory value differs from preflight')
        details=self.b.read('stock.move.line',move['move_line_ids'],LINE_FIELDS)
        if len(details)!=1 or key(details[0])!=k or rid(details[0]['location_dest_id'])!=inv or abs(details[0]['quantity']+DELTAS[k])>1e-6 or details[0]['result_package_id']:raise RuntimeError('Native offset dimensions differ')
        entry.update(target_move=move['id'],target_lines=move['move_line_ids'],status='applied_once');self.persist()
        self.mutate('stock.move.line','write',[entry['target_lines'],{'date':DATE}])
        self.mutate('stock.move','write',[[entry['target_move']],{'date':DATE,'origin':reference,'inventory_name':reference,'description_picking_manual':entry['note']}])
        self.mutate('ir.model.data','create',[{'module':'pysb_temporary_offset','name':token,'model':'stock.move','res_id':move['id'],'noupdate':True}])
        final=self.quants(pid);a=self.balance(before,loc);b=self.balance(final,loc)
        for changed in set(a)|set(b):
            if abs(b[changed][0]-a[changed][0]-(DELTAS[k] if changed==k else 0))>1e-6 or abs(b[changed][1]-a[changed][1])>1e-6:raise RuntimeError('Stock/reservation changed outside exact count')
        current=b[k][0];s,t,afterledger=self.source_and_target_opening(item,current)
        finalmove=self.b.read('stock.move',[move['id']],MOVE_FIELDS)[0];dates=self.b.read('stock.move.line',entry['target_lines'],['date'])
        if abs(t-s)>1e-6 or abs(historical(self.b,pid)-source_total)>1e-6 or finalmove['date']!=DATE or any(x['date']!=DATE for x in dates):raise RuntimeError('Historical opening/date readback differs')
        if self.b.read('product.product',[pid],list(product))[0]!=product:raise RuntimeError('Master/cost changed during count')
        if self.b.read('stock.move',item['proposal']['temporary_move_ids'],list(history['original_moves'][0]))!=history['original_moves']:raise RuntimeError('Original temporary history changed')
        if self.b.call('account.move','search_count',[[['company_id','=',1]]])!=entry['account_count_before']:raise RuntimeError('Accounting count changed; separate readback required')
        entry.update(status='verified',verified_utc=now(),after_quants=final,after_move=finalmove,after_ledger=afterledger,source_opening_after=s,target_opening_after=t,target_total_opening_after=historical(self.b,pid),account_moves_created=0);self.persist()
        print(json.dumps(dict(verified_offset=eid,move=move['id'],delta=DELTAS[k],current_quantity=current,source_opening=s,target_opening=t,account_moves_created=0)),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['inspect','sample','remaining'],default='inspect');p.add_argument('--history-only',action='store_true');args=p.parse_args()
    approval=load('phases/operator-temporary-offset-approval.json');raw=(OUT/approval['approved_preflight']).read_bytes()
    if not approval.get('approved') or hashlib.sha256(raw).hexdigest()!=approval['plan_sha256']:raise RuntimeError('Immutable reviewed preflight/approval mismatch')
    approved=json.loads(raw);rows=approved['rows']
    if {tuple(x['proposal']['target_key']) for x in rows}!=set(KEYS):raise RuntimeError('Not exactly the three reviewed keys')
    if args.mode=='inspect':
        if not args.history_only:runpy.run_path(str(BASE/'preflight_pysb_safe_temporary_offsets.py'))['main']()
        r=Run();findings=[]
        for item in rows:
            try:
                h=r.history(item);findings.append(dict(target_key=item['proposal']['target_key'],history_ok=True,temporary_net=h['temporary_net'],original_move_ids=[x['id'] for x in h['original_moves']]))
            except RuntimeError as error:findings.append(dict(target_key=item['proposal']['target_key'],history_ok=False,reason=str(error)))
        I['save']('phases/temporary-offset-history-review.json',dict(read_only=True,generated_utc=now(),rows=findings));print(json.dumps(findings),flush=True);return
    lock=runpy.run_path(str(BASE/'production_write_lock.py'))['acquire'](OUT);active=False;previous=os.environ.get('PYSB_PHASE_TOKEN')
    try:
        C=runpy.run_path(str(BASE/'run_pysb_phased_migration.py'));identity,_=C['validate_context'](OUT)
        C['require_previous_gate'](OUT,'stock',identity)
        if approval['identity']!=identity or not load('scope.json')['backup_acknowledged_by_operator'] or not load('phases/stock-offset-handoff.json')['requested']:raise RuntimeError('Opening-offset scope/backup/handoff missing')
        r=Run()
        if not r.j.get('fresh_preflight'):
            runpy.run_path(str(BASE/'preflight_pysb_safe_temporary_offsets.py'))['main']();fresh=load('phases/temporary-opening-safe-preflight.json')
            for item in fresh['rows']:
                old=next(x for x in rows if x['proposal']['target_key']==item['proposal']['target_key'])
                if item['proposal']['proposed_delta']!=old['proposal']['proposed_delta'] or item['target_product']!=old['target_product']:raise RuntimeError('Approved amount/master changed')
            r.j.update(fresh_preflight=fresh,approval=approval);r.persist()
        rows=r.j['fresh_preflight']['rows']
        if args.mode=='remaining' and r.j['entries'].get(str(KEYS[0][0])+'_'+str(KEYS[0][2]),{}).get('status')!='verified':raise RuntimeError('CYAN sample must verify before remaining two')
        token=uuid.uuid4().hex;I['save']('phases/phased-control-enabled.json',dict(identity=identity,supported_phases=['stock'],status='Exactly approved temporary opening offsets'))
        I['save']('phases/active-phase.json',dict(identity=identity,phase='stock',token=token,pid=os.getpid(),started_utc=now()));os.environ['PYSB_PHASE_TOKEN']=token;active=True
        selected=[x for x in rows if (tuple(x['proposal']['target_key'])==KEYS[0])==(args.mode=='sample')]
        for item in selected:r.apply(item)
    finally:
        if active:
            I['save']('phases/active-phase.json',dict(phase=None,pid=None,token=None,stopped_utc=now()));I['save']('phases/phased-control-enabled.json',dict(identity=identity,supported_phases=[],status='Offset group closed; normal queue stays handed off'))
        if previous is None:os.environ.pop('PYSB_PHASE_TOKEN',None)
        else:os.environ['PYSB_PHASE_TOKEN']=previous
        lock.close()
if __name__=='__main__':main()
