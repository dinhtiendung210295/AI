"""Production workflow context, separate from archive-inclusive read helpers."""
import runpy
from pathlib import Path

GUARD=runpy.run_path(str(Path(__file__).parent/'production_phase_guard.py'))['require_access']
def workflow_options(kwargs=None):
    options=dict(kwargs or {})
    options['context']={**options.get('context',{}),'allowed_company_ids':[1],'active_test':True}
    return options

def call(reader,model,method,args,kwargs=None):
    if (reader.url,reader.db)!=('https://py19.odoo.com','py19-main-33843450'):raise RuntimeError('Production workflow database identity mismatch')
    options=workflow_options(kwargs)
    token=options['context'].pop('pysb_phase_token',None)
    GUARD(token)
    return reader.models.execute_kw(reader.db,reader.uid,reader.secret,model,method,args,options)
