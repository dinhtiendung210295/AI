"""Live read-only source/target/valuation proof for the three nonnegative offset proposals."""
import json,runpy
from datetime import datetime,timezone
from pathlib import Path
BASE=Path(__file__).parent
I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'));OUT=I['OUT']
def load(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False
def unique_source(maps,model,target):
    values=[int(s) for s,t in maps[model].items() if t==target]
    if len(values)!=1:raise RuntimeError('Source identity is not unique: '+model)
    return values[0]
def main():
    proposals=[x for x in load('temporary-opening-reconciliation-review.json')['rows'] if x['safe_sample_candidate']]
    a=I['ReadOnly']('v14-prod',('http://175.145.85.151','paoyeang_live'));b=I['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    maps=load('after-run-stock-mapping.json')['maps'];scope=load('scope.json');boundary=scope['start_utc']
    su={x['id']:x for x in load('source-uom.uom.json')};tu={x['id']:x for x in load('target-uom.uom.json')}
    company=b.read('res.company',[1],['currency_id'])[0];currency=b.read('res.currency',[rid(company['currency_id'])],['name','rounding'])[0]
    results=[]
    for row in proposals:
        pid,loc,lot,package,owner=row['target_key'];sp=unique_source(maps,'product.product',pid);sloc=unique_source(maps,'stock.location',loc);slot=unique_source(maps,'stock.lot',lot)
        if package or owner:raise RuntimeError('No package/owner scope in these proposals')
        product=b.read('product.product',[pid],['name','uom_id','tracking','is_storable','company_id','standard_price','cost_method','valuation','property_stock_inventory','active'])[0]
        sourceproduct=a.read('product.product',[sp],['name','uom_id','company_id'])[0]
        targetlot=b.read('stock.lot',[lot],['name','company_id','product_id'])[0];sourcelot=a.read('stock.production.lot',[slot],['name','company_id','product_id'])[0]
        locations=b.read('stock.location',[loc,rid(product['property_stock_inventory'])],['usage','company_id','complete_name'])
        if rid(sourcelot['company_id'])!=1 or rid(targetlot['company_id'])!=1 or rid(sourceproduct['company_id']) not in [False,1] or rid(product['company_id']) not in [False,1]:raise RuntimeError('Company identity changed')
        by_location={x['id']:x for x in locations}
        if by_location[loc]['usage']!='internal' or rid(by_location[loc]['company_id'])!=1 or by_location[rid(product['property_stock_inventory'])]['usage']!='inventory':raise RuntimeError('Inventory location configuration changed')
        if product['cost_method'] not in ['average','standard'] or product['standard_price']<0:raise RuntimeError('Valuation requires separate review')
        if maps['uom.uom'].get(str(rid(sourceproduct['uom_id'])))!=rid(product['uom_id']) or sourcelot['name']!=targetlot['name'] or rid(sourcelot['product_id'])!=sp or rid(targetlot['product_id'])!=pid:raise RuntimeError('Unit or lot identity changed')
        def ledger(reader,source_mode):
            p,l,lt=(sp,sloc,slot) if source_mode else (pid,loc,lot)
            dateop='<' if source_mode else '>='
            domain=[['company_id','=',1],['state','=','done'],['product_id','=',p],['lot_id','=',lt],['move_id.date',dateop,boundary],'|',['location_id','=',l],['location_dest_id','=',l]]
            qfield='qty_done' if source_mode else 'quantity';rows=reader.scan('stock.move.line',domain,['move_id','product_id','product_uom_id',qfield,'lot_id','location_id','location_dest_id','package_id','result_package_id','owner_id','date'])
            units=su if source_mode else tu;base=rid(sourceproduct['uom_id'] if source_mode else product['uom_id']);total=0.
            for x in rows:
                u=rid(x['product_uom_id']);q=x[qfield]*(units[base]['factor']/units[u]['factor'] if source_mode else units[u]['factor']/units[base]['factor'])
                if rid(x['owner_id']):continue
                if rid(x['location_id'])==l and not x['package_id']:total-=q
                if rid(x['location_dest_id'])==l and not x['result_package_id']:total+=q
            return total,rows
        source_opening,source_lines=ledger(a,True);post_opening,target_lines=ledger(b,False)
        quants=b.scan('stock.quant',[['company_id','=',1],['product_id','=',pid],['location_id','=',loc],['lot_id','=',lot],['package_id','=',False],['owner_id','=',False]],['quantity','reserved_quantity','product_id','location_id','lot_id','package_id','owner_id'])
        current=sum(x['quantity'] for x in quants);reserved=sum(x['reserved_quantity'] for x in quants);target_opening=current-post_opening;after=current+row['proposed_delta']
        if abs(source_opening-row['opening']['source_quantity'])>1e-6 or abs(target_opening-row['opening']['target_quantity'])>1e-6 or abs(target_opening+row['proposed_delta']-source_opening)>1e-6:raise RuntimeError('Live opening ledger does not prove proposed offset')
        if after<-1e-6 or after+1e-6<reserved or len(quants)!=1 or product['valuation']!='periodic' or not product['active'] or not product['is_storable']:raise RuntimeError('Nonnegative/periodic sample gate no longer passes')
        results.append(dict(proposal=row,source_key=[sp,sloc,slot,False,False],source_product=sourceproduct,target_product=product,source_lot=sourcelot,target_lot=targetlot,locations=locations,live_source_opening=source_opening,live_target_opening=target_opening,current_quants=quants,current_quantity=current,reserved_quantity=reserved,proposed_inventory_count=after,source_lines=source_lines,target_post_opening_lines=target_lines,estimated_stock_value_reduction=abs(row['proposed_delta'])*product['standard_price'],currency=currency['name'],expected_new_account_moves=0,master_changes=0))
    report=dict(read_only=True,write_authorized=False,generated_utc=datetime.now(timezone.utc).isoformat(),proposed_effective_utc='2026-07-31 15:59:59',rows=results,summary=dict(proven_nonnegative_candidates=len(results),all_periodic=True,expected_new_account_moves=0,estimated_stock_value_reduction=sum(x['estimated_stock_value_reduction'] for x in results),currency=currency['name']),note='Review only. Offset native inventory counts with preserved original temporary moves; do not cancel done history, change master cost, or generalize to negative/reserved cases. Historical total valuation is not certified by this quantity preflight.')
    I['save']('phases/temporary-opening-safe-preflight.json',report);print(json.dumps(report['summary']),flush=True)
    print(json.dumps([dict(product=x['target_product']['name'],lot=x['target_lot']['name'],before=x['current_quantity'],after=x['proposed_inventory_count'],delta=x['proposal']['proposed_delta'],estimated_value=x['estimated_stock_value_reduction']) for x in results],ensure_ascii=False),flush=True)
if __name__=='__main__':main()
