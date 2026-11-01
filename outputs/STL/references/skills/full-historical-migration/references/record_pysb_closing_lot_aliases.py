"""Record only uniquely evidenced whitespace aliases; preserve cleaned lot names."""
from complete_pysb_stock_migration import Completion,rid,require
import json
def main():
 m=Completion()
 for sourcepid,targetpid,source_name in [(47228,119645,'4059K89790 '),(47230,119647,'4061M90204 ')]:
  source=m.a.search_read('stock.production.lot',[['company_id','=',1],['product_id','=',sourcepid],['name','=',source_name]],['name']);target=m.b.search_read('stock.lot',[['company_id','=',1],['product_id','=',targetpid],['name','=',source_name.strip()]],['name']);require(len(source)==len(target)==1,'Alias not unique')
  aliases=m.j.setdefault('approved_opening_lot_aliases',[])
  if not any(x['source_lot']==source[0]['id'] for x in aliases):aliases.append({'source_lot':source[0]['id'],'target_lot':target[0]['id'],'source_name':source_name,'target_name':target[0]['name'],'reason':'Approved July closing reconciliation: unique whitespace-only alias, report mapping only; cleaned master names preserved'})
 m.persist();print(json.dumps({'whitespace_aliases':2,'masters_changed':False}))
if __name__=='__main__':main()
