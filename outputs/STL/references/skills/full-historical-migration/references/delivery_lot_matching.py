"""Exact API identity check for the full, paginated product/company lot scan."""
def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False
def select(source_name,product,company,rows,mapped=None):
    found=[x for x in rows if x['name']==source_name and rid(x['product_id'])==product and rid(x['company_id'])==company]
    if len(found)!=1:raise RuntimeError('Delivery requires unique exact supply lot')
    if mapped and found[0]['id']!=mapped:raise RuntimeError('Supply lot external identity conflict')
    return found[0]
