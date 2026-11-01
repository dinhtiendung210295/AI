"""Native simple SO delivery chains using shared receipt detail/validation gates.

No return/backorder split repair, master changes, temporary stock or invoices.
The conservative historical plan and a successful sample precede batch work.
"""
import argparse
import json
import runpy
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
R=runpy.run_path(str(Path(__file__).with_name('migrate_pysb_independent_receipts.py')))
load=R['load'];save=R['save'];OUT=R['OUT'];rid=R['rid'];Base=R['Run']

class Run(Base):
    is_delivery=True
    reservation_evidence_dir=OUT
    def release_scoped_reservations(self,needed,own_move_ids):
        runpy.run_path(str(Path(__file__).with_name('scoped_delivery_reservations.py')))['release'](self,needed,own_move_ids)
    def __init__(self):
        super().__init__()
        for name in ['independent-mo-journal.json','independent-inventory-journal.json','opening-lot-resolution.json']:
            if not (OUT/name).exists():continue
            for model,pairs in load(name)['maps'].items():self.maps.setdefault(model,{}).update({int(k):v for k,v in pairs.items()})
        self.j=load('independent-delivery-journal.json') if (OUT/'independent-delivery-journal.json').exists() else {'database':self.b.r.db,'company_id':1,'operations':[],'groups':{},'maps':{},'rounding_differences':[]}
        for model,pairs in self.j['maps'].items():self.maps.setdefault(model,{}).update({int(k):v for k,v in pairs.items()})
        self.uncertain=[x for x in self.j['operations'] if x['status'] in ['intent','uncertain']]
        self.planrows=load('independent-delivery-plan.json')['rows']
        self.so={x['id']:x for x in load('source-delivery-orders.json')};self.to={x['id']:x for x in load('target-delivery-orders.json')}
        self.sol=defaultdict(list);self.tol={x['id']:x for x in load('target-delivery-order-lines.json')}
        for x in load('source-delivery-order-lines.json'):self.sol[rid(x['order_id'])].append(x)
        communication=runpy.run_path(str(Path(__file__).with_name('inspect_pysb_stock_automations.py')))['inspect'](self.b)
        save('stock-automation-preflight.json',communication)
        if not communication['delivery_communications_disabled'] or communication['automations_need_review']:raise RuntimeError('Delivery communication/automation configuration requires review')
    def persist(self):
        self.j['maps']={m:v for m,v in self.maps.items() if m in ['stock.lot','stock.picking','stock.move','stock.move.line']}
        save('independent-delivery-journal.json',self.j)
    def target_chain(self,order_id):
        order=self.b.read('sale.order',[order_id],['picking_ids'])[0]
        picks=self.b.read('stock.picking',order['picking_ids'],['state','company_id','move_ids'])
        mids={i for p in picks for i in p['move_ids']}
        return self.b.read('stock.move',mids,'state company_id product_id product_uom product_uom_qty quantity location_id location_dest_id picking_id move_orig_ids move_dest_ids move_line_ids sale_line_id reference_ids'.split())
    def group(self,row):
        s=self.so[row['source_so']];t=self.to[row['target_so']]
        return {'source':s,'target':t,'source_lines':self.sol[s['id']],'target_lines':[self.tol[i] for i in t['order_line']],'moves':row['moves'],'pickings':row['pickings'],'requires_mts_route_sample':row.get('requires_mts_route_sample',False),'issues':row['errors']}
    def flow(self,row):
        tracking=sorted({self.tp[self.maps['product.product'][rid(self.sm[i]['product_id'])]]['tracking'] for i in row['moves']})
        flow=(rid(self.so[row['source_so']]['warehouse_id']),len(row['pickings']),tuple(tracking),row.get('requires_mts_route_sample',False))
        different=runpy.run_path(str(Path(__file__).with_name('delivery_stage_demand.py')))['differs']([self.sm[mid] for mid in row['moves']],self.locations,self.maps,self.tu)
        return flow+('physical_stage_demand_differs',) if different else flow
    def verify_order_fulfillment(self,g):
        target=self.b.read('sale.order.line',[x['id'] for x in g['target_lines']],['qty_delivered','product_uom_qty','price_unit','discount','price_subtotal','price_total','product_id','product_uom_id'])
        source={self.maps['sale.order.line'][x['id']]:x for x in g['source_lines']}
        for t in target:
            s=source[t['id']]
            for f in ['qty_delivered','product_uom_qty','price_unit','discount','price_subtotal','price_total']:
                expected=s[f]
                if f=='qty_delivered' and s['product_id'] and self.tp[self.maps['product.product'][rid(s['product_id'])]]['type']!='service':
                    unit=self.maps['uom.uom'][rid(s['product_uom'])];expected=R['rounded'](expected,self.tu[unit]['rounding'])
                    if abs(expected-s[f])>1e-8:
                        record={'source_line':s['id'],'target_line':t['id'],'field':f,'source':s[f],'target_expected':expected,'delta':expected-s[f],'target_unit':unit}
                        if record not in self.j.setdefault('order_rounding_differences',[]):self.j['order_rounding_differences'].append(record);self.persist()
                if abs(t[f]-expected)>1e-6:raise RuntimeError('SO fulfillment/commercial mismatch: '+f)
            if s['product_id'] and (rid(t['product_id'])!=self.maps['product.product'][rid(s['product_id'])] or rid(t['product_uom_id'])!=self.maps['uom.uom'][rid(s['product_uom'])]):raise RuntimeError('SO line identity mismatch after completion')
    def prepare(self,g):
        sid=g['source']['id'];tid=g['target']['id'];state=self.j['groups'].get(str(sid))
        if state:
            if state.get('phase') in ['completed','chain_prepared']:return
            if state.get('phase') in ['order_confirmed','native_chain_matched'] and getattr(self,'resume_unvalidated',False) and not self.uncertain:
                reservations=[];physical_before={}
                if self.a.read('sale.order',[sid],list(g['source']))[0]!=g['source']:raise RuntimeError('Source SO changed before unvalidated resume')
                if state.get('phase')=='native_chain_matched':
                    ids=set(state['move_pairs'].values());pids=set(state['picking_pairs'].values())
                    actual=self.b.read('stock.move',list(ids),['state','company_id','quantity','picked','move_line_ids','move_orig_ids','move_dest_ids','picking_id','product_id','location_id','location_dest_id'])
                    if {x['id'] for x in self.target_chain(tid)}!=ids or any(x['state'] in ['done','cancel'] or rid(x['company_id'])!=1 or x['picked'] or rid(x['picking_id']) not in pids or (set(x['move_orig_ids'])|set(x['move_dest_ids']))-ids for x in actual):raise RuntimeError('Prepared delivery no longer unconsumed/isolated')
                    reservation_helper=runpy.run_path(str(Path(__file__).with_name('unconsumed_native_reservations.py')))
                    reservations=self.b.read('stock.move.line',[lid for x in actual for lid in x['move_line_ids']],['state','picked','move_id','company_id','product_id','lot_id','quantity','location_id','location_dest_id','owner_id','package_id','result_package_id'])
                    reservation_helper['validate'](actual,reservations,self.maps.get('stock.move.line',{}).values())
                    physical_before=reservation_helper['capture'](self,reservations)
                    if any(x['model']=='stock.picking' and x['method']=='button_validate' and set(x['args'][0])&pids for x in self.j['operations']):raise RuntimeError('Prior delivery validation attempt needs separate recovery')
                    fresh=self.a.read('stock.move',g['moves'],['state','write_date'])
                    if any(x['state']!='done' or x['write_date']!=self.sm[x['id']]['write_date'] for x in fresh):raise RuntimeError('Source moves changed before unvalidated recovery')
                    state['unconsumed_resume_readback']=actual;self.persist()
                self.prepare_native_chain(g,state)
                if reservations:
                    physical_after=reservation_helper['capture'](self,reservations)
                    reservation_helper['unchanged'](physical_before,physical_after)
                    state.setdefault('resumed_reservation_release',[]).append(dict(lines=reservations,physical_before=physical_before,physical_after=physical_after,method='native do_unreserve on own unvalidated chain'))
                    self.persist()
                return
            raise RuntimeError('Interrupted delivery preparation requires read-back')
        if g['issues']:raise RuntimeError('Held SO')
        if self.uncertain:raise RuntimeError('Uncertain earlier RPC requires recovery')
        if self.a.read('sale.order',[sid],list(g['source']))[0]!=g['source']:raise RuntimeError('Source SO changed since preflight')
        fresh_moves=self.a.read('stock.move',g['moves'],['state','write_date'])
        if any(x['state']!='done' or x['write_date']!=self.sm[x['id']]['write_date'] for x in fresh_moves):raise RuntimeError('Source delivery moves changed since snapshot')
        source_lines={x['id']:x for x in g['source_lines']}
        fresh_lines=self.a.read('sale.order.line',list(source_lines),list(g['source_lines'][0]))
        if any(x!=source_lines[x['id']] for x in fresh_lines):raise RuntimeError('Source commercial lines changed since preflight')
        before=self.b.read('sale.order',[tid],list(dict.fromkeys([*g['target'],'carrier_id'])))[0]
        if any(before[f]!=v for f,v in g['target'].items()) or before['state'] not in ['draft','sent','sale','done'] or rid(before['company_id'])!=1 or rid(g['source']['company_id'])!=1:raise RuntimeError('Target SO changed or company mismatch')
        expected_target={x['id']:x for x in g['target_lines']}
        fresh_target=self.b.read('sale.order.line',list(expected_target),list(dict.fromkeys([*g['target_lines'][0],'route_ids','is_expense'])))
        if any(any(x[f]!=v for f,v in expected_target[x['id']].items()) for x in fresh_target):raise RuntimeError('Target commercial lines changed since preflight')
        route_overrides=fresh_target
        if any(x.get('route_ids') or x.get('is_expense') for x in route_overrides):
            self.j['groups'][str(sid)]={'source_name':g['source']['name'],'target_order':tid,'phase':'preflight_held','execution_hold':True,'hold_reason':'Explicit native line route or expense requires procurement review'};self.persist();return
        route_proof=None
        if g.get('requires_mts_route_sample'):
            route_proof=runpy.run_path(str(Path(__file__).with_name('hq_mts_delivery_proof.py')))['live_order_gate'](self.b,before,g['target_lines'])
            if not route_proof['ready']:
                self.j['groups'][str(sid)]={'source_name':g['source']['name'],'target_order':tid,'phase':'preflight_held','execution_hold':True,'hold_reason':'HQ MTS route proof failed','route_proof':route_proof};self.persist();return
        if before.get('carrier_id'):raise RuntimeError('Carrier integration needs separate review before delivery')
        state={'source_name':g['source']['name'],'target_order':tid,'phase':'preflight_passed','route_proof':route_proof};self.j['groups'][str(sid)]=state;self.persist()
        countdomain=[['company_id','=',1],['move_type','in',['out_invoice','in_invoice','out_refund','in_refund']]]
        state['invoice_count_before']=self.b.call('account.move','search_count',[countdomain]);self.persist()
        if before['state'] in ['sale','done']:
            confirmed=load('phases/so-confirmation-journal.json')['orders'].get(str(sid),{})
            if confirmed.get('status')!='verified_confirmed' or confirmed.get('target_id')!=tid:raise RuntimeError('Confirmed SO lacks scoped confirmation evidence')
            state.update(phase='order_confirmed',confirmation_reused=True,confirmation_evidence=confirmed)
            self.persist();self.prepare_native_chain(g,state);return
        counts={model:self.b.call(model,'search_count',[[['company_id','=',1]]]) for model in ['purchase.order','mrp.production']}
        result=self.mutate('sale.order','action_confirm',[[tid]])
        confirmation=self.b.read('sale.order',[tid],['state','picking_ids','company_id'])[0]
        if confirmation['state'] not in ['sale','done']:
            state.update(phase='confirmation_held',execution_hold=True,hold_reason='Native confirmation did not complete; approval or native review required',confirmation_result=result,confirmation_readback=confirmation);self.persist()
            print(json.dumps({'held_so':g['source']['name'],'reason':state['hold_reason']}),flush=True);return
        self.mutate('sale.order','write',[[tid],{'date_order':g['source']['date_order']}])
        state['phase']='order_confirmed';self.persist()
        for model,count in counts.items():
            if self.b.call(model,'search_count',[[['company_id','=',1]]])!=count:raise RuntimeError('Unexpected procurement created by SO confirmation: '+model)
        if self.b.call('account.move','search_count',[countdomain])!=state['invoice_count_before']:raise RuntimeError('Unexpected invoice created by SO confirmation')
        self.prepare_native_chain(g,state)

    def prepare_native_chain(self,g,state):
        tid=g['target']['id']
        confirmation=self.b.read('sale.order',[tid],['state','company_id'])[0]
        if confirmation['state'] not in ['sale','done'] or rid(confirmation['company_id'])!=1:raise RuntimeError('SO must really be confirmed before preparing delivery')
        native=self.target_chain(tid);pairs={};pickpairs={};used=set()
        if not native:
            state.update(phase='confirmation_held',execution_hold=True,hold_reason='Confirmed SO produced no native stock moves; review before creating stages');self.persist();return
        native_picks=self.b.read('stock.picking',list({rid(x['picking_id']) for x in native}),['carrier_id'])
        if any(x.get('carrier_id') for x in native_picks):raise RuntimeError('Unexpected carrier on generated delivery')
        if any(x['state'] in ['done','cancel'] or rid(x['company_id'])!=1 for x in native):raise RuntimeError('Unexpected native delivery state/company')
        native_checks=self.b.read('stock.move.line',[i for x in native for i in x['move_line_ids']],['picked','state'])
        if any(x['picked'] or x['state']=='done' for x in native_checks):raise RuntimeError('Native delivery already picked/done before reconstruction')
        self.mutate('stock.picking','do_unreserve',[list({rid(x['picking_id']) for x in native})],jsonrpc=True)
        native=self.target_chain(tid)
        if any(abs(x['quantity'])>1e-8 or x['move_line_ids'] for x in native):raise RuntimeError('Native reconstruction unreserve not verified')
        original_native_ids={x['id'] for x in native}
        references=sorted({i for x in native for i in x.get('reference_ids',[])})
        def ancestors(mid):
            seen=set();frontier=[mid]
            while frontier:
                current=frontier.pop()
                if current in seen:continue
                seen.add(current);frontier.extend(i for i in self.sm[current]['move_orig_ids'] if i in g['moves'])
            return [self.sm[i] for i in seen if not self.sm[i]['move_orig_ids']]
        def downstream_line(mid):
            seen=set();frontier=[mid];result=set()
            while frontier:
                current=frontier.pop()
                if current in seen:continue
                seen.add(current);m=self.sm[current]
                if m['sale_line_id']:result.add(self.maps['sale.order.line'][rid(m['sale_line_id'])])
                frontier.extend(i for i in m['move_dest_ids'] if i in g['moves'])
            if len(result)!=1:raise RuntimeError('Internal delivery has ambiguous SO line provenance')
            return next(iter(result))
        pending=set(g['moves']);ordered=[]
        while pending:
            ready=sorted([mid for mid in pending if set(self.sm[mid]['move_orig_ids']).issubset(set(ordered))],key=lambda mid:(self.sm[mid]['date'],mid))
            if not ready:raise RuntimeError('Source delivery predecessor cycle or missing predecessor')
            ordered.extend(ready);pending.difference_update(ready)
        for mid in ordered:
            s=self.sm[mid]
            source_line=downstream_line(mid)
            candidates=[x for x in native if x['id'] not in used and
                all(rid(x[f])==self.maps[model][rid(s[f])] for f,model in [('product_id','product.product'),('product_uom','uom.uom'),('location_id','stock.location'),('location_dest_id','stock.location')]) and
                abs(x['product_uom_qty']-s['product_uom_qty'])<=1e-6 and
                rid(x['sale_line_id']) in [False,source_line]]
            if not candidates:
                expected_unit=self.maps['uom.uom'][rid(s['product_uom'])]
                equivalents=[x for x in native if x['id'] not in used and
                    all(rid(x[f])==self.maps[model][rid(s[f])] for f,model in [('product_id','product.product'),('location_id','stock.location'),('location_dest_id','stock.location')]) and
                    rid(x['sale_line_id']) in [False,source_line] and
                    R['equivalent_demand'](rid(x['product_uom']),x['product_uom_qty'],expected_unit,s['product_uom_qty'],self.tu)]
                if len(equivalents)==1:
                    x=equivalents[0];checks=self.b.read('stock.move.line',x['move_line_ids'],['picked','state'])
                    if any(z['picked'] or z['state']=='done' for z in checks):raise RuntimeError('Equivalent delivery unit already picked/done')
                    state.setdefault('unit_normalizations',[]).append({'source_move':mid,'target_move':x['id'],'old_unit':rid(x['product_uom']),'new_unit':expected_unit,'old_demand':x['product_uom_qty'],'new_demand':s['product_uom_qty'],'proof':'same unit root and base quantity; unpicked/not done'})
                    self.persist();self.mutate('stock.move','write',[[x['id']],{'product_uom':expected_unit,'product_uom_qty':s['product_uom_qty']}]);x.update(self.b.read('stock.move',[x['id']],list(x))[0]);candidates=[x]
            if not candidates:
                same_leg=[x for x in native if x['id'] not in used and all(rid(x[field])==self.maps[model][rid(s[field])] for field,model in [('product_id','product.product'),('product_uom','uom.uom'),('location_id','stock.location'),('location_dest_id','stock.location')]) and rid(x['sale_line_id'])==source_line]
                if len(same_leg)==1:
                    x=same_leg[0]
                    guard=self.b.read('stock.move',[x['id']],['state','company_id','quantity','picked','move_line_ids','bom_line_id','purchase_line_id','production_id','raw_material_production_id','move_orig_ids','move_dest_ids'])[0]
                    if guard['state'] in ['done','cancel'] or rid(guard['company_id'])!=1 or abs(guard['quantity'])>1e-8 or guard['picked'] or guard['move_line_ids'] or any(guard.get(field) for field in ['bom_line_id','purchase_line_id','production_id','raw_material_production_id']) or (set(guard['move_orig_ids'])|set(guard['move_dest_ids']))-original_native_ids:raise RuntimeError('Physical delivery demand differs on a non-isolated native move')
                    if abs(s['quantity_done']-s['product_uom_qty'])>1e-6:raise RuntimeError('Source physical demand requires partial handling')
                    state.setdefault('physical_demand_normalizations',[]).append({'source_move':mid,'target_move':x['id'],'source_planned':s['product_uom_qty'],'source_done':s['quantity_done'],'native_demand_before':x['product_uom_qty'],'native_demand_after':s['product_uom_qty'],'readback_before':guard,'proof':'same product/unit/physical leg/SO line, source done in frozen scope; own new unpicked/unconsumed native move; no commercial quantity change'})
                    self.persist();self.mutate('stock.move','write',[[x['id']],{'product_uom_qty':s['product_uom_qty']}]);x.update(self.b.read('stock.move',[x['id']],list(x))[0]);candidates=[x]
            if not candidates:
                roots=ancestors(mid);root_locations={self.maps['stock.location'][rid(x['location_id'])] for x in roots}
                compressed=[x for x in native if x['id'] not in used and not x['move_orig_ids'] and rid(x['location_id']) in root_locations and
                    rid(x['product_id'])==self.maps['product.product'][rid(s['product_id'])] and
                    rid(x['location_dest_id'])==self.maps['stock.location'][rid(s['location_dest_id'])] and
                    rid(x['sale_line_id']) in [False,source_line] and
                    R['equivalent_demand'](rid(x['product_uom']),x['product_uom_qty'],self.maps['uom.uom'][rid(s['product_uom'])],s['product_uom_qty'],self.tu)]
                if len(compressed)==1:
                    x=compressed[0]
                    state.setdefault('compressed_native_legs',[]).append({'source_move':mid,'target_move':x['id'],'old_source_location':rid(x['location_id']),'new_source_location':self.maps['stock.location'][rid(s['location_id'])],'proof':'same product, SO line, destination and base quantity; source root location matches; unpicked/unreserved/not done'})
                    self.persist();self.mutate('stock.move','write',[[x['id']],{'location_id':self.maps['stock.location'][rid(s['location_id'])],'product_uom':self.maps['uom.uom'][rid(s['product_uom'])],'product_uom_qty':s['product_uom_qty']}]);x.update(self.b.read('stock.move',[x['id']],list(x))[0]);candidates=[x]
            if not candidates and self.locations[rid(s['location_id'])]['usage']=='internal' and self.locations[rid(s['location_dest_id'])]['usage'] in ['internal','customer']:
                if any(i not in pairs for i in s['move_orig_ids']):raise RuntimeError('Missing source predecessor before creating delivery stage')
                spid=rid(s['picking_id']);sp=self.sp[spid]
                if spid not in pickpairs:
                    pickpairs[spid]=self.mutate('stock.picking','create',[{'company_id':1,'picking_type_id':self.maps['stock.picking.type'][rid(sp['picking_type_id'])],'location_id':self.maps['stock.location'][rid(sp['location_id'])],'location_dest_id':self.maps['stock.location'][rid(sp['location_dest_id'])],'scheduled_date':sp['scheduled_date'],'origin':g['source']['name'],'partner_id':rid(g['target']['partner_shipping_id'])}])
                v={'company_id':1,'product_id':self.maps['product.product'][rid(s['product_id'])],'product_uom':self.maps['uom.uom'][rid(s['product_uom'])],'product_uom_qty':s['product_uom_qty'],
                    'location_id':self.maps['stock.location'][rid(s['location_id'])],'location_dest_id':self.maps['stock.location'][rid(s['location_dest_id'])],'location_final_id':self.maps['stock.location'][rid(s['location_dest_id'])],
                    'picking_id':pickpairs[spid],'sale_line_id':source_line,'reference_ids':[(6,0,references)],'state':'confirmed','procure_method':'make_to_stock','propagate_cancel':False,'rule_id':False,'date':s['date']}
                created=self.mutate('stock.move','create',[v]);row=self.b.read('stock.move',[created],list(native[0]))[0];native.append(row);candidates=[row]
            if len(candidates)!=1:
                state['mapping_mismatch']={'source_move':s,'native_moves':native};self.persist();raise RuntimeError('Ambiguous native delivery move: '+str(mid))
            x=candidates[0];pairs[mid]=x['id'];used.add(x['id']);spid=rid(s['picking_id']);tpid=rid(x['picking_id'])
            if spid in pickpairs and pickpairs[spid]!=tpid:raise RuntimeError('Source picking split by target')
            if tpid in pickpairs.values() and pickpairs.get(spid)!=tpid:raise RuntimeError('Target picking merges source pickings')
            pickpairs[spid]=tpid
        if not original_native_ids.issubset(used) or used!={x['id'] for x in native}:raise RuntimeError('Additional native delivery moves')
        state.update(move_pairs=pairs,picking_pairs=pickpairs,phase='native_chain_matched');self.persist()
        self.attach_many('stock.move',list(pairs.items()));self.attach_many('stock.picking',list(pickpairs.items()))
        header_locations={p['id']:p for p in self.b.read('stock.picking',list(pickpairs.values()),['location_id','location_dest_id'])}
        for spid,tpid in pickpairs.items():
            sp=self.sp[spid]
            values={'location_id':self.maps['stock.location'][rid(sp['location_id'])],'location_dest_id':self.maps['stock.location'][rid(sp['location_dest_id'])]}
            if any(rid(header_locations[tpid][f])!=v for f,v in values.items()):self.mutate('stock.picking','write',[[tpid],values])
        native_by_id={x['id']:x for x in native}
        for mid,tmid in pairs.items():
            origins=[pairs[i] for i in self.sm[mid]['move_orig_ids']]
            current=set(native_by_id[tmid]['move_orig_ids'])
            if current-set(pairs.values()):raise RuntimeError('Unexpected external native delivery predecessor')
            if current!=set(origins):self.mutate('stock.move','write',[[tmid],{'move_orig_ids':[(6,0,origins)]}])
        # Release only this new chain; defer detailed reservations until its event.
        self.mutate('stock.picking','do_unreserve',[list(pickpairs.values())],jsonrpc=True)
        after=self.b.read('stock.move',list(pairs.values()),['quantity','move_line_ids'])
        if any(abs(x['quantity'])>1e-8 or x['move_line_ids'] for x in after):raise RuntimeError('Delivery unreserve postcondition failed')
        lots={rid(x['lot_id']) for mid in g['moves'] for x in self.by_move[mid] if x['lot_id']}
        source_lots=self.a.read('stock.production.lot',lots,'name product_id company_id expiration_date use_date removal_date alert_date'.split())
        for lot in source_lots:
            pid=self.maps['product.product'][rid(lot['product_id'])]
            found=self.b.call('stock.lot','search_read',[[['company_id','=',1],['product_id','=',pid],['name','=',lot['name']]]],{'fields':['name'],'limit':2})
            if not found:
                all_lots=self.b.scan('stock.lot',[['company_id','=',1],['product_id','=',pid]],['name','product_id','company_id'])
                chosen=runpy.run_path(str(Path(__file__).with_name('delivery_lot_matching.py')))['select'](lot['name'],pid,1,all_lots,self.maps.get('stock.lot',{}).get(lot['id']))
                state.setdefault('lot_lookup_readback',[]).append({'source_lot':lot,'mapped_target_lot':self.maps.get('stock.lot',{}).get(lot['id']),'full_product_company_scan':all_lots,'selected':chosen});self.persist();found=[chosen]
            if len(found)!=1:raise RuntimeError('Delivery requires unique existing supply lot')
            self.attach('stock.lot',lot['id'],found[0]['id'])
        state['phase']='chain_prepared';self.persist()

