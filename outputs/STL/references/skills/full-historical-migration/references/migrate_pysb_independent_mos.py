"""Journalled native MO execution for the conservative historical supply plan.

Interrupted/uncertain executions stop for read-back recovery. Main finished
lines remain unpicked until button_mark_done, preventing double consumption.
"""
import argparse
import copy
import json
import runpy
import hashlib
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
R=runpy.run_path(str(Path(__file__).with_name('migrate_pysb_independent_receipts.py')))
I=R['I'];OUT=R['OUT'];load=R['load'];save=R['save'];rid=R['rid'];rounded=R['rounded'];CTX=R['CTX']

class Run:
    def __init__(self):
        self.a=I['ReadOnly']('v14-prod',('http://175.145.85.151','paoyeang_live'));self.b=I['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
        self.scope=load('scope.json');assert self.scope['backup_acknowledged_by_operator'] and self.scope['complete']
        self.maps=load('discovery-manifest.json')['maps']
        self.maps=runpy.run_path(str(Path(__file__).with_name('stock_confirmation_handoff.py')))['apply'](self.maps,OUT)
        for model,pairs in load('independent-receipts-journal.json')['maps'].items():self.maps.setdefault(model,{}).update(pairs)
        for model,pairs in load('independent-inventory-journal.json')['maps'].items():self.maps.setdefault(model,{}).update(pairs)
        self.maps.setdefault('stock.lot',{}).update(load('opening-lot-resolution.json')['maps']['stock.lot'])
        self.mos={x['id']:x for x in load('source-mo-execution-details.json')};self.moves={x['id']:x for x in load('source-moves.json')};self.lines=defaultdict(list)
        for x in load('source-move-lines.json'):self.lines[rid(x['move_id'])].append(x)
        self.tu={x['id']:x for x in load('target-uom.uom.json')};self.tp={x['id']:x for x in load('target-products.json')}
        self.lots={x['id']:x for x in load('source-lots.json')}
        if (OUT/'source-mo-lot-metadata.json').exists():self.lots.update({x['id']:x for x in load('source-mo-lot-metadata.json')['rows']})
        self.plan=load('independent-mo-supply-plan.json')
        self.j=load('independent-mo-journal.json') if (OUT/'independent-mo-journal.json').exists() else {'database':self.b.r.db,'company_id':1,'operations':[],'mos':{},'maps':{},'rounding_differences':[]}
        for model,pairs in self.j['maps'].items():self.maps.setdefault(model,{}).update(pairs)
        if any(x['status'] not in ['returned','verified_rejected_by_readback'] for x in self.j['operations']):raise RuntimeError('Prior uncertain MO operation requires read-back; do not repeat consumption')
    def persist(self):save('independent-mo-journal.json',self.j)
    def mutate(self,model,method,args,context=None):
        R['WORKFLOW']['GUARD']()
        allowed={'mrp.production':{'create','write','action_confirm','button_mark_done'},'stock.move':{'write'},'stock.move.line':{'create','write','unlink'},'stock.lot':{'create'},'ir.model.data':{'create'},'expiry.picking.confirmation':{'create','confirm_produce'}}
        if method not in allowed.get(model,set()):raise RuntimeError('Forbidden MO mutation')
        op={'model':model,'method':method,'args':copy.deepcopy(args),'status':'intent','utc':datetime.now(timezone.utc).isoformat()};self.j['operations'].append(op);self.persist()
        try:
            result=R['WORKFLOW']['call'](self.b.r,model,method,args,{'context':{**CTX,**(context or {})}});op.update(status='returned',result=result);self.persist();return result
        except Exception as e:op.update(status='uncertain',error=str(e));self.persist();raise
    def mapped(self,model,sid):return self.maps[model][str(sid)]
    def attach(self,model,sid,tid):
        name=model.replace('.','_')+'_'+str(sid)
        old=self.b.call('ir.model.data','search_read',[[['module','=','pysb_v14'],['name','=',name]]],{'fields':['model','res_id'],'limit':2})
        if old:
            if len(old)!=1 or old[0]['model']!=model or old[0]['res_id']!=tid:raise RuntimeError('MO XMLID conflict')
        else:self.mutate('ir.model.data','create',[{'module':'pysb_v14','name':name,'model':model,'res_id':tid,'noupdate':True}])
        self.maps.setdefault(model,{})[str(sid)]=tid;self.j['maps'].setdefault(model,{})[str(sid)]=tid;self.persist()
    def lot(self,sid):
        if not sid:return False
        if str(sid) in self.maps.get('stock.lot',{}):return self.mapped('stock.lot',sid)
        s=self.lots[sid];pid=self.mapped('product.product',rid(s['product_id']))
        old=self.b.call('stock.lot','search_read',[[['company_id','=',1],['product_id','=',pid],['name','=',s['name']]]],{'fields':['name'],'limit':2})
        if not old:
            complete=self.b.scan('stock.lot',[['company_id','=',1],['product_id','=',pid]],['name','product_id','company_id'])
            old=[x for x in complete if x['name']==s['name'] and rid(x['product_id'])==pid and rid(x['company_id'])==1]
            self.j.setdefault('lot_lookup_readbacks',[]).append({'source_lot':sid,'source_name':s['name'],'target_product':pid,'complete_product_company_lot_ids':[x['id'] for x in complete],'exact_api_matches':old});self.persist()
        if len(old)>1:raise RuntimeError('Ambiguous MO lot')
        values={'name':s['name'],'company_id':1,'product_id':pid}
        for field in ['expiration_date','use_date','removal_date','alert_date']:
            if s.get(field):
                if field not in self.b.fields('stock.lot',[field]):raise RuntimeError('Historical lot expiry field unavailable')
                values[field]=s[field]
        tid=old[0]['id'] if old else self.mutate('stock.lot','create',[values])
        self.attach('stock.lot',sid,tid);return tid
    def flow(self,entry):
        s=self.mos[entry['source_mo']];raw=[i for i in s['move_raw_ids'] if i in self.moves];finished=[i for i in s['move_finished_ids'] if i in self.moves]
        tracking=tuple(sorted({self.tp[self.mapped('product.product',rid(self.moves[i]['product_id']))]['tracking'] for i in raw+finished}))
        return len(raw),len(finished),tracking,len({self.moves[i]['date'] for i in raw+finished})>1
    def qty(self,line):
        unit=self.mapped('uom.uom',rid(line['product_uom_id']));q=rounded(line['qty_done'],self.tu[unit]['rounding'])
        if abs(q-line['qty_done'])>1e-8:
            record={'source_line':line['id'],'source_quantity':line['qty_done'],'target_quantity':q,'delta':q-line['qty_done'],'target_unit':unit}
            if record not in self.j['rounding_differences']:self.j['rounding_differences'].append(record);self.persist()
        return q
    def demand_qty(self,mo,move):
        unit=self.mapped('uom.uom',rid(move['product_uom']))
        approval=load('operator-mo-demand-rounding-approval.json') if (OUT/'operator-mo-demand-rounding-approval.json').exists() else {}
        helper=runpy.run_path(str(Path(__file__).with_name('approved_mo_demand_rounding.py')))
        value,record=helper['demand_quantity'](mo,move,unit,self.tu[unit]['rounding'],approval)
        if record and record not in self.j.setdefault('demand_rounding_differences',[]):
            self.j['demand_rounding_differences'].append(record);self.persist()
        return value
    def process(self,entry):
        sid=entry['source_mo'];s=self.mos[sid];rec=self.j['mos'].get(str(sid))
        if rec:
            if rec['status']=='verified_done':return
            raise RuntimeError('Interrupted MO needs explicit read-back recovery: '+s['name'])
        if not entry['eligible']:raise RuntimeError('Held MO')
        # Predecessor proposals must really have succeeded before execution.
        earlier=[x for x in self.plan['rows'] if x['eligible'] and (x['event_utc'],x['source_mo'])<(entry['event_utc'],sid)]
        if any(self.j['mos'].get(str(x['source_mo']),{}).get('status')!='verified_done' for x in earlier):raise RuntimeError('Earlier proposed MO supply not completed')
        if self.a.read('mrp.production',[sid],list(s))[0]!=s:raise RuntimeError('Source MO changed since frozen dependency snapshot')
        duplicate=self.b.scan('mrp.production',[['company_id','=',1],['name','=',s['name']]],['state'])
        if duplicate:raise RuntimeError('Existing unjournalled MO name')
        mids=[i for i in s['move_raw_ids']+s['move_finished_ids'] if i in self.moves]
        fresh=self.a.read('stock.move',mids,['state','write_date'])
        if any(x['state']!='done' or x['write_date']!=self.moves[x['id']]['write_date'] for x in fresh):raise RuntimeError('Source MO moves changed')
        expected_lines={x['id']:x for mid in mids for x in self.lines[mid]}
        fresh_lines=self.a.read('stock.move.line',list(expected_lines),list(next(iter(expected_lines.values()))))
        if any(x!=expected_lines[x['id']] for x in fresh_lines):raise RuntimeError('Source MO detailed operations changed since frozen snapshot')
        rec={'source_name':s['name'],'status':'preparing','source_id':sid};self.j['mos'][str(sid)]=rec;self.persist()
        for mid in mids:
            for line in self.lines[mid]:self.lot(rid(line['lot_id']))
        values={'name':s['name'],'company_id':1,'product_id':self.mapped('product.product',rid(s['product_id'])),'product_qty':s['product_qty'],'product_uom_id':self.mapped('uom.uom',rid(s['product_uom_id'])),'bom_id':False,
            'picking_type_id':self.mapped('stock.picking.type',rid(s['picking_type_id'])),'location_src_id':self.mapped('stock.location',rid(s['location_src_id'])),'location_dest_id':self.mapped('stock.location',rid(s['location_dest_id'])),
            'date_start':s['date_planned_start'],'date_finished':s['date_finished'],'origin':s['origin'],'x_studio_reference_no':s['x_studio_reference_no']}
        for field in ['move_raw_ids','move_finished_ids']:
            vals=[]
            for mid in s[field]:
                if mid not in self.moves:continue
                m=self.moves[mid];v={'company_id':1,'product_id':self.mapped('product.product',rid(m['product_id'])),'product_uom':self.mapped('uom.uom',rid(m['product_uom'])),'product_uom_qty':self.demand_qty(s,m),
                    'location_id':self.mapped('stock.location',rid(m['location_id'])),'location_dest_id':self.mapped('stock.location',rid(m['location_dest_id'])),'date':m['date'],'state':'draft','procure_method':'make_to_stock','propagate_cancel':False,'rule_id':False}
                vals.append((0,0,v))
            values[field]=vals
        mainlots={self.lot(rid(x['lot_id'])) for mid in s['move_finished_ids'] for x in self.lines[mid] if rid(x['product_id'])==rid(s['product_id']) and x['lot_id']}
        if mainlots:values['lot_producing_ids']=[(6,0,sorted(mainlots))]
        tid=self.mutate('mrp.production','create',[values]);rec['target_id']=tid;self.persist();self.attach('mrp.production',sid,tid)
        self.mutate('mrp.production','action_confirm',[[tid]])
        self.mutate('mrp.production','write',[[tid],{'qty_producing':s['qty_produced']}])
        self.prepare_and_finish(s,rec)
    def prepare_and_finish(self,s,rec):
        tid=rec['target_id']
        t=self.b.read('mrp.production',[tid],['move_raw_ids','move_finished_ids','state'])[0]
        native=self.b.read('stock.move',t['move_raw_ids']+t['move_finished_ids'],['product_id','product_uom','product_uom_qty','location_id','location_dest_id','move_line_ids','state','picked','move_orig_ids','move_dest_ids','origin_returned_move_id'])
        pairs={};used=set()
        for field in ['move_raw_ids','move_finished_ids']:
            for mid in s[field]:
                if mid not in self.moves:continue
                m=self.moves[mid]
                candidates=[x for x in native if x['id'] in t[field] and x['id'] not in used and all(rid(x[f])==self.mapped(model,rid(m[f])) for f,model in [('product_id','product.product'),('product_uom','uom.uom'),('location_id','stock.location'),('location_dest_id','stock.location')])]
                known=self.j['maps'].get('stock.move',{}).get(str(mid))
                x,interchangeable=runpy.run_path(str(Path(__file__).with_name('native_mo_placeholder_matching.py')))['choose'](candidates,self.demand_qty(s,m),known)
                if interchangeable:
                    rec.setdefault('placeholder_bindings',[]).append({'source_move':mid,'target_move':x['id'],'candidate_ids':[v['id'] for v in candidates],'proof':'own same-role same-product/unit/location/demand unpicked moves without supply/return links; historical lot details assigned and verified afterward'})
                    self.persist()
                if abs(x['product_uom_qty']-self.demand_qty(s,m))>1e-8:raise RuntimeError('Native MO demand differs from scoped approval')
                pairs[mid]=x['id'];used.add(x['id']);self.attach('stock.move',mid,x['id'])
        if len(used)!=len(native):raise RuntimeError('Additional native MO moves')
        existing=self.b.read('stock.move.line',[i for x in native for i in x['move_line_ids']],['state','picked'])
        if any(x['state']=='done' or x['picked'] for x in existing):raise RuntimeError('MO raw/finished unexpectedly picked or done')
        if existing:self.mutate('stock.move.line','unlink',[[x['id'] for x in existing]])
        # Check free live stock only after releasing this MO's own reservations.
        demand=defaultdict(float)
        for mid in s['move_raw_ids']:
            for x in self.lines[mid]:
                pid=self.mapped('product.product',rid(x['product_id']));u=self.mapped('uom.uom',rid(x['product_uom_id']));base=rid(self.tp[pid]['uom_id'])
                demand[(pid,self.mapped('stock.location',rid(x['location_id'])),self.lot(rid(x['lot_id'])))]+=self.qty(x)*self.tu[u]['factor']/self.tu[base]['factor']
        for (pid,loc,lot),qty in demand.items():
            quants=self.b.scan('stock.quant',[['company_id','=',1],['product_id','=',pid],['location_id','=',loc],['lot_id','=',lot],['package_id','=',False],['owner_id','=',False]],['quantity','reserved_quantity'])
            if sum(x['quantity']-x['reserved_quantity'] for x in quants)+1e-6<qty:raise RuntimeError('Insufficient free live MO stock')
        for mid,tmid in pairs.items():
            main=mid in s['move_finished_ids'] and rid(self.moves[mid]['product_id'])==rid(s['product_id'])
            vals=[]
            for x in self.lines[mid]:
                vals.append({'move_id':tmid,'company_id':1,'product_id':self.mapped('product.product',rid(x['product_id'])),'product_uom_id':self.mapped('uom.uom',rid(x['product_uom_id'])),'quantity':self.qty(x),'lot_id':self.lot(rid(x['lot_id'])),
                    'location_id':self.mapped('stock.location',rid(x['location_id'])),'location_dest_id':self.mapped('stock.location',rid(x['location_dest_id'])),'picked':not main,'date':x['date']})
            tids=self.mutate('stock.move.line','create',[vals])
            for x,tlid in zip(self.lines[mid],tids):self.attach('stock.move.line',x['id'],tlid)
            self.mutate('stock.move','write',[[tmid],{'picked':not main}])
        rec['status']='prepared_unconsumed';self.persist()
        result=self.mutate('mrp.production','button_mark_done',[[tid]],{'skip_backorder':True,'skip_redirection':True})
        actual=self.b.read('mrp.production',[tid],['state','product_qty','qty_produced'])[0]
        if actual['state']!='done':
            if isinstance(result,dict) and result.get('res_model')=='expiry.picking.confirmation' and (OUT/'operator-expiry-confirmation-approval.json').exists():
                rec.update(status='expiry_held',execution_hold=True,expiry_warning=result);self.persist();self.confirm_expiry(s['id']);return
            raise RuntimeError('MO returned wizard; read-back before continuing: '+str(result))
        # Read and compare quantity before any date restoration; never consume twice.
        rec['status']='done_pending_verification';self.persist()
        self.restore_and_verify(s,rec,pairs)
    def recover_unconsumed(self,sid):
        s=self.mos[sid];rec=self.j['mos'][str(sid)];tid=rec.get('target_id')
        if rec['status']!='preparing' or not tid or self.mapped('mrp.production',sid)!=tid:raise RuntimeError('Recovery requires own journalled preparing MO')
        if self.a.read('mrp.production',[sid],list(s))[0]!=s:raise RuntimeError('Source MO changed before recovery')
        mids=[i for i in s['move_raw_ids']+s['move_finished_ids'] if i in self.moves]
        fresh=self.a.read('stock.move',mids,['state','write_date'])
        if any(x['state']!='done' or x['write_date']!=self.moves[x['id']]['write_date'] for x in fresh):raise RuntimeError('Source moves changed before recovery')
        expected_lines={x['id']:x for mid in mids for x in self.lines[mid]}
        if any(x!=expected_lines[x['id']] for x in self.a.read('stock.move.line',list(expected_lines),list(next(iter(expected_lines.values()))))):raise RuntimeError('Source details changed before recovery')
        expected={'name':s['name'],'company_id':1,'product_id':self.mapped('product.product',rid(s['product_id'])),'product_uom_id':self.mapped('uom.uom',rid(s['product_uom_id'])),'product_qty':s['product_qty'],'qty_producing':s['qty_produced'],'date_start':s['date_planned_start'],'bom_id':False,'origin':s['origin'],'x_studio_reference_no':s['x_studio_reference_no']}
        for field,model in [('location_src_id','stock.location'),('location_dest_id','stock.location'),('picking_type_id','stock.picking.type')]:expected[field]=self.mapped(model,rid(s[field]))
        mo=self.b.read('mrp.production',[tid],list(expected)+['state','qty_produced','move_raw_ids','move_finished_ids'])[0]
        moves=self.b.read('stock.move',mo['move_raw_ids']+mo['move_finished_ids'],['state','picked','move_line_ids'])
        lines=self.b.read('stock.move.line',[i for m in moves for i in m['move_line_ids']],['state','picked'])
        runpy.run_path(str(Path(__file__).with_name('unconsumed_mo_recovery_guard.py')))['guard'](mo,moves,lines,self.j['operations'],expected)
        rec['recovery_readback']={'mo':mo,'moves':moves,'lines':lines,'utc':datetime.now(timezone.utc).isoformat()};self.persist()
        self.prepare_and_finish(s,rec)
    def confirm_expiry(self,sid):
        s=self.mos[sid];rec=self.j['mos'][str(sid)];tid=rec['target_id']
        if rec['status'] not in ['expiry_held','prepared_unconsumed'] or self.mapped('mrp.production',sid)!=tid:raise RuntimeError('Expiry recovery requires own prepared MO')
        if self.a.read('mrp.production',[sid],list(s))[0]!=s:raise RuntimeError('Source MO changed before expiry confirmation')
        mids=[i for i in s['move_raw_ids']+s['move_finished_ids'] if i in self.moves]
        fresh=self.a.read('stock.move',mids,['state','write_date'])
        if any(x['state']!='done' or x['write_date']!=self.moves[x['id']]['write_date'] for x in fresh):raise RuntimeError('Source moves changed before expiry confirmation')
        source_lines={x['id']:x for mid in mids for x in self.lines[mid]}
        if any(x!=source_lines[x['id']] for x in self.a.read('stock.move.line',list(source_lines),list(next(iter(source_lines.values()))))):raise RuntimeError('Source expiry detail drift')
        mo=self.b.read('mrp.production',[tid],['name','date_start','origin','x_studio_reference_no','state','company_id','product_id','product_uom_id','product_qty','qty_produced','qty_producing','move_raw_ids','move_finished_ids'])[0]
        if any(mo[field]!=s[source_field] for field,source_field in [('name','name'),('date_start','date_planned_start'),('origin','origin'),('x_studio_reference_no','x_studio_reference_no')]):raise RuntimeError('Expiry MO history identity drift')
        if rid(mo['product_id'])!=self.mapped('product.product',rid(s['product_id'])) or rid(mo['product_uom_id'])!=self.mapped('uom.uom',rid(s['product_uom_id'])) or abs(mo['product_qty']-s['product_qty'])>1e-8 or abs(mo['qty_producing']-s['qty_produced'])>1e-8:raise RuntimeError('Expiry MO header drift')
        pairs={mid:self.mapped('stock.move',mid) for mid in mids}
        for field in ['move_raw_ids','move_finished_ids']:
            if set(mo[field])!={pairs[mid] for mid in s[field] if mid in pairs}:raise RuntimeError('Expiry MO role/move mismatch')
        native=self.b.read('stock.move',list(pairs.values()),['state','product_uom_qty','move_line_ids'])
        fields=['product_id','product_uom_id','location_id','location_dest_id','lot_id','quantity','owner_id','package_id','result_package_id']
        details=self.b.read('stock.move.line',[i for move in native for i in move['move_line_ids']],fields)
        detail_index={x['id']:x for x in details}
        for mid,tmid in pairs.items():
            move=next(x for x in native if x['id']==tmid)
            expected_ids={self.mapped('stock.move.line',x['id']) for x in self.lines[mid]}
            if set(move['move_line_ids'])!=expected_ids or abs(move['product_uom_qty']-self.demand_qty(s,self.moves[mid]))>1e-8:raise RuntimeError('Prepared expiry move demand/line drift')
            for line in self.lines[mid]:
                actual=detail_index[self.mapped('stock.move.line',line['id'])]
                for field,model in [('product_id','product.product'),('product_uom_id','uom.uom'),('location_id','stock.location'),('location_dest_id','stock.location'),('lot_id','stock.lot')]:
                    expected=self.mapped(model,rid(line[field])) if line[field] else False
                    if rid(actual[field])!=expected:raise RuntimeError('Prepared expiry line identity drift')
                if actual['quantity']!=self.qty(line) or any(actual[x] for x in ['owner_id','package_id','result_package_id']):raise RuntimeError('Prepared expiry line quantity/owner drift')
        warning=rec.get('expiry_warning')
        if not warning:
            warning=next((x.get('result') for x in reversed(self.j['operations']) if x['model']=='mrp.production' and x['method']=='button_mark_done' and x['args']==[[tid]] and isinstance(x.get('result'),dict)),{})
        raw_ids={pairs[mid] for mid in s['move_raw_ids'] if mid in pairs}
        raw_lines=[detail_index[i] for move in native if move['id'] in raw_ids for i in move['move_line_ids']]
        needed=defaultdict(float);owned=defaultdict(float)
        for move in native:
            if move['id'] not in raw_ids:continue
            for line_id in move['move_line_ids']:
                line=detail_index[line_id];pid=rid(line['product_id']);unit=rid(line['product_uom_id']);base=rid(self.tp[pid]['uom_id']);key=(pid,rid(line['location_id']),rid(line['lot_id']))
                amount=line['quantity']*self.tu[unit]['factor']/self.tu[base]['factor'];needed[key]+=amount
                if move['state'] in ['assigned','partially_available']:owned[key]+=amount
        quant_readback=[]
        for (pid,location,lot),amount in needed.items():
            quants=self.b.scan('stock.quant',[['company_id','=',1],['product_id','=',pid],['location_id','=',location],['lot_id','=',lot],['package_id','=',False],['owner_id','=',False]],['quantity','reserved_quantity'])
            quantity=sum(x['quantity'] for x in quants);reserved=sum(x['reserved_quantity'] for x in quants)
            if quantity+1e-6<reserved or quantity-reserved+min(owned[(pid,location,lot)],reserved)+1e-6<amount:raise RuntimeError('Expiry confirmation stock/reservation gate failed')
            quant_readback.append({'key':[pid,location,lot],'quants':quants,'own_reserved':owned[(pid,location,lot)],'required':amount})
        approval=load('operator-expiry-confirmation-approval.json')
        lots=runpy.run_path(str(Path(__file__).with_name('historical_expiry_confirmation_guard.py')))['authorize'](approval,hashlib.sha256((OUT/'scope.json').read_bytes()).hexdigest(),s,mo,native,warning,[rid(x['lot_id']) for x in raw_lines if x['lot_id']])
        lot_fields=['name','product_id','expiration_date','use_date','removal_date','alert_date']
        before_lots=self.b.read('stock.lot',lots,lot_fields)
        rec['expiry_confirmation']={'operator_approval':'operator-expiry-confirmation-approval.json','before_mo':mo,'before_moves':native,'before_lines':details,'before_lots':before_lots,'quants':quant_readback,'warning':warning};self.persist()
        context={'default_lot_ids':[(6,0,lots)],'default_production_ids':[tid],'skip_backorder':True,'skip_redirection':True}
        wid=self.mutate('expiry.picking.confirmation','create',[{'production_ids':[(6,0,[tid])],'lot_ids':[(6,0,lots)]}],context)
        wizard=self.b.read('expiry.picking.confirmation',[wid],['production_ids','lot_ids','picking_ids','workorder_id'])[0]
        if wizard['production_ids']!=[tid] or set(wizard['lot_ids'])!=set(lots) or wizard['picking_ids'] or wizard['workorder_id']:raise RuntimeError('Created expiry wizard scope drift')
        rec['status']='expiry_confirming';rec['expiry_confirmation']['wizard']=wizard;self.persist()
        result=self.mutate('expiry.picking.confirmation','confirm_produce',[[wid]],context)
        actual=self.b.read('mrp.production',[tid],['state','qty_produced'])[0]
        if actual['state']!='done':raise RuntimeError('Expiry confirmation returned another wizard; do not repeat: '+str(result))
        rec['status']='done_pending_verification';self.persist()
        after_lots=self.b.read('stock.lot',lots,lot_fields)
        if before_lots!=after_lots:raise RuntimeError('Expiry metadata unexpectedly changed')
        rec['expiry_confirmation']['after_lots']=after_lots
        self.restore_and_verify(s,rec,pairs)
        rec['execution_hold']=False;rec['expiry_confirmation']['verified_utc']=datetime.now(timezone.utc).isoformat();self.persist()
    def restore_and_verify(self,s,rec,pairs):
        tid=rec['target_id']
        current=self.b.read('mrp.production',[tid],['state','date_start','qty_produced','product_qty'])[0]
        if current['state']!='done' or current['date_start']!=s['date_planned_start'] or abs(current['qty_produced']-s['qty_produced'])>1e-6:raise RuntimeError('MO done/date-start/quantity recovery gate failed')
        self.mutate('mrp.production','write',[[tid],{'date_finished':s['date_finished']}])
        for mid,tmid in pairs.items():
            self.mutate('stock.move','write',[[tmid],{'date':self.moves[mid]['date']}])
            for x in self.lines[mid]:self.mutate('stock.move.line','write',[[self.mapped('stock.move.line',x['id'])],{'date':x['date']}])
        rows=self.b.read('stock.move',list(pairs.values()),['state','quantity','product_uom_qty','date','move_line_ids'])
        for row in rows:
            mid=next(i for i,j in pairs.items() if j==row['id']);expected=self.lines[mid]
            if abs(row['product_uom_qty']-self.demand_qty(s,self.moves[mid]))>1e-8:raise RuntimeError('Final MO demand mismatch')
            got=self.b.read('stock.move.line',row['move_line_ids'],['product_id','product_uom_id','location_id','location_dest_id','lot_id','quantity','date','owner_id','package_id','result_package_id'])
            want=Counter((self.mapped('product.product',rid(x['product_id'])),self.mapped('uom.uom',rid(x['product_uom_id'])),self.mapped('stock.location',rid(x['location_id'])),self.mapped('stock.location',rid(x['location_dest_id'])),self.lot(rid(x['lot_id'])),self.qty(x),x['date']) for x in expected)
            have=Counter((rid(x['product_id']),rid(x['product_uom_id']),rid(x['location_id']),rid(x['location_dest_id']),rid(x['lot_id']),x['quantity'],x['date']) for x in got)
            if row['state']!='done' or row['date']!=self.moves[mid]['date'] or want!=have or any(x['owner_id'] or x['package_id'] or x['result_package_id'] for x in got):raise RuntimeError('MO detailed read-back mismatch')
        header=self.b.read('mrp.production',[tid],['name','company_id','product_id','product_uom_id','product_qty','state','qty_produced','date_start','date_finished','origin','x_studio_reference_no'])[0]
        if header['state']!='done' or abs(header['qty_produced']-s['qty_produced'])>1e-6 or abs(header['product_qty']-s['product_qty'])>1e-6 or header['date_finished']!=s['date_finished'] or header['date_start']!=s['date_planned_start']:raise RuntimeError('MO header read-back mismatch')
        rec.update(status='verified_done',after=header,verified_moves=rows,verified_utc=datetime.now(timezone.utc).isoformat());self.persist();print(json.dumps({'completed_mo':s['name'],'target_id':tid,'moves':len(pairs)}),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['sample','batch'],default='sample');p.add_argument('--limit',type=int,default=10);p.add_argument('--recover-dates-only',type=int);p.add_argument('--recover-unconsumed',type=int);p.add_argument('--confirm-expiry',type=int);args=p.parse_args();r=Run()
    write_lock=runpy.run_path(str(Path(__file__).with_name('production_write_lock.py')))['acquire'](OUT)
    if args.confirm_expiry:
        r.confirm_expiry(args.confirm_expiry);return
    if args.recover_unconsumed:
        r.recover_unconsumed(args.recover_unconsumed);return
    if args.recover_dates_only:
        sid=args.recover_dates_only;s=r.mos[sid];rec=r.j['mos'][str(sid)]
        if rec['status']!='done_pending_verification':raise RuntimeError('Date recovery requires already-done journal status')
        mids=[i for i in s['move_raw_ids']+s['move_finished_ids'] if i in r.moves]
        pairs={mid:r.mapped('stock.move',mid) for mid in mids}
        rows=r.b.read('stock.move',list(pairs.values()),['state','quantity'])
        for x in rows:
            mid=next(i for i,j in pairs.items() if j==x['id'])
            if x['state']!='done' or abs(x['quantity']-sum(r.qty(z) for z in r.lines[mid]))>1e-6:raise RuntimeError('Done raw/finished quantities must match before date recovery')
        r.restore_and_verify(s,rec,pairs);return
    if args.mode=='batch' and not any(x['status']=='verified_done' for x in r.j['mos'].values()):raise RuntimeError('Successful MO sample required')
    rows=sorted([x for x in r.plan['rows'] if x['eligible'] and r.j['mos'].get(str(x['source_mo']),{}).get('status')!='verified_done'],key=lambda x:(x['event_utc'],x['source_mo']))
    selected=rows[:1 if args.mode=='sample' else args.limit]
    if args.mode=='batch' and selected:
        proven={r.flow({'source_mo':int(sid)}) for sid,state in r.j['mos'].items() if state['status']=='verified_done'}
        if r.flow(selected[0]) not in proven:
            selected=selected[:1];print(json.dumps({'new_mo_flow_sample':r.flow(selected[0]),'source_mo':selected[0]['name']}),flush=True)
        else:selected=selected[:next((i for i,x in enumerate(selected) if r.flow(x) not in proven),len(selected))]
    for x in selected:r.process(x)
    print(json.dumps({'verified_mos':sum(x['status']=='verified_done' for x in r.j['mos'].values())}),flush=True)

if __name__=='__main__':main()
