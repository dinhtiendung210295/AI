"""Evidence source-negative history without duplicating real later supply."""
from complete_pysb_stock_migration import Completion,rid,require,index,load,OUT
from execute_pysb_stock_migration import save
import json
def main():
 m=Completion();m.uoms=index(m.b.search_read('uom.uom',[],['factor','rounding']));proof=load('remaining-after-supporting-proof.json');rows=[x for x in proof['rows'] if x['source_would_be_negative']];current=m.ledger(m.b.search_read('stock.quant',[['company_id','=',1]],['product_id','location_id','lot_id','package_id','owner_id','quantity']));physical=[]
 for r in rows:
  mid=r['source_move'];require(r['source_quantity_before_move']<r['source_required_base_qty']-1e-6,'Source was not negative')
  require(r['event']['source'] in m.maps['stock.picking'],'Wrong source picking')
  key=tuple(r['target_key']);required=sum(m.qty(x) for x in m.expected(r['event']) if rid(x['move_id'])==mid and m.quantkey(x)==key)
  m.j.setdefault('historical_source_negative_allowances',{})[str(mid)]={'source_evidence':r,'reason':'Bruce authorized replay of evidenced source-negative stock. Historical negative allowed only for this move; native physical quantity gate remains mandatory. Real later supply must not be duplicated.','current_physical':current[key],'required':required,'approved_by':'Bruce'}
  if current[key]+1e-6<required:physical.append(r)
  target=m.maps['stock.move'][mid];old=m.b.read('stock.move',[target],['description_picking_manual'])[0]['description_picking_manual'] or ''
  marker='PYSB-HISTORICAL-SOURCE-NEGATIVE '+str(mid)
  if marker not in old:m.mutate('stock.move','write',[[target],{'description_picking_manual':old+'\n'+marker+'\n'+json.dumps(m.j['historical_source_negative_allowances'][str(mid)],ensure_ascii=False)}])
  m.persist()
 save(OUT/'remaining-negative-requiring-physical-credit.json',{**proof,'rows':physical});print(json.dumps({'evidenced_negative_moves':len(rows),'physical_credit_moves':len(physical),'real_supply_not_duplicated':True}))
if __name__=='__main__':main()