def main():
    if (OUT/'queue-handoff-request.json').exists():raise RuntimeError('Controlled handoff requested before next delivery writer; no mutation attempted')
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['sample','batch'],default='sample');p.add_argument('--limit',type=int,default=10);p.add_argument('--resume-unvalidated',action='store_true');p.add_argument('--finish-prepared',action='store_true');p.add_argument('--source-so',type=int);args=p.parse_args();r=Run();r.resume_unvalidated=args.resume_unvalidated
    if r.uncertain:raise RuntimeError('Uncertain prior delivery operation requires read-back')
    write_lock=runpy.run_path(str(Path(__file__).with_name('production_write_lock.py')))['acquire'](OUT)
    if args.mode=='batch' and not any(x.get('phase')=='completed' for x in r.j['groups'].values()):raise RuntimeError('Successful delivery sample required')
    rows=[x for x in r.planrows if x['eligible'] and not r.j['groups'].get(str(x['source_so']),{}).get('execution_hold') and r.j['groups'].get(str(x['source_so']),{}).get('phase')!='completed']
    if args.source_so:rows=[x for x in rows if x['source_so']==args.source_so]
    if args.finish_prepared:rows=[x for x in rows if r.j['groups'].get(str(x['source_so']),{}).get('phase')=='chain_prepared']
    selected=rows[:1 if args.mode=='sample' else args.limit]
    if args.mode=='batch' and selected:
        proven={r.flow(x) for x in r.planrows if r.j['groups'].get(str(x['source_so']),{}).get('phase')=='completed'}
        if r.flow(selected[0]) not in proven:
            selected=selected[:1];print(json.dumps({'new_flow_sample':r.flow(selected[0]),'source_so':selected[0]['name']}),flush=True)
        else:
            first_unknown=next((i for i,x in enumerate(selected) if r.flow(x) not in proven),len(selected));selected=selected[:first_unknown]
    groups=[r.group(x) for x in selected]
    for g in groups:r.prepare(g)
    groups=[g for g in groups if not r.j['groups'].get(str(g['source']['id']),{}).get('execution_hold')]
    events=sorted((r.sp[pid]['date_done'],pid,g) for g in groups for pid in g['pickings'])
    for date,pid,g in events:r.finish(g,only_picking=pid)
    print(json.dumps({'completed_deliveries':sum(x.get('phase')=='completed' for x in r.j['groups'].values())}),flush=True)

if __name__=='__main__':main()
