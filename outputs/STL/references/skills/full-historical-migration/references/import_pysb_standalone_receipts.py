"""Replay two approved missing July supply chains without importing old POs."""
import json, runpy
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[6]
H = runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/complete_pysb_stock_migration.py'))

def main():
    m = H['Completion'](); require = H['require']; rid = H['rid']
    move_ids = [478844, 478845, 458792, 458798]
    fields = ['name','date','state','company_id','product_id','product_uom','product_uom_qty','location_id','location_dest_id','picking_id','move_line_ids']
    moves = {x['id']: x for x in m.a.read('stock.move',move_ids,fields)}
    lines = m.a.read('stock.move.line',[i for x in moves.values() for i in x['move_line_ids']],['move_id','product_id','product_uom_id','qty_done','lot_id','location_id','location_dest_id','package_id','result_package_id','owner_id','date'])
    pickings = {x['id']:x for x in m.a.read('stock.picking',[rid(x['picking_id']) for x in moves.values()],['name','date_done','origin','partner_id','company_id','state'])}
    types = m.b.search_read('stock.picking.type',[['company_id','=',1]],['name','code','default_location_src_id','default_location_dest_id'])
    records = m.j.setdefault('standalone_source_receipts',[])
    plan = []
    for sid in move_ids:
        s=moves[sid]; p=pickings[rid(s['picking_id'])]; ls=[x for x in lines if rid(x['move_id'])==sid and x['qty_done']>0]
        require(s['state']=='done' and rid(s['company_id'])==1 and p['state']=='done','Source not done/company 1')
        require(sid not in m.maps['stock.move'],'Source already mapped; do not duplicate')
        require(len(ls)==1 and not any(ls[0][k] for k in ['owner_id','package_id','result_package_id']),'Unexpected detail scope')
        x=ls[0]; product=m.maps['product.product'][rid(x['product_id'])]; lot=m.maps['stock.lot'][rid(x['lot_id'])]
        src=m.maps['stock.location'][rid(x['location_id'])]; dst=m.maps['stock.location'][rid(x['location_dest_id'])]
        code='incoming' if m.locations[src]['usage']=='supplier' else 'internal'
        matches=[t for t in types if t['code']==code and rid(t['default_location_src_id'])==src and rid(t['default_location_dest_id'])==dst]
        if not matches: matches=[t for t in types if t['code']==code and rid(t['default_location_dest_id'])==5]
        require(len(matches)==1,'Ambiguous picking type')
        prod=m.b.read('product.product',[product],['tracking','uom_id'])[0]
        require(prod['tracking']!='serial' or x['qty_done']==1,'Serial quantity violation')
        lotrow=m.b.read('stock.lot',[lot],['product_id','company_id'])[0]
        require(rid(lotrow['product_id'])==product and rid(lotrow['company_id'])==1,'Wrong lot mapping')
        token='source_supply_move_'+str(sid)
        existing=m.b.search_read('ir.model.data',[['module','=','pysb_standalone_supply'],['name','=',token]],['res_id','model'])
        require(not existing or any(r.get('source_move')==sid and r.get('target_picking')==existing[0]['res_id'] for r in records),'Existing external ID needs recovery review')
        plan.append({'source_move':sid,'source':s,'source_picking':p,'line':x,'product':product,'lot':lot,'src':src,'dst':dst,'type':matches[0]['id'],'code':code,'token':token})
    H['H']['H']['save'](m.path.parent/'standalone-source-receipts-plan.json',plan)
    for row in plan:
        sid=row['source_move']; old=next((r for r in records if r['source_move']==sid),None)
        if old:
            require(old['status']=='verified','Interrupted receipt needs review before retry');continue
        s=row['source'];p=row['source_picking'];x=row['line']
        ref=f"PYSB-SOURCE-SUPPLY | v14 {p['name']} | {p['origin']} | move {sid}"
        note={'purpose':'REAL V14 JULY RECEIPT / STORAGE MOVEMENT FROM OLD PO; STANDALONE WITHOUT PO IMPORT','source_database':m.a.db,'target_database':m.b.db,'company_id':1,'source_move':sid,'source_picking':p,'source_line':x,'reference':ref}
        rec={'source_move':sid,'source_picking':p['id'],'reference':ref,'status':'intent','date':s['date'],'source_qty':x['qty_done'],'note':note};records.append(rec);m.persist()
        target=m.mutate('stock.picking','create',[{'company_id':1,'picking_type_id':row['type'],'location_id':row['src'],'location_dest_id':row['dst'],'origin':ref,'scheduled_date':s['date'],'note':json.dumps(note,ensure_ascii=False),'move_type':'direct'}]);rec['target_picking']=target;m.persist()
        m.mutate('ir.model.data','create',[{'module':'pysb_standalone_supply','name':row['token'],'model':'stock.picking','res_id':target,'noupdate':True}])
        vals={'company_id':1,'picking_id':target,'product_id':row['product'],'product_uom':m.maps['uom.uom'][rid(s['product_uom'])],'product_uom_qty':x['qty_done'],'location_id':row['src'],'location_dest_id':row['dst'],'location_final_id':row['dst'],'date':s['date'],'state':'confirmed','procure_method':'make_to_stock','propagate_cancel':False,'rule_id':False,'purchase_line_id':False,'sale_line_id':False,'origin':ref,'description_picking_manual':json.dumps(note,ensure_ascii=False)}
        mid=m.mutate('stock.move','create',[vals]);rec['target_move']=mid;m.persist()
        lid=m.mutate('stock.move.line','create',[{'company_id':1,'picking_id':target,'move_id':mid,'product_id':row['product'],'product_uom_id':m.maps['uom.uom'][rid(x['product_uom_id'])],'quantity':x['qty_done'],'picked':True,'location_id':row['src'],'location_dest_id':row['dst'],'lot_id':row['lot'],'date':s['date']}]);rec['target_line']=lid;m.persist()
        result=m.mutate('stock.picking','button_validate',[[target]],{'context':{'skip_backorder':True,'skip_redirection':True,'picking_ids_not_to_backorder':[target]}})
        require(not isinstance(result,dict) or not result.get('res_model'),'Unexpected validation wizard; read back before retry')
        done=m.b.read('stock.picking',[target],['state','move_ids'])[0]
        require(done['state']=='done' and done['move_ids']==[mid],'Unexpected generated move or picking state')
        m.matrix('stock.picking',['id','date_done'],[[f'pysb_standalone_supply.{row["token"]}',p['date_done']]])
        m.mutate('stock.move','write',[[mid],{'date':s['date']}],{'context':{'tz':'UTC'}})
        m.mutate('stock.move.line','write',[[lid],{'date':s['date']}],{'context':{'tz':'UTC'}})
        actual=m.b.read('stock.move.line',[lid],['quantity','lot_id','location_id','location_dest_id','date','state'])[0]
        require(actual['state']=='done' and actual['quantity']==x['qty_done'] and rid(actual['lot_id'])==row['lot'] and rid(actual['location_id'])==row['src'] and rid(actual['location_dest_id'])==row['dst'] and actual['date']==s['date'],'Receipt detail mismatch')
        m.uoms=H['index'](m.b.search_read('uom.uom',[],['name','factor','rounding']))
        q=m.qty(x);rec.update(status='verified',after_line=actual,target_qty=x['qty_done'],deltas=[[[row['product'],row['src'],row['lot'],False,False],-q],[[row['product'],row['dst'],row['lot'],False,False],q]])
        m.persist();print(json.dumps({'source_move':sid,'target_picking':target,'status':'verified','qty':x['qty_done']}),flush=True)
    H['H']['H']['save'](m.path.parent/'standalone-source-receipts-report.json',records)

if __name__=='__main__':main()
