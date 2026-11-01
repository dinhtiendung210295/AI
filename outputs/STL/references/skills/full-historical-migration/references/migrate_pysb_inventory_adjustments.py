"""Replay actual frozen inventory deltas through native quant inventory counts.

Never writes quant.quantity, imports an absolute old count, or supplies temporary
stock. Each source group is applied atomically and checked before another group.
"""
import argparse
import json
import runpy
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
BASE=Path(__file__).parent
R=runpy.run_path(str(BASE/'migrate_pysb_independent_receipts.py'))
OUT=R['OUT'];load=R['load'];rid=R['rid']


class Run(R['Run']):
    def __init__(self,recovery_group=None):
        super().__init__()
        for name in ['independent-mo-journal.json','independent-delivery-journal.json','opening-lot-resolution.json']:
            for model,pairs in load(name)['maps'].items():
                for sid,tid in pairs.items():
                    old=self.maps.setdefault(model,{}).get(int(sid))
                    if old and old!=tid:raise RuntimeError('Inventory source mapping conflict')
                    self.maps[model][int(sid)]=tid
        self.plan=load('independent-inventory-adjustment-plan.json');self.rows={x['source_move']:x for x in self.plan['rows']}
        self.headers={x['id']:x for x in load('source-inventory-adjustment-headers.json')}
        self.count_lines=load('source-inventory-adjustment-count-lines.json')
        self.verified_sources={x['source_move_id'] for x in load('after-run-stock-coverage.json')['results'] if x['status'] in ['verified','approved_exception']}
        self.lots={x['id']:x for x in load('source-inventory-adjustment-lots.json')}
        self.j=load('independent-inventory-journal.json') if (OUT/'independent-inventory-journal.json').exists() else {'database':self.b.r.db,'company_id':1,'operations':[],'groups':{},'maps':{},'rounding_differences':[]}
        for model,pairs in self.j['maps'].items():self.maps.setdefault(model,{}).update({int(s):t for s,t in pairs.items()})
        self.uncertain=[x for x in self.j['operations'] if x['status'] in ['intent','uncertain']]
        if not recovery_group and (self.uncertain or any(x['status']!='verified_done' for x in self.j['groups'].values())):raise RuntimeError('Interrupted inventory group requires read-back; do not apply delta again')
        if recovery_group and any(key!=recovery_group and row['status']!='verified_done' for key,row in self.j['groups'].items()):raise RuntimeError('Different inventory group also incomplete')
    def persist(self):
        self.j['maps']={model:values for model,values in self.maps.items() if model in ['stock.move','stock.move.line','stock.lot']}
        R['save']('independent-inventory-journal.json',self.j)
    def mutate(self,model,method,args,context=None,jsonrpc=False):
        allowed={'stock.quant':{'create','write','action_apply_inventory'},'stock.lot':{'create'},'stock.move':{'write'},'stock.move.line':{'write'},'ir.model.data':{'create'}}
        if method not in allowed.get(model,set()):raise RuntimeError('Forbidden inventory mutation')
        if model=='stock.quant' and method=='write' and not set(args[1])<={'inventory_quantity','user_id'}:raise RuntimeError('Only count input may be written')
        if model=='stock.quant' and method=='create' and not set(args[0])<={'product_id','location_id','lot_id','package_id','owner_id','inventory_quantity','user_id'}:raise RuntimeError('No direct quant quantity or arbitrary fields')
        if model in ['stock.move','stock.move.line'] and method=='write' and set(args[1])!={'date'}:raise RuntimeError('Inventory post-write limited to historical dates')
        return super().mutate(model,method,args,{**(context or {}),'inventory_mode':True},jsonrpc=jsonrpc)
    def lot(self,sid):
        if not sid:return False
        source=self.lots[sid];pid=self.maps['product.product'][rid(source['product_id'])]
        known=self.maps.get('stock.lot',{}).get(sid)
        found=self.b.read('stock.lot',[known],['name','product_id','company_id']) if known else self.b.scan('stock.lot',[['company_id','=',1],['product_id','=',pid],['name','=',source['name']]],['name','product_id','company_id'])
        if not known and not found:
            complete=self.b.scan('stock.lot',[['company_id','=',1],['product_id','=',pid]],['name','product_id','company_id'])
            found=[x for x in complete if x['name']==source['name'] and rid(x['product_id'])==pid and rid(x['company_id'])==1]
            self.j.setdefault('lot_lookup_readbacks',[]).append({'source_lot':sid,'source_name':source['name'],'target_product':pid,'complete_product_company_lot_ids':[x['id'] for x in complete],'exact_api_matches':found});self.persist()
        if len(found)>1:raise RuntimeError('Ambiguous count lot')
        if found:
            target=found[0]
            if target['name']!=source['name'] or rid(target['product_id'])!=pid or rid(target['company_id'])!=1:raise RuntimeError('Historical count lot identity drift')
            tid=target['id']
        else:
            values={'name':source['name'],'product_id':pid,'company_id':1}
            values.update({field:source[field] for field in ['expiration_date','use_date','removal_date','alert_date'] if source.get(field)})
            tid=self.mutate('stock.lot','create',[values])
            actual=self.b.read('stock.lot',[tid],['name','product_id','company_id'])[0]
            if actual['name']!=source['name'] or rid(actual['product_id'])!=pid:raise RuntimeError('Created count lot read-back differs')
        self.attach('stock.lot',sid,tid);return tid
    def flow(self,group):
        flow=(bool(group['source_inventory']),tuple(sorted({self.rows[mid]['sign'] for mid in group['pending_moves']})),tuple(sorted({self.tp[self.rows[mid]['target_product']]['tracking'] for mid in group['pending_moves']})),len(group['pending_moves'])>1)
        return flow+('same_factor_native_unit_alias',) if any(self.rows[mid].get('target_unit_alias_proof') for mid in group['pending_moves']) else flow
    def process(self,group):
        key=group['group_key']
        if key in self.j['groups']:return
        if not group['eligible']:raise RuntimeError('Held source inventory group')
        mids=group['pending_moves'];frozen={mid:self.sm[mid] for mid in mids}
        fresh=self.a.read('stock.move',mids,list(next(iter(frozen.values()))))
        if any(x!=frozen[x['id']] for x in fresh):raise RuntimeError('Source inventory moves changed')
        lines={line['id']:line for mid in mids for line in self.by_move[mid]}
        if any(x!=lines[x['id']] for x in self.a.read('stock.move.line',list(lines),list(next(iter(lines.values()))))):raise RuntimeError('Source inventory details changed')
        if group['source_inventory']:
            header=self.headers[group['source_inventory']]
            scope_members={mid for mid in header['move_ids'] if mid in self.sm}
            if set(mids)!=scope_members-self.verified_sources or group['name']!=header['name']:raise RuntimeError('Incomplete source inventory change set')
            if self.a.read('stock.inventory',[header['id']],list(header))[0]!=header:raise RuntimeError('Source count header changed')
            counts={self.rows[mid]['source_count']['id']:self.rows[mid]['source_count'] for mid in mids}
            if any(x!=counts[x['id']] for x in self.a.read('stock.inventory.line',list(counts),list(next(iter(counts.values()))))):raise RuntimeError('Source count lines changed')
        elif len(mids)!=1 or group['name']!=self.sm[mids[0]]['name']+' [v14:'+str(mids[0])+']':raise RuntimeError('Direct adjustment scope differs')
        if any(self.maps.get('stock.move',{}).get(mid) for mid in mids):raise RuntimeError('Existing inventory move needs audit')
        rec={'source_name':group['name'],'source_inventory':group['source_inventory'],'source_moves':mids,'status':'preparing','flow':self.flow(group),'before':[]};self.j['groups'][key]=rec;self.persist()
        quant_ids=[]
        for mid in mids:
            row=self.rows[mid];source=self.sm[mid];line=self.by_move[mid][0];pid=row['target_product'];unit=row['target_unit']
            if source['state']!='done' or rid(source['company_id'])!=1 or not self.scope['start_utc']<=source['date']<self.scope['end_utc_exclusive'] or source['date']!=group['event_utc']:raise RuntimeError('Inventory source date/company/state outside scope')
            mapped_unit=self.maps['uom.uom'][rid(source['product_uom'])];alias=row.get('target_unit_alias_proof')
            if unit!=mapped_unit:
                policy=load('inventory-unit-alias-validation.json')
                if not policy.get('enabled') or policy['scope']!=self.scope or str(mid) not in policy['moves'] or policy['moves'][str(mid)]['proof']!=alias:raise RuntimeError('Unvalidated inventory unit alias')
                unit_ids=sorted({x['id'] for chain in ['mapped_chain','native_chain'] for x in alias[chain]})
                actual_units={x['id']:x for x in self.b.read('uom.uom',unit_ids,['factor','rounding','relative_factor','relative_uom_id'])}
                runpy.run_path(str(BASE/'same_factor_unit_alias.py'))['check'](alias,mapped_unit,unit,actual_units)
            elif alias:raise RuntimeError('Unexpected unit alias on an identical unit')
            src=rid(source['location_id']);dst=rid(source['location_dest_id']);usages=(self.locations[src]['usage'],self.locations[dst]['usage'])
            if usages not in [('inventory','internal'),('internal','inventory')]:raise RuntimeError('Source is not an inventory delta')
            sign=1 if usages[0]=='inventory' else -1;internal=dst if sign==1 else src;virtual=src if sign==1 else dst
            if row['sign']!=sign or pid!=self.maps['product.product'][rid(source['product_id'])] or row['target_location']!=self.maps['stock.location'][internal] or row['target_inventory_location']!=self.maps['stock.location'][virtual] or rid(line['product_id'])!=rid(source['product_id']) or rid(line['product_uom_id'])!=rid(source['product_uom']) or any(line[field] for field in ['owner_id','package_id','result_package_id']):raise RuntimeError('Inventory plan is not an exact source projection')
            if row['source_lot']!=rid(line['lot_id']) or abs(line['qty_done']-source['quantity_done'])>1e-8:raise RuntimeError('Source inventory lot/quantity differs')
            if row['source_lot'] and rid(self.lots[row['source_lot']]['product_id'])!=rid(source['product_id']):raise RuntimeError('Source count lot belongs to another product')
            if rid(source['inventory_id'])!=group['source_inventory']:raise RuntimeError('Inventory source parent differs')
            if group['source_inventory']:
                counted_source=runpy.run_path(str(BASE/'inventory_count_checks.py'))['match_count'](source,line,self.headers[group['source_inventory']],self.count_lines,sign,internal)
                if counted_source!=row['source_count']:raise RuntimeError('Source inventory count proof differs')
            lot=self.lot(row['source_lot'])
            product=self.b.read('product.product',[pid],['uom_id','tracking','is_storable','property_stock_inventory'])[0]
            if not product['is_storable'] or rid(product['uom_id'])!=unit or rid(product['property_stock_inventory'])!=row['target_inventory_location'] or product['tracking']!=self.tp[pid]['tracking']:raise RuntimeError('Native count product/unit/location/tracking changed')
            domain=[['company_id','=',1],['product_id','=',pid],['location_id','=',row['target_location']],['lot_id','=',lot],['package_id','=',False],['owner_id','=',False]]
            quants=self.b.scan('stock.quant',domain,['quantity','reserved_quantity','inventory_quantity_set','inventory_quantity','inventory_diff_quantity','user_id','inventory_date'])
            if len(quants)>1:raise RuntimeError('Duplicate native count quant key')
            before=quants[0] if quants else None
            if before and (before['inventory_quantity_set'] or before['user_id']):raise RuntimeError('Existing staff inventory count must not be overwritten')
            quantity=before['quantity'] if before else 0;reserved=before['reserved_quantity'] if before else 0
            target_quantity=R['rounded'](line['qty_done'],self.tu[unit]['rounding']);delta=row['sign']*target_quantity;counted=quantity+delta
            if alias and abs(target_quantity-line['qty_done'])>1e-8:raise RuntimeError('Validated unit alias must not change historical quantity')
            if abs(target_quantity-line['qty_done'])>1e-8:
                if not load('operator-decisions.json')['rounding']['approved']:raise RuntimeError('Inventory rounding not approved')
                record={'source_line':line['id'],'source_move':mid,'source_qty':line['qty_done'],'target_qty':target_quantity,'target_unit':unit,'delta':target_quantity-line['qty_done']}
                if record not in self.j['rounding_differences']:self.j['rounding_differences'].append(record);self.persist()
            if quantity+1e-6<reserved or counted<-1e-8 or (delta<0 and quantity-reserved+1e-6<-delta):raise RuntimeError('Inventory count stock/reservation gate failed')
            evidence={'source_move':mid,'source_line':line['id'],'source_count':row['source_count'],'quant_before':before,'target_product':pid,'location':row['target_location'],'lot':lot,'unit':unit,'delta':delta,'count_input':counted,'target_unit_alias_proof':alias};rec['before'].append(evidence);self.persist()
            if before:
                qid=before['id'];self.mutate('stock.quant','write',[[qid],{'inventory_quantity':counted,'user_id':self.b.r.uid}])
            else:
                qid=self.mutate('stock.quant','create',[{'product_id':pid,'location_id':row['target_location'],'lot_id':lot,'package_id':False,'owner_id':False,'inventory_quantity':counted,'user_id':self.b.r.uid}])
            staged=self.b.read('stock.quant',[qid],['quantity','inventory_quantity','inventory_diff_quantity','inventory_quantity_set'])[0]
            if abs(staged['quantity']-quantity)>1e-8 or abs(staged['inventory_diff_quantity']-delta)>1e-8:raise RuntimeError('Count input precision or concurrent stock changed; do not apply')
            evidence['quant_id']=qid;evidence['staged']=staged;quant_ids.append(qid);self.persist()
        before_max=self.b.call('stock.move','search_read',[[['company_id','=',1]]],{'fields':['id'],'order':'id desc','limit':1})
        floor=before_max[0]['id'] if before_max else 0
        counts={model:self.b.call(model,'search_count',[[['company_id','=',1]]]) for model in ['purchase.order','mrp.production']}
        invoice_domain=[['company_id','=',1],['move_type','in',['out_invoice','in_invoice','out_refund','in_refund']]]
        invoice_count=self.b.call('account.move','search_count',[invoice_domain])
        rec.update(status='prepared_unapplied',target_quants=quant_ids,before_move_floor=floor,before_procurement_counts=counts,invoice_count_before=invoice_count);self.persist()
        result=self.mutate('stock.quant','action_apply_inventory',[quant_ids,group['event_utc']],{'inventory_name':group['name']},jsonrpc=True)
        rec['apply_result']=result;self.persist();self.finish_applied(group,rec)
    def recover_applied(self,key):
        rec=self.j['groups'][key];group=next(x for x in self.plan['groups'] if x['group_key']==key)
        if rec['status']!='prepared_unapplied':raise RuntimeError('Recovery requires prepared inventory with uncertain apply response')
        expected_args=[rec['target_quants'],group['event_utc']]
        if len(self.uncertain)!=1 or self.uncertain[0]['model']!='stock.quant' or self.uncertain[0]['method']!='action_apply_inventory' or self.uncertain[0]['args']!=expected_args:raise RuntimeError('Unexpected inventory uncertainty; separate review required')
        native=self.b.scan('stock.move',[['company_id','=',1],['id','>',rec['before_move_floor']]],['state','is_inventory','inventory_name','quantity'])
        if len(native)!=len(group['pending_moves']) or any(x['state']!='done' or not x['is_inventory'] or x['inventory_name']!=group['name'] for x in native):raise RuntimeError('Inventory apply not proven; never repeat delta blindly')
        after=self.b.read('stock.quant',rec['target_quants'],['quantity','reserved_quantity','inventory_quantity_set'])
        for evidence in rec['before']:
            quant=next(x for x in after if x['id']==evidence['quant_id']);before=evidence['quant_before']['quantity'] if evidence['quant_before'] else 0
            if abs(quant['quantity']-before-evidence['delta'])>1e-8 or quant['inventory_quantity_set']:raise RuntimeError('Inventory quant delta not proven for recovery')
        operation=self.uncertain[0];since=operation['utc'].split('.')[0].replace('T',' ')
        added={model:self.b.scan(model,[['company_id','=',1],['create_date','>=',since]]+([['move_type','in',['out_invoice','in_invoice','out_refund','in_refund']]] if model=='account.move' else []),['name','state']) for model in ['purchase.order','mrp.production','account.move']}
        if any(added.values()):raise RuntimeError('New procurement/invoice since uncertain count requires review')
        operation.update(status='verified_applied_by_readback',readback={'native_moves':native,'quants':after,'no_new_procurement_since':since});self.uncertain=[];rec['recovery_readback']=operation['readback'];self.persist()
        self.finish_applied(group,rec)
    def resume_staged(self,key):
        rec=self.j['groups'][key];group=next(x for x in self.plan['groups'] if x['group_key']==key)
        if self.uncertain or rec['status']!='prepared_unapplied':raise RuntimeError('Only definitely unsent staged count may resume')
        if any(x['model']=='stock.quant' and x['method']=='action_apply_inventory' and x['args'][0]==rec['target_quants'] for x in self.j['operations']):raise RuntimeError('Prior apply intent requires separate read-back')
        mids=group['pending_moves'];source=self.a.read('stock.move',mids,list(self.sm[mids[0]]))
        if any(x!=self.sm[x['id']] for x in source):raise RuntimeError('Source staged count changed')
        lines={x['id']:x for mid in mids for x in self.by_move[mid]}
        if any(x!=lines[x['id']] for x in self.a.read('stock.move.line',list(lines),list(next(iter(lines.values()))))):raise RuntimeError('Source staged count details changed')
        if group['source_inventory']:
            header=self.headers[group['source_inventory']]
            if self.a.read('stock.inventory',[header['id']],list(header))[0]!=header:raise RuntimeError('Source staged count header changed')
            counts={x['source_count']['id']:x['source_count'] for x in rec['before']}
            if any(x!=counts[x['id']] for x in self.a.read('stock.inventory.line',list(counts),list(next(iter(counts.values()))))):raise RuntimeError('Source staged count input changed')
        if self.b.scan('stock.move',[['company_id','=',1],['id','>',rec['before_move_floor']]],['state']):raise RuntimeError('New moves since unsent count require review')
        quants=self.b.read('stock.quant',rec['target_quants'],['quantity','reserved_quantity','inventory_quantity','inventory_diff_quantity','inventory_quantity_set','user_id','product_id','location_id','lot_id','owner_id','package_id'])
        for evidence in rec['before']:
            quant=next(x for x in quants if x['id']==evidence['quant_id']);before=evidence['quant_before']['quantity'] if evidence['quant_before'] else 0
            if abs(quant['quantity']-before)>1e-8 or abs(quant['inventory_diff_quantity']-evidence['delta'])>1e-8 or abs(quant['inventory_quantity']-evidence['count_input'])>1e-8 or not quant['inventory_quantity_set'] or rid(quant['user_id'])!=self.b.r.uid or rid(quant['product_id'])!=evidence['target_product'] or rid(quant['location_id'])!=evidence['location'] or rid(quant['lot_id'])!=evidence['lot'] or quant['owner_id'] or quant['package_id'] or quant['reserved_quantity']>before+min(evidence['delta'],0)+1e-8:raise RuntimeError('Staged native count drift; do not apply')
        rec['unsent_resume_readback']=quants;self.persist()
        result=self.mutate('stock.quant','action_apply_inventory',[rec['target_quants'],group['event_utc']],{'inventory_name':group['name']},jsonrpc=True)
        rec['apply_result']=result;self.persist();self.finish_applied(group,rec)
    def resume_verification(self,key):
        rec=self.j['groups'][key];group=next(x for x in self.plan['groups'] if x['group_key']==key)
        if self.uncertain or rec['status']!='done_pending_verification':raise RuntimeError('Only returned inventory application may finish verification')
        operations=[x for x in self.j['operations'] if x['model']=='stock.quant' and x['method']=='action_apply_inventory' and x['args']==[rec['target_quants'],group['event_utc']]]
        if len(operations)!=1 or operations[0]['status']!='returned':raise RuntimeError('Returned native inventory application not proven')
        quants=self.b.read('stock.quant',rec['target_quants'],['quantity','inventory_quantity_set'])
        for evidence in rec['before']:
            quant=next(x for x in quants if x['id']==evidence['quant_id']);before=evidence['quant_before']['quantity'] if evidence['quant_before'] else 0
            if abs(quant['quantity']-before-evidence['delta'])>1e-8 or quant['inventory_quantity_set']:raise RuntimeError('Applied inventory delta differs; no reapplication allowed')
        rec['verification_resume_quants']=quants;self.persist();self.finish_applied(group,rec)
    def finish_applied(self,group,rec):
        mids=group['pending_moves'];floor=rec['before_move_floor']
        native=self.b.scan('stock.move',[['id','>',floor],['company_id','=',1]],['state','is_inventory','inventory_name','product_id','product_uom','product_uom_qty','quantity','location_id','location_dest_id','move_line_ids'])
        if len(native)!=len(mids) or any(x['state']!='done' or not x['is_inventory'] or x['inventory_name']!=group['name'] for x in native):raise RuntimeError('Inventory returned wizard or unexpected native moves; read back before repeating')
        rec['status']='done_pending_verification';rec['native_moves']=native;self.persist()
        pairs=[];line_pairs=[];used=set()
        for evidence in rec['before']:
            mid=evidence['source_move'];row=self.rows[mid];source=self.sm[mid];quantity=abs(evidence['delta'])
            candidates=[x for x in native if x['id'] not in used and rid(x['product_id'])==row['target_product'] and rid(x['product_uom'])==row['target_unit'] and rid(x['location_id'])==self.maps['stock.location'][rid(source['location_id'])] and rid(x['location_dest_id'])==self.maps['stock.location'][rid(source['location_dest_id'])] and abs(x['quantity']-quantity)<1e-8]
            if len(candidates)>1:
                candidates=[x for x in candidates if len(x['move_line_ids'])==1 and rid(self.b.read('stock.move.line',x['move_line_ids'],['lot_id'])[0]['lot_id'])==evidence['lot']]
            if len(candidates)!=1:raise RuntimeError('Native inventory move pairing not unique')
            target=candidates[0];used.add(target['id']);pairs.append((mid,target['id']))
            actual=self.b.read('stock.move.line',target['move_line_ids'],['state','product_id','product_uom_id','location_id','location_dest_id','quantity','lot_id','owner_id','package_id','result_package_id'])
            if len(actual)!=1:raise RuntimeError('Unexpected count detail count')
            detail=actual[0]
            if detail['state']!='done' or rid(detail['product_id'])!=row['target_product'] or rid(detail['product_uom_id'])!=row['target_unit'] or rid(detail['lot_id'])!=evidence['lot'] or abs(detail['quantity']-quantity)>1e-8 or any(detail[field] for field in ['owner_id','package_id','result_package_id']):raise RuntimeError('Native inventory detail differs')
            for field in ['location_id','location_dest_id']:
                if rid(detail[field])!=self.maps['stock.location'][rid(source[field])]:raise RuntimeError('Inventory detail location differs')
            line_pairs.append((evidence['source_line'],detail['id']))
        self.attach_many('stock.move',pairs);self.attach_many('stock.move.line',line_pairs)
        for mid,tid in pairs:
            self.mutate('stock.move','write',[[tid],{'date':self.sm[mid]['date']}])
            for line in self.by_move[mid]:self.mutate('stock.move.line','write',[[self.maps['stock.move.line'][line['id']]],{'date':line['date']}])
        after=self.b.read('stock.move',list(used),['state','date','quantity','product_uom','move_line_ids'])
        for mid,tid in pairs:
            target=next(x for x in after if x['id']==tid);line=self.by_move[mid][0]
            actual=self.b.read('stock.move.line',target['move_line_ids'],['date','quantity'])[0]
            if target['date']!=self.sm[mid]['date'] or actual['date']!=line['date']:raise RuntimeError('Inventory historical date read-back differs')
        for model,count in rec.get('before_procurement_counts',{}).items():
            if self.b.call(model,'search_count',[[['company_id','=',1]]])!=count:raise RuntimeError('Unexpected inventory procurement created')
        invoice_domain=[['company_id','=',1],['move_type','in',['out_invoice','in_invoice','out_refund','in_refund']]]
        if 'invoice_count_before' in rec and self.b.call('account.move','search_count',[invoice_domain])!=rec['invoice_count_before']:raise RuntimeError('Unexpected invoice created by count')
        rec.update(status='verified_done',verified_moves=after,verified_utc=datetime.now(timezone.utc).isoformat());self.persist()
        print(json.dumps({'completed_inventory':group['name'],'moves':len(mids)}),flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['sample','batch'],default='sample');parser.add_argument('--limit',type=int,default=10);parser.add_argument('--recover-applied');parser.add_argument('--finish-applied');parser.add_argument('--resume-staged');args=parser.parse_args();r=Run(args.recover_applied or args.finish_applied or args.resume_staged)
    lock=runpy.run_path(str(BASE/'production_write_lock.py'))['acquire'](OUT)
    if sum(bool(x) for x in [args.recover_applied,args.finish_applied,args.resume_staged])>1:raise RuntimeError('Select one recovery mode')
    if args.resume_staged:r.resume_staged(args.resume_staged);return
    if args.recover_applied:r.recover_applied(args.recover_applied);return
    if args.finish_applied:r.resume_verification(args.finish_applied);return
    rows=[x for x in r.plan['groups'] if x['eligible'] and x['group_key'] not in r.j['groups']]
    selected=rows[:1 if args.mode=='sample' else args.limit]
    if args.mode=='batch' and selected:
        proven={json.dumps(x['flow']) for x in r.j['groups'].values() if x['status']=='verified_done'}
        if json.dumps(r.flow(selected[0])) not in proven:selected=selected[:1]
        else:selected=selected[:next((i for i,x in enumerate(selected) if json.dumps(r.flow(x)) not in proven),len(selected))]
    for group in selected:r.process(group)
    print(json.dumps({'verified_inventory_groups':sum(x['status']=='verified_done' for x in r.j['groups'].values())}),flush=True)


if __name__=='__main__':main()
