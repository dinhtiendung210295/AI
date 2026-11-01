"""Operator-approved historical usage; rejects generic/ambiguous account choices."""
def rid(x):return x[0] if isinstance(x,(list,tuple)) and x else x or False
def select(history,source_account,source_product,move_type):
    source=next((x for x in history['source_accounts'] if x['id']==source_account),None)
    if not source:return None
    targets={x['id']:x for x in history['target_accounts']}
    rows=next((x['evidence'] for x in history['account_inferences'] if x['source_id']==source_account),[])
    def valid(row):
        t=targets.get(rid(row['target_account']))
        return bool(t and t.get('active') and 1 in t.get('company_ids',[]) and t.get('code')!='v14' and
                    (t['internal_group']==source['internal_group'] or
                     source_account==4 and move_type in ['in_invoice','in_refund'] and t['internal_group']=='expense'))
    candidates=[x for x in rows if valid(x)]
    # A global account must retain its accounting group and be unique.
    global_rows=[x for x in candidates if targets[rid(x['target_account'])]['internal_group']==source['internal_group']]
    choices={rid(x['target_account']) for x in global_rows}
    if len(choices)==1:return {'target_account':next(iter(choices)),'basis':'unique_historical_business_account','evidence_file':'historical-account-term-inference.json','evidence_count':len(global_rows),'evidence_source_line_examples':[x.get('source_line') for x in global_rows[:3]]}
    exact=[x for x in candidates if source_product and rid(x.get('product'))==source_product and x.get('move_type')==move_type]
    choices={rid(x['target_account']) for x in exact}
    if len(choices)==1:return {'target_account':next(iter(choices)),'basis':'exact_source_account_product_document_type','evidence_file':'historical-account-term-inference.json','evidence_count':len(exact),'evidence_source_line_examples':[x.get('source_line') for x in exact[:3]]}
    return None

def term_mapping(history):
    src={x['id']:x for x in history['source_terms']};dst={x['id']:x for x in history['target_terms']}
    sl={x['id']:x for x in history['source_term_lines']};tl={x['id']:x for x in history['target_term_lines']}
    result={}
    for group in history['term_inferences']:
        choices={rid(x.get('target_term')) for x in group['evidence']}
        if len(choices)!=1:continue
        sid=group['source_id'];tid=next(iter(choices));s=src.get(sid);t=dst.get(tid)
        if not s or not t or not t.get('active') or len(s['line_ids'])!=1 or len(t['line_ids'])!=1:continue
        a=sl[s['line_ids'][0]];b=tl[t['line_ids'][0]]
        source_full=a['value']=='balance' or a['value']=='percent' and a['value_amount']==100
        if source_full and a.get('option')=='day_after_invoice_date' and b['value']=='percent' and b['value_amount']==100 and b['delay_type']=='days_after' and a['days']==b['nb_days']:
            result[sid]=tid
    return result
