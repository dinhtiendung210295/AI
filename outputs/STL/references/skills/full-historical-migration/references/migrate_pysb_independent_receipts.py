"""Production PO receipt chains, strict full-chain matching and native validation.

Only complete, self-supplied vendor->warehouse chains are eligible. No master
changes, no arbitrary reservation cleanup, no retries of uncertain RPC writes.
"""
import argparse
import copy
import json
import runpy
import socket
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

BASE=Path(__file__).resolve().parent
I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'))
ROOT,OUT,ReadOnly=I['ROOT'],I['OUT'],I['ReadOnly']
Reader=I['Reader']
WORKFLOW=runpy.run_path(str(BASE/'production_workflow_rpc.py'))
def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False
def load(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def save(n,d):I['save'](n,d)
def idx(rows):return {r['id']:r for r in rows}
def rounded(q,r):return float((Decimal(str(q))/Decimal(str(r))).quantize(Decimal('1'),rounding=ROUND_HALF_UP)*Decimal(str(r)))
def equivalent_demand(old_unit,old_qty,new_unit,new_qty,units):
    def root(unit):
        seen=set()
        while unit and unit in units and unit not in seen:
            seen.add(unit);parent=rid(units[unit].get('relative_uom_id'))
            if not parent:return unit
            unit=parent
        return None
    return bool(root(old_unit) and root(old_unit)==root(new_unit) and
                abs(old_qty*units[old_unit]['factor']-new_qty*units[new_unit]['factor'])<=1e-6)

def assert_exact_stock(needed,quants):
    totals=defaultdict(lambda:[0.0,0.0])
    for q in quants:
        key=(rid(q['product_id']),rid(q['location_id']),rid(q['lot_id']))
        totals[key][0]+=q['quantity'];totals[key][1]+=q['reserved_quantity']
    for key,qty in needed.items():
        quantity,reserved=totals[key]
        if quantity+1e-6<qty:raise RuntimeError('Live internal quantity insufficient at exact lot/location')
        if quantity+1e-6<reserved:raise RuntimeError('Live stock over-reserved; separate review required')
CTX={'allowed_company_ids':[1],'active_test':False,'tz':'UTC','tracking_disable':True,'mail_notrack':True,'mail_create_nolog':True,'mail_create_nosubscribe':True,'mail_auto_subscribe_no_notify':True,'send_email':False}

class Run:
    def __init__(self):
        socket.setdefaulttimeout(120)
        self.a=ReadOnly('v14-prod',('http://175.145.85.151','paoyeang_live'))
        self.b=ReadOnly('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
        self.scope=load('scope.json')
        assert self.scope['complete'] and self.scope['backup_acknowledged_by_operator']
        self.maps={m:{int(s):t for s,t in v.items()} for m,v in load('discovery-manifest.json')['maps'].items()}
        self.maps=runpy.run_path(str(BASE/'stock_confirmation_handoff.py'))['apply'](self.maps,OUT)
        self.sm=idx(load('source-moves.json'));self.sp=idx(load('source-pickings.json'))
        self.sl=idx(load('source-move-lines.json'));self.by_move=defaultdict(list)
        for line in self.sl.values():self.by_move[rid(line['move_id'])].append(line)
        self.locations=idx(load('source-stock.location.json'));self.tu=idx(load('target-uom.uom.json'))
        self.tp=idx(load('target-products.json'))
        self.held_products={x['source_id'] for x in load('native-opening-comparison.json')['rows'] if not x['exact_quantity_match']}
        self.held_products.update(x['source_id'] for x in load('resolved-master-evidence.json')['issues'] if x['model']=='product.product')
        self.move_issues={x['source_move']:x['missing'] for x in load('discovery-manifest.json')['moves'] if x['missing']}
        self.j=load('independent-receipts-journal.json') if (OUT/'independent-receipts-journal.json').exists() else {
            'database':self.b.r.db,'company_id':1,'started_utc':datetime.now(timezone.utc).isoformat(),
            'authorization':{'rounding':'Operator approved rounding by target UoM with individual differences recorded','hold':'Operator requested held groups remain pending; execute independent groups','backup':'Operator confirmed backup exists'},
            'operations':[],'groups':{},'maps':{},'rounding_differences':[]}
        for m,pairs in self.j['maps'].items():self.maps.setdefault(m,{}).update({int(s):t for s,t in pairs.items()})
        self.uncertain=[x for x in self.j['operations'] if x['status'] in {'intent','uncertain'}]

    def persist(self):
        self.j['maps']={m:v for m,v in self.maps.items() if m in {'stock.picking','stock.move','stock.move.line','stock.lot'}}
        save('independent-receipts-journal.json',self.j)

    def mutate(self,model,method,args,context=None,jsonrpc=False):
        WORKFLOW['GUARD']()
        if self.uncertain:raise RuntimeError('Uncertain earlier mutation requires read-back recovery')
        kwargs=WORKFLOW['workflow_options']({'context':{**CTX,**(context or {})}})
        op={'model':model,'method':method,'args':copy.deepcopy(args),'kwargs':kwargs,'status':'intent','utc':datetime.now(timezone.utc).isoformat()}
        self.j['operations'].append(op);self.persist()
        try:
            if jsonrpc:
                r=self.b.r
                body={'jsonrpc':'2.0','method':'call','id':len(self.j['operations']),'params':{'service':'object','method':'execute_kw','args':[r.db,r.uid,r.secret,model,method,args,kwargs]}}
                req=urllib.request.Request(r.url+'/jsonrpc',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(req,timeout=120) as response: result=json.load(response)
                if 'error' in result:raise RuntimeError(str(result['error']))
                if 'result' not in result and (method=='do_unreserve' or (model=='stock.quant' and method=='action_apply_inventory')):
                    op['response_without_result']={'keys':sorted(result),'id':result.get('id')}
                    value=None  # Caller must verify zero quantities/empty lines.
                else:value=result['result']
            else:value=WORKFLOW['call'](self.b.r,model,method,args,kwargs)
            op['status']='returned';op['result']=value;self.persist();return value
        except Exception as e:
            op['status']='uncertain';op['error']=str(e);self.uncertain=[op];self.persist();raise

    def attach(self,model,sid,tid):
        name=model.replace('.','_')+'_'+str(sid)
        rows=self.b.call('ir.model.data','search_read',[[['module','=','pysb_v14'],['name','=',name]]],{'fields':['model','res_id'],'limit':2})
        if rows:
            if len(rows)!=1 or rows[0]['model']!=model or rows[0]['res_id']!=tid:raise RuntimeError('External ID conflict')
        else:self.mutate('ir.model.data','create',[{'module':'pysb_v14','name':name,'model':model,'res_id':tid,'noupdate':True}])
        self.maps.setdefault(model,{})[sid]=tid;self.persist()

    def attach_many(self,model,pairs):
        if not pairs:return
        if len({s for s,t in pairs})!=len(pairs) or len({t for s,t in pairs})!=len(pairs):raise RuntimeError('Non-unique batch mapping')
        names={model.replace('.','_')+'_'+str(s):(s,t) for s,t in pairs}
        existing=self.b.call('ir.model.data','search_read',[[['module','=','pysb_v14'],['name','in',list(names)]]],{'fields':['name','model','res_id'],'limit':len(names)+1})
        found={};values=[]
        for row in existing:
            if row['name'] in found:raise RuntimeError('Duplicate batch external ID')
            found[row['name']]=row
        for name,(sid,tid) in names.items():
            old=found.get(name)
            if old and (old['model']!=model or old['res_id']!=tid):raise RuntimeError('Batch external ID conflict')
            if not old:values.append({'module':'pysb_v14','name':name,'model':model,'res_id':tid,'noupdate':True})
        if values:self.mutate('ir.model.data','create',[values])
        self.maps.setdefault(model,{}).update(dict(pairs));self.persist()

    def plan(self):
        line_ids={rid(m['purchase_line_id']) for m in self.sm.values() if m.get('purchase_line_id')}
        fields='order_id product_id product_uom product_qty qty_received price_unit discount taxes_id price_subtotal price_total display_type name date_planned write_date'.split()
        pol=self.a.read('purchase.order.line',line_ids,fields)
        order_ids={rid(x['order_id']) for x in pol}
        sources=self.a.read('purchase.order',order_ids,'name state company_id partner_id partner_ref currency_id date_order date_approve order_line picking_ids amount_untaxed amount_tax amount_total write_date'.split())
        all_lines=self.a.read('purchase.order.line',[i for x in sources for i in x['order_line']],fields)
        spl=idx(all_lines)
        tids=[self.maps.get('purchase.order',{}).get(s['id']) for s in sources]
        targets=idx(self.b.read('purchase.order',tids,'name state company_id partner_id partner_ref currency_id date_order date_approve order_line picking_ids invoice_ids amount_untaxed amount_tax amount_total write_date x_studio_v14_reference_studio'.split()))
        target_lines=idx(self.b.read('purchase.order.line',[i for x in targets.values() for i in x['order_line']], 'order_id product_id product_uom_id product_qty price_unit discount tax_ids price_subtotal price_total display_type name date_planned'.split()))
        source_picks=idx(self.a.read('stock.picking',[i for s in sources for i in s['picking_ids']],['name','state','date_done','move_lines']))
        product_ids={rid(x['product_id']) for x in target_lines.values() if x['product_id']}
        prods=idx(self.b.read('product.product',product_ids,['product_tmpl_id','seller_ids','name','tracking','uom_id','type']))
        source_products=idx(self.a.read('product.product',{rid(x['product_id']) for x in all_lines if x['product_id']},['type']))
        service_line_check=runpy.run_path(str(BASE/'receipt_service_line.py'))['nonphysical_service']
        sellers=idx(self.b.read('product.supplierinfo',[i for x in prods.values() for i in x['seller_ids']],['partner_id']))
        partners=idx(self.b.read('res.partner',[rid(x['partner_id']) for x in targets.values()],['parent_id']))
        groups=[]
        for s in sources:
            tid=self.maps.get('purchase.order',{}).get(s['id']);t=targets.get(tid);issues=[]
            mids={m['id'] for m in self.sm.values() if rid(m.get('purchase_line_id')) in s['order_line']}
            picks={rid(self.sm[i]['picking_id']) for i in mids if self.sm[i]['picking_id']}
            # Follow the complete receipt chain even when a push move loses purchase_line_id.
            changed=True
            while changed:
                changed=False
                for i in list(mids):
                    for dest in self.sm[i]['move_dest_ids']:
                        m=self.sm.get(dest)
                        if m and not m.get('sale_line_id') and rid(m.get('purchase_line_id')) in set(s['order_line'])|{False} and self.locations[rid(m['location_dest_id'])]['usage']=='internal' and dest not in mids:
                            mids.add(dest);picks.add(rid(m['picking_id']));changed=True
            picks.discard(False)
            root_picks={rid(self.sm[i]['picking_id']) for i in mids if self.locations[rid(self.sm[i]['location_id'])]['usage']=='supplier'}
            if len(root_picks)>1:issues.append('multiple_source_receipts_need_native_picking_split')
            for p in picks:
                if p not in self.sp:issues.append('missing_full_picking_snapshot');continue
                if any(m['id'] not in mids for m in self.sm.values() if rid(m.get('picking_id'))==p):issues.append('picking_contains_other_business_group')
            if not t:issues.append('missing_target_order')
            if s['state'] not in ['purchase','done']:issues.append('source_order_not_confirmed')
            if t:
                if rid(t['company_id'])!=1 or t.get('x_studio_v14_reference_studio')!=s['name']:issues.append('target_identity_mismatch')
                if t['state'] not in ['draft','sent','purchase']:issues.append('target_state_not_supported')
                if {self.maps.get('purchase.order.line',{}).get(i) for i in s['order_line']}!=set(t['order_line']):issues.append('order_lines_not_exactly_mapped')
                if t['currency_id'][1]!={'CNH':'CNY'}.get(s['currency_id'][1],s['currency_id'][1]):issues.append('currency_mismatch')
                for k in ['amount_untaxed','amount_tax','amount_total']:
                    if abs(s[k]-t[k])>0.010001:issues.append('commercial_total_mismatch:'+k)
                if t['state'] in ['draft','sent'] and t['picking_ids']:issues.append('draft_order_already_has_pickings')
                vendor={rid(t['partner_id']),rid(partners[rid(t['partner_id'])]['parent_id'])}
            else:vendor=set()
            for lid in s['order_line']:
                sl=spl[lid];tl=target_lines.get(self.maps.get('purchase.order.line',{}).get(lid))
                if sl.get('display_type'):continue
                nonphysical=service_line_check(sl,tl,source_products.get(rid(sl['product_id'])),prods.get(rid(tl['product_id'])) if tl else None,self.sm.values())
                if abs(sl['qty_received']-sl['product_qty'])>1e-6 and not nonphysical:issues.append('partial_or_returned_order_requires_separate_handling')
                roots=[self.sm[i] for i in mids if rid(self.sm[i].get('purchase_line_id'))==lid and self.locations[rid(self.sm[i]['location_id'])]['usage']=='supplier']
                if roots and (len(roots)!=1 or abs(roots[0]['product_uom_qty']-sl['product_qty'])>1e-6):issues.append('split_receipts_require_separate_preparation')
                if not tl:continue
                if rid(tl['product_id'])!=self.maps.get('product.product',{}).get(rid(sl['product_id'])):issues.append('line_product_mapping_mismatch')
                if rid(tl['product_uom_id'])!=self.maps.get('uom.uom',{}).get(rid(sl['product_uom'])):issues.append('line_unit_mapping_mismatch')
                for f in ['product_qty','price_unit','discount','price_subtotal','price_total']:
                    if f in sl and f in tl and abs(sl[f]-tl[f])>1e-6:issues.append('commercial_line_mismatch:'+f)
                p=prods.get(rid(tl['product_id']))
                if p and len(p['seller_ids'])<=10 and not vendor.intersection(rid(sellers[i]['partner_id']) for i in p['seller_ids']):issues.append('confirmation_would_create_supplier_master')
            active=[source_picks[i] for i in s['picking_ids'] if source_picks[i]['state']!='cancel']
            if any(p['state']!='done' or not (self.scope['start_utc']<=p['date_done']<self.scope['end_utc_exclusive']) for p in active):issues.append('source_order_has_pending_or_outside_period_receipt')
            for i in mids:
                m=self.sm[i]
                if rid(m['product_id']) in self.held_products:issues.append('held_opening_or_tracking_product')
                if i in self.move_issues:issues.append('unresolved_move_mapping')
                own=self.j['groups'].get(str(s['id']),{})
                owned_pair=own.get('move_pairs',{}).get(str(i),own.get('move_pairs',{}).get(i))
                if i in self.maps.get('stock.move',{}) and own.get('phase')!='completed' and owned_pair!=self.maps['stock.move'][i]:issues.append('preexisting_source_mapping_requires_separate_review')
                if m.get('origin_returned_move_id'):issues.append('return_requires_separate_handling')
                if self.locations[rid(m['location_dest_id'])]['usage']!='internal':issues.append('not_vendor_to_warehouse_chain')
                for line in self.by_move[i]:
                    if line['package_id'] or line['result_package_id'] or line['owner_id']:issues.append('package_or_owner_requires_separate_handling')
            if not mids or not picks:issues.append('no_complete_receipt_chain')
            # Prove this chain supplies its own internal consumption from vendor
            # receipts; never borrow unrelated opening or future target inventory.
            balances=defaultdict(float)
            for spid in sorted(picks,key=lambda i:(self.sp[i]['date_done'],i)):
                outgoing=defaultdict(float);incoming=defaultdict(float)
                for mid in mids:
                    move=self.sm[mid]
                    if rid(move['picking_id'])!=spid:continue
                    product=self.maps.get('product.product',{}).get(rid(move['product_id']))
                    target_product=self.tp.get(product)
                    if not target_product or not target_product.get('is_storable'):continue
                    for line in self.by_move[mid]:
                        unit=self.maps.get('uom.uom',{}).get(rid(line['product_uom_id']))
                        if not unit:continue
                        qty=rounded(line['qty_done'],self.tu[unit]['rounding'])*self.tu[unit]['factor']/self.tu[rid(target_product['uom_id'])]['factor']
                        if qty<=0:issues.append('nonpositive_effective_done_quantity')
                        src=(product,rid(line['location_id']),rid(line['lot_id']))
                        dst=(product,rid(line['location_dest_id']),rid(line['lot_id']))
                        if self.locations[src[1]]['usage']=='internal':outgoing[src]+=qty
                        if self.locations[dst[1]]['usage']=='internal':incoming[dst]+=qty
                if any(balances[k]+1e-6<q for k,q in outgoing.items()):issues.append('chain_requires_unproven_opening_or_future_supply')
                for k,q in outgoing.items():balances[k]-=q
                for k,q in incoming.items():balances[k]+=q
            groups.append({'source':s,'target':t,'source_lines':[spl[i] for i in s['order_line']],
                           'target_lines':[target_lines[i] for i in t['order_line']] if t else [],
                           'moves':sorted(mids),'pickings':sorted(picks),'issues':sorted(set(issues)),
                           'date':min((self.sp[i]['date_done'] for i in picks),default='')})
        groups.sort(key=lambda x:(x['date'],x['source']['id']))
        save('independent-receipts-manifest.json',{'write_ready':True,'scope':self.scope,'groups':groups,
             'eligibility':'Full source receipt chain, exact imported PO lines, no held products, no supplier master addition; live generated-move match and stock gate required before validation',
             'summary':{'groups':len(groups),'eligible':sum(not g['issues'] for g in groups),'held':sum(bool(g['issues']) for g in groups),'hold_reasons':dict(Counter(i for g in groups for i in g['issues']))}})
        print(json.dumps({'groups':len(groups),'eligible':sum(not g['issues'] for g in groups),'held':sum(bool(g['issues']) for g in groups)}),flush=True)
        return groups

    def target_chain(self,order_id):
        order=self.b.read('purchase.order',[order_id],['picking_ids'])[0]
        picks=self.b.read('stock.picking',order['picking_ids'],['state','company_id','move_ids'])
        mids={i for p in picks for i in p['move_ids']};rows={};frontier=mids
        fields='state company_id product_id product_uom product_uom_qty quantity location_id location_dest_id picking_id move_orig_ids move_dest_ids move_line_ids purchase_line_id'.split()
        while frontier:
            batch=self.b.read('stock.move',frontier,fields);rows.update(idx(batch))
            frontier={i for x in batch for i in x['move_dest_ids']}-set(rows)
        return list(rows.values())

    def process(self,g,prepare_only=False):
        sid=g['source']['id'];tid=g['target']['id'];key=str(sid)
        if self.j['groups'].get(key,{}).get('phase')=='completed':return
        if g['issues']:raise RuntimeError('Attempt to process held group')
        state=self.j['groups'].setdefault(key,{'source_name':g['source']['name'],'target_order':tid,'phase':'preflight_passed'})
        self.persist()
        source_now=self.a.read('purchase.order',[sid],list(g['source']))[0]
        if source_now!=g['source']:raise RuntimeError('Source PO changed after preparation')
        before=self.b.read('purchase.order',[tid],list(g['target']))[0]
        if before!=g['target']:raise RuntimeError('Target PO changed after preparation')
        supplier_products={rid(l['product_id']) for l in g['target_lines'] if l['product_id']}
        supplier_before=self.b.read('product.product',supplier_products,['seller_ids'])
        invoice_before=self.b.call('account.move','search_count',[[['company_id','=',1],['move_type','in',['out_invoice','in_invoice','out_refund','in_refund']]]])
        state['invoice_count_before']=invoice_before;self.persist()
        if before['state'] in ['draft','sent']:
            self.mutate('purchase.order','button_confirm',[[tid]])
            self.mutate('purchase.order','write',[[tid],{'date_approve':g['source']['date_approve']}])
        current=self.b.read('purchase.order',[tid],['state','date_approve'])[0]
        if current['state']!='purchase' or current['date_approve']!=g['source']['date_approve']:raise RuntimeError('PO confirmation/date verification failed')
        if self.b.read('product.product',supplier_products,['seller_ids'])!=supplier_before:raise RuntimeError('Supplier master changed unexpectedly')
        state['phase']='order_confirmed';self.persist()
        native=self.target_chain(tid);used=set();pairs={};target_picking={}
        if any(rid(x['company_id'])!=1 or x['state'] in ['done','cancel'] for x in native):raise RuntimeError('Generated chain already done/cancel or wrong company')
        for smid in g['moves']:
            s=self.sm[smid]
            matches=[t for t in native if t['id'] not in used and
                     rid(t['product_id'])==self.maps['product.product'][rid(s['product_id'])] and
                     rid(t['product_uom'])==self.maps['uom.uom'][rid(s['product_uom'])] and
                     rid(t['location_id'])==self.maps['stock.location'][rid(s['location_id'])] and
                     rid(t['location_dest_id'])==self.maps['stock.location'][rid(s['location_dest_id'])] and
                     abs(t['product_uom_qty']-s['product_uom_qty'])<1e-6 and
                     (not s['purchase_line_id'] or rid(t['purchase_line_id'])==self.maps['purchase.order.line'][rid(s['purchase_line_id'])])]
            if not matches:
                expected_unit=self.maps['uom.uom'][rid(s['product_uom'])]
                equivalents=[t for t in native if t['id'] not in used and
                    rid(t['product_id'])==self.maps['product.product'][rid(s['product_id'])] and
                    rid(t['location_id'])==self.maps['stock.location'][rid(s['location_id'])] and
                    rid(t['location_dest_id'])==self.maps['stock.location'][rid(s['location_dest_id'])] and
                    s['purchase_line_id'] and rid(t['purchase_line_id'])==self.maps['purchase.order.line'][rid(s['purchase_line_id'])] and
                    equivalent_demand(rid(t['product_uom']),t['product_uom_qty'],expected_unit,s['product_uom_qty'],self.tu)]
                if len(equivalents)==1:
                    t=equivalents[0]
                    checks=self.b.read('stock.move.line',t['move_line_ids'],['picked','state'])
                    if any(x['picked'] or x['state']=='done' for x in checks):raise RuntimeError('Equivalent-unit move already picked/done')
                    state.setdefault('unit_normalizations',[]).append({'source_move':smid,'target_move':t['id'],'old_unit':rid(t['product_uom']),'new_unit':expected_unit,'old_demand':t['product_uom_qty'],'new_demand':s['product_uom_qty'],'proof':'same unit root and same base quantity; unpicked and not done'})
                    self.persist()
                    self.mutate('stock.move','write',[[t['id']],{'product_uom':expected_unit,'product_uom_qty':s['product_uom_qty']}])
                    t.update(self.b.read('stock.move',[t['id']],list(t))[0]);matches=[t]
            if not matches and self.locations[rid(s['location_id'])]['usage']=='internal' and self.locations[rid(s['location_dest_id'])]['usage']=='internal' and not s['purchase_line_id'] and not s['sale_line_id']:
                predecessors=[pairs[i] for i in s['move_orig_ids'] if i in pairs]
                if not predecessors or len(predecessors)!=len(s['move_orig_ids']):raise RuntimeError('Missing internal receipt predecessor')
                spid=rid(s['picking_id']);sp=self.sp[spid]
                if spid not in target_picking:
                    target_picking[spid]=self.mutate('stock.picking','create',[{'company_id':1,'picking_type_id':self.maps['stock.picking.type'][rid(sp['picking_type_id'])],
                        'location_id':self.maps['stock.location'][rid(sp['location_id'])],'location_dest_id':self.maps['stock.location'][rid(sp['location_dest_id'])],
                        'scheduled_date':sp['scheduled_date'],'origin':sp['origin'],'partner_id':rid(before['partner_id'])}])
                    self.attach('stock.picking',spid,target_picking[spid])
                values={'company_id':1,'product_id':self.maps['product.product'][rid(s['product_id'])],
                        'product_uom':self.maps['uom.uom'][rid(s['product_uom'])],'product_uom_qty':s['product_uom_qty'],
                        'location_id':self.maps['stock.location'][rid(s['location_id'])],'location_dest_id':self.maps['stock.location'][rid(s['location_dest_id'])],
                        'picking_id':target_picking[spid],'state':'confirmed','procure_method':'make_to_stock','propagate_cancel':False,'rule_id':False,
                        'move_orig_ids':[(6,0,predecessors)],'date':s['date']}
                if 'location_final_id' in self.b.fields('stock.move',['location_final_id']):values['location_final_id']=values['location_dest_id']
                new_id=self.mutate('stock.move','create',[values])
                created=self.b.read('stock.move',[new_id],list(native[0]))[0]
                native.append(created);matches=[created]
            if len(matches)!=1:
                state['mapping_mismatch']={'source_move':s,'native_moves':native};self.persist()
                raise RuntimeError('Ambiguous generated source move match: '+str(smid))
            t=matches[0];pairs[smid]=t['id'];used.add(t['id'])
            spid=rid(s['picking_id']);tpid=rid(t['picking_id'])
            if spid in target_picking and target_picking[spid]!=tpid:raise RuntimeError('Source picking split unexpectedly')
            target_picking[spid]=tpid
        if used!={x['id'] for x in native}:raise RuntimeError('Unexpected additional native moves')
        if len(set(target_picking.values()))!=len(target_picking):raise RuntimeError('Target picking shared by source pickings')
        state['move_pairs']=pairs;state['picking_pairs']=target_picking;state['phase']='native_chain_matched';self.persist()
        for s,t in pairs.items():self.attach('stock.move',s,t)
        for s,t in target_picking.items():self.attach('stock.picking',s,t)
        # All target moves in this chain were just generated and have not been done.
        existing=self.b.read('stock.move.line',[i for m in native for i in m['move_line_ids']],['picked','state'])
        if any(x['picked'] or x['state']=='done' for x in existing):raise RuntimeError('Generated operations already picked; separate review required')
        if not state.get('unreserved'):
            self.mutate('stock.picking','do_unreserve',[list(target_picking.values())],jsonrpc=True)
            check=self.b.read('stock.move',list(pairs.values()),['quantity','move_line_ids'])
            if any(abs(x['quantity'])>1e-8 or x['move_line_ids'] for x in check):raise RuntimeError('Unreserve postcondition not verified')
            state['unreserved']=True;self.persist()
        remaining=self.b.scan('stock.move.line',[['move_id','in',list(pairs.values())]],['picked','state','quantity'])
        if remaining:
            if any(x['picked'] or x['state']=='done' for x in remaining):raise RuntimeError('Unreserve left picked/done lines')
            self.mutate('stock.move.line','unlink',[[x['id'] for x in remaining]])
        # Reuse unique lots, creating only missing lots required by the selected chain.
        line_ids=[i for s in g['moves'] for i in self.sm[s]['move_line_ids']]
        lot_ids={rid(self.sl[i]['lot_id']) for i in line_ids if self.sl[i]['lot_id']}
        source_lots=self.a.read('stock.production.lot',lot_ids,'name product_id company_id expiration_date use_date removal_date alert_date'.split())
        for lot in source_lots:
            product=self.maps['product.product'][rid(lot['product_id'])]
            found=self.b.call('stock.lot','search_read',[[['company_id','=',1],['product_id','=',product],['name','=',lot['name']]]],{'fields':['name','product_id'],'limit':2})
            if not found:
                complete=self.b.scan('stock.lot',[['company_id','=',1],['product_id','=',product]],['name','product_id','company_id'])
                found=[x for x in complete if x['name']==lot['name'] and rid(x['product_id'])==product and rid(x['company_id'])==1]
                self.j.setdefault('lot_lookup_readbacks',[]).append({'source_lot':lot['id'],'source_name':lot['name'],'target_product':product,'complete_product_company_lot_ids':[x['id'] for x in complete],'exact_api_matches':found});self.persist()
            if len(found)>1:raise RuntimeError('Ambiguous lot')
            if found:lot_tid=found[0]['id']
            else:
                values={'company_id':1,'product_id':product,'name':lot['name']}
                values.update({k:lot[k] for k in ['expiration_date','use_date','removal_date','alert_date'] if lot.get(k) and k in self.b.fields('stock.lot',[k])})
                lot_tid=self.mutate('stock.lot','create',[values])
            self.attach('stock.lot',lot['id'],lot_tid)
        if prepare_only:
            state['phase']='chain_prepared';self.persist();return
        for i in line_ids:
            x=self.sl[i];unit=self.maps['uom.uom'][rid(x['product_uom_id'])];qty=rounded(x['qty_done'],self.tu[unit]['rounding'])
            if abs(qty-x['qty_done'])>1e-8:
                self.j['rounding_differences'].append({'source_line':i,'source_move':rid(x['move_id']),'source_qty':x['qty_done'],'target_qty':qty,'target_unit':unit,'delta':qty-x['qty_done']});self.persist()
            values={'company_id':1,'move_id':pairs[rid(x['move_id'])],'product_id':self.maps['product.product'][rid(x['product_id'])],
                    'product_uom_id':unit,'location_id':self.maps['stock.location'][rid(x['location_id'])],'location_dest_id':self.maps['stock.location'][rid(x['location_dest_id'])],
                    'lot_id':self.maps.get('stock.lot',{}).get(rid(x['lot_id']),False),'quantity':qty,'picked':True,'date':x['date']}
            lid=self.mutate('stock.move.line','create',[values]);self.attach('stock.move.line',i,lid)
        state['phase']='details_prepared';self.persist()
        return self.finish(g)

    def prepare_picking_lines(self,g,spid):
        state=self.j['groups'][str(g['source']['id'])]
        pairs={int(s):t for s,t in state['move_pairs'].items()}
        tpid=state['picking_pairs'].get(str(spid),state['picking_pairs'].get(spid))
        source_ids=[i for mid in g['moves'] if rid(self.sm[mid]['picking_id'])==spid for i in self.sm[mid]['move_line_ids']]
        if all(i in self.maps.get('stock.move.line',{}) for i in source_ids):return
        fresh_source=self.a.read('stock.move.line',source_ids,list(self.sl[source_ids[0]])) if source_ids else []
        if any(x!=self.sl[x['id']] for x in fresh_source):raise RuntimeError('Source detailed operations changed since frozen snapshot')
        source_moves=[mid for mid in g['moves'] if rid(self.sm[mid]['picking_id'])==spid]
        check_fields=['state','date','quantity_done','product_id','product_uom','location_id','location_dest_id','move_line_ids','write_date']
        fresh_moves=self.a.read('stock.move',source_moves,check_fields)
        if any(any(x[f]!=self.sm[x['id']][f] for f in check_fields) for x in fresh_moves):raise RuntimeError('Source stock moves changed since frozen snapshot')
        current=self.b.scan('stock.move.line',[['move_id','in',[pairs[mid] for mid in g['moves'] if rid(self.sm[mid]['picking_id'])==spid]]],['picked','state'])
        if any(x['picked'] or x['state']=='done' for x in current):raise RuntimeError('Picking has preexisting picked/done operations')
        self.mutate('stock.picking','do_unreserve',[[tpid]],jsonrpc=True)
        after=self.b.read('stock.move',[pairs[mid] for mid in g['moves'] if rid(self.sm[mid]['picking_id'])==spid],['quantity','move_line_ids'])
        if any(abs(x['quantity'])>1e-8 or x['move_line_ids'] for x in after):raise RuntimeError('Per-picking unreserve postcondition not verified')
        values_batch=[]
        for i in source_ids:
            x=self.sl[i];unit=self.maps['uom.uom'][rid(x['product_uom_id'])];qty=rounded(x['qty_done'],self.tu[unit]['rounding'])
            if abs(qty-x['qty_done'])>1e-8:self.j['rounding_differences'].append({'source_line':i,'source_move':rid(x['move_id']),'source_qty':x['qty_done'],'target_qty':qty,'target_unit':unit,'delta':qty-x['qty_done']});self.persist()
            values={'company_id':1,'move_id':pairs[rid(x['move_id'])],'product_id':self.maps['product.product'][rid(x['product_id'])],
                    'product_uom_id':unit,'location_id':self.maps['stock.location'][rid(x['location_id'])],'location_dest_id':self.maps['stock.location'][rid(x['location_dest_id'])],
                    'lot_id':self.maps.get('stock.lot',{}).get(rid(x['lot_id']),False),'quantity':qty,'picked':True,'date':x['date']}
            values_batch.append(values)
        if values_batch:
            lids=self.mutate('stock.move.line','create',[values_batch])
            if len(lids)!=len(source_ids) or len(set(lids))!=len(lids):raise RuntimeError('Incomplete batch detailed operations')
            actual={x['id']:x for x in self.b.read('stock.move.line',lids,list(values_batch[0]))}
            for lid,want in zip(lids,values_batch):
                for field,value in want.items():
                    have=rid(actual[lid][field]) if field.endswith('_id') else actual[lid][field]
                    if have!=value:raise RuntimeError('Prepared batch line read-back mismatch: '+field)
            self.attach_many('stock.move.line',list(zip(source_ids,lids)))

    def finish(self,g,only_picking=None):
        sid=g['source']['id'];tid=g['target']['id'];state=self.j['groups'][str(sid)]
        pairs={int(s):t for s,t in state['move_pairs'].items()}
        target_picking={int(s):t for s,t in state['picking_pairs'].items()}
        invoice_before=state['invoice_count_before']
        done_picks=set(state.get('completed_pickings',[]))
        completed={i for i in g['moves'] if rid(self.sm[i]['picking_id']) in done_picks}
        for spid in sorted(g['pickings'],key=lambda i:(self.sp[i]['date_done'],i)):
            if spid in done_picks or (only_picking and spid!=only_picking):continue
            tp=target_picking[spid]
            native_batch_done=tp in getattr(self,'native_batch_validated',set())
            if native_batch_done:
                after=self.b.read('stock.picking',[tp],['state','company_id'])[0]
                if after['state']!='done' or rid(after['company_id'])!=1:raise RuntimeError('Native batch completion changed before historical verification')
            else:
                self.finish_validate_one(g,spid,pairs,completed)
            self.mutate('stock.picking','write',[[tp],{'date_done':self.sp[spid]['date_done'],'scheduled_date':self.sp[spid]['scheduled_date']}])
            source_moves=[i for i in g['moves'] if rid(self.sm[i]['picking_id'])==spid]
            move_dates=defaultdict(list);line_dates=defaultdict(list)
            for smid in source_moves:
                move_dates[self.sm[smid]['date']].append(pairs[smid])
                for lid in self.sm[smid]['move_line_ids']:line_dates[self.sl[lid]['date']].append(self.maps['stock.move.line'][lid])
            for date,ids in move_dates.items():self.mutate('stock.move','write',[ids,{'date':date}])
            for date,ids in line_dates.items():self.mutate('stock.move.line','write',[ids,{'date':date}])
            completed.update(source_moves)
            state.setdefault('completed_pickings',[]).append(spid);self.persist()
        self.verify_finished_chain(g,pairs,target_picking,invoice_before,state)

    def finish_validate_one(self,g,spid,pairs,completed):
            self.prepare_picking_lines(g,spid)
            state=self.j['groups'][str(g['source']['id'])]
            target_picking={int(s):t for s,t in state['picking_pairs'].items()}
            tp=target_picking[spid];source_moves=[i for i in g['moves'] if rid(self.sm[i]['picking_id'])==spid]
            for smid in source_moves:
                for pred in self.sm[smid]['move_orig_ids']:
                    if pred in pairs and rid(self.sm[pred]['picking_id'])!=spid and pred not in completed:raise RuntimeError('Predecessor not completed')
            needed=defaultdict(float)
            for smid in source_moves:
                for x in self.by_move[smid]:
                    product=self.maps['product.product'][rid(x['product_id'])]
                    if not self.tp[product].get('is_storable') or self.locations[rid(x['location_id'])]['usage']!='internal':continue
                    unit=self.maps['uom.uom'][rid(x['product_uom_id'])]
                    qty=rounded(x['qty_done'],self.tu[unit]['rounding'])*self.tu[unit]['factor']/self.tu[rid(self.tp[product]['uom_id'])]['factor']
                    needed[(product,self.maps['stock.location'][rid(x['location_id'])],self.maps.get('stock.lot',{}).get(rid(x['lot_id']),False))]+=qty
            if needed:
                if getattr(self,'is_delivery',False) and hasattr(self,'release_scoped_reservations'):self.release_scoped_reservations(needed,set(pairs.values()))
                quants=self.b.scan('stock.quant',[['company_id','=',1],['product_id','in',sorted({k[0] for k in needed})],['location_id','in',sorted({k[1] for k in needed})],['lot_id','in',sorted({k[2] for k in needed})],['package_id','=',False],['owner_id','=',False]],['product_id','location_id','lot_id','quantity','reserved_quantity'])
                assert_exact_stock(needed,quants)
            ctx={'skip_backorder':True,'picking_ids_not_to_backorder':[tp],'skip_redirection':True}
            result=self.mutate('stock.picking','button_validate',[[tp]],context=ctx)
            after=self.b.read('stock.picking',[tp],['state','company_id'])[0]
            if after['state']!='done':raise RuntimeError('Validation needs separate wizard review: '+str(result))

    def verify_finished_chain(self,g,pairs,target_picking,invoice_before,state):
        tid=g['target']['id']
        if set(state.get('completed_pickings',[]))!=set(g['pickings']):return
        target_moves=self.b.read('stock.move',list(pairs.values()),['state','quantity','date','product_id','product_uom','location_id','location_dest_id','move_line_ids'])
        target_lines=self.b.read('stock.move.line',[i for m in target_moves for i in m['move_line_ids']],['move_id','product_id','product_uom_id','quantity','lot_id','location_id','location_dest_id','owner_id','package_id','result_package_id','date'])
        target_by_move=defaultdict(list)
        for x in target_lines:target_by_move[rid(x['move_id'])].append(x)
        for t in target_moves:
            smid=next(s for s,tt in pairs.items() if tt==t['id']);s=self.sm[smid]
            if t['state']!='done' or t['date']!=s['date'] or abs(t['quantity']-sum(rounded(self.sl[i]['qty_done'],self.tu[self.maps['uom.uom'][rid(self.sl[i]['product_uom_id'])]]['rounding']) for i in s['move_line_ids']))>1e-6:raise RuntimeError('Completed move quantity/date read-back failed')
            expected=Counter((self.maps['product.product'][rid(x['product_id'])],self.maps['uom.uom'][rid(x['product_uom_id'])],self.maps.get('stock.lot',{}).get(rid(x['lot_id']),False),self.maps['stock.location'][rid(x['location_id'])],self.maps['stock.location'][rid(x['location_dest_id'])],rounded(x['qty_done'],self.tu[self.maps['uom.uom'][rid(x['product_uom_id'])]]['rounding']),x['date']) for x in self.by_move[smid])
            actual=Counter((rid(x['product_id']),rid(x['product_uom_id']),rid(x['lot_id']),rid(x['location_id']),rid(x['location_dest_id']),x['quantity'],x['date']) for x in target_by_move[t['id']])
            if expected!=actual:raise RuntimeError('Completed detailed operations differ')
        self.verify_order_fulfillment(g)
        invoice_after=self.b.call('account.move','search_count',[[['company_id','=',1],['move_type','in',['out_invoice','in_invoice','out_refund','in_refund']]]])
        if invoice_after!=invoice_before:raise RuntimeError('Unexpected Invoice/Bill creation during warehouse step')
        if {x['id'] for x in self.target_chain(tid)}!=set(pairs.values()):raise RuntimeError('Unexpected additional moves created by push rules')
        state['phase']='completed';state['completed_utc']=datetime.now(timezone.utc).isoformat();state['verified_moves']=target_moves;self.persist()
        print(json.dumps({('completed_so' if getattr(self,'is_delivery',False) else 'completed_po'):g['source']['name'],'pickings':len(target_picking),'moves':len(pairs)}),flush=True)

    def verify_order_fulfillment(self,g):
        after_lines=self.b.read('purchase.order.line',[x['id'] for x in g['target_lines']],['qty_received','product_qty'])
        source_by_target={self.maps['purchase.order.line'][x['id']]:x for x in g['source_lines']}
        for t in after_lines:
            if abs(t['qty_received']-source_by_target[t['id']]['qty_received'])>1e-6:raise RuntimeError('PO received quantity mismatch')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['preflight','sample','batch'],default='preflight');parser.add_argument('--source-po',type=int);parser.add_argument('--limit',type=int,default=20);parser.add_argument('--finish-prepared',action='store_true');parser.add_argument('--retry-equivalent-units',action='store_true')
    args=parser.parse_args();r=Run();groups=r.plan()
    if args.mode=='preflight':return
    write_lock=runpy.run_path(str(BASE/'production_write_lock.py'))['acquire'](OUT)
    if r.uncertain:raise RuntimeError('Uncertain previous RPC requires recovery')
    if args.retry_equivalent_units:
        for g in groups:
            state=r.j['groups'].get(str(g['source']['id']),{})
            if g['issues'] or not state.get('execution_hold') or state.get('phase')!='order_confirmed' or (args.source_po and g['source']['id']!=args.source_po):continue
            error=state.get('error','')
            if not error.startswith('Ambiguous generated source move match:'):continue
            s=r.sm[int(error.rsplit(':',1)[1])]
            candidates=[t for t in r.target_chain(g['target']['id']) if t['state'] not in ['done','cancel'] and
                rid(t['product_id'])==r.maps['product.product'][rid(s['product_id'])] and
                all(rid(t[f])==r.maps['stock.location'][rid(s[f])] for f in ['location_id','location_dest_id']) and
                s['purchase_line_id'] and rid(t['purchase_line_id'])==r.maps['purchase.order.line'][rid(s['purchase_line_id'])] and
                equivalent_demand(rid(t['product_uom']),t['product_uom_qty'],r.maps['uom.uom'][rid(s['product_uom'])],s['product_uom_qty'],r.tu)]
            if len(candidates)!=1:continue
            checks=r.b.read('stock.move.line',candidates[0]['move_line_ids'],['picked','state'])
            if any(x['picked'] or x['state']=='done' for x in checks):continue
            state.setdefault('hold_history',[]).append({'error':error,'released_utc':datetime.now(timezone.utc).isoformat(),'reason':'Live unique same-product/location/PO-line candidate, equal base quantity, unpicked; normalize generated move unit only'})
            state['execution_hold']=False;r.persist()
    eligible=[g for g in groups if not g['issues'] and not r.j['groups'].get(str(g['source']['id']),{}).get('execution_hold') and r.j['groups'].get(str(g['source']['id']),{}).get('phase')!='completed' and (not args.source_po or g['source']['id']==args.source_po)]
    if args.finish_prepared:eligible=[g for g in eligible if r.j['groups'].get(str(g['source']['id']),{}).get('phase') in ['chain_prepared','details_prepared']]
    if args.mode=='batch' and not any(x.get('phase')=='completed' for x in r.j['groups'].values()):raise RuntimeError('Successful sample required')
    selected=eligible[:1 if args.mode=='sample' else args.limit]
    for group in selected:
        try:
            if args.mode=='sample':r.process(group)
            elif r.j['groups'].get(str(group['source']['id']),{}).get('phase') not in ['chain_prepared','details_prepared']:
                r.process(group,prepare_only=True)
        except Exception as e:
            state=r.j['groups'].setdefault(str(group['source']['id']),{});state['error']=str(e);state['stopped_utc']=datetime.now(timezone.utc).isoformat()
            if not r.uncertain and (str(e).startswith('Ambiguous generated source move match:') or str(e) in ['Unexpected additional native moves','Target picking shared by source pickings']):
                state['execution_hold']=True;r.persist();print(json.dumps({'held_po':group['source']['name'],'reason':str(e)}),flush=True);continue
            r.persist();raise
    if args.mode=='batch':
        events=sorted((r.sp[spid]['date_done'],spid,g) for g in selected if not r.j['groups'].get(str(g['source']['id']),{}).get('execution_hold') for spid in g['pickings'])
        for date,spid,group in events:
            try:r.finish(group,only_picking=spid)
            except Exception as e:
                state=r.j['groups'][str(group['source']['id'])];state['error']=str(e);state['stopped_utc']=datetime.now(timezone.utc).isoformat();r.persist();raise
    print(json.dumps({'completed_in_call':len(selected),'completed_total':sum(x.get('phase')=='completed' for x in r.j['groups'].values())}),flush=True)

if __name__=='__main__':main()
