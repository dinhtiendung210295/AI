"""Read-only exhaustive July stock.move coverage, retaining legacy report keys."""
import argparse
import json
import runpy
import socket
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
EVIDENCE = ROOT / 'outputs/pysb-stock-migration-20261012'
START, END, COMPANY = '2026-06-30 16:00:00', '2026-07-31 16:00:00', 1
MOVE_FIELDS = ('name date state company_id product_id product_uom product_uom_qty '
 'quantity_done quantity location_id location_dest_id picking_id move_line_ids '
 'move_orig_ids move_dest_ids production_id raw_material_production_id '
 'unbuild_id consume_unbuild_id scrap_id scrapped inventory_id is_inventory '
 'origin_returned_move_id purchase_line_id sale_line_id').split()
LINE_FIELDS = ('move_id company_id product_id product_uom_id qty_done quantity '
 'location_id location_dest_id lot_id package_id result_package_id owner_id date').split()

def rid(v):
 return v[0] if isinstance(v, (list, tuple)) and v else v or False

def load(path):
 return json.loads(Path(path).read_text(encoding='utf8'))

def save(path, data):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8');temp.replace(path)

class ReadOnly:
 def __init__(self,reader):self.reader=reader;self.schemas={}
 def call(self,model,method,args,kwargs=None):
  if method not in {'read','search_read','search_count','fields_get'}:raise RuntimeError('Forbidden write method: '+method)
  return self.reader.call(model,method,args,kwargs or {})
 def fields(self,model,wanted):
  if model not in self.schemas:self.schemas[model]=self.call(model,'fields_get',[],{'attributes':['type']})
  return [f for f in wanted if f in self.schemas[model]]
 def read(self,model,ids,fields):
  ids=sorted(set(ids));rows=[]
  for n in range(0,len(ids),300):rows+=self.call(model,'read',[ids[n:n+300]],{'fields':self.fields(model,fields)})
  if {r['id'] for r in rows}!=set(ids):raise RuntimeError('Incomplete read: '+model)
  return rows

def paged(reader,model,domain,fields,page_size=500):
 count=reader.call(model,'search_count',[domain]);rows=[];cursor=0
 while True:
  batch=reader.call(model,'search_read',[domain+[['id','>',cursor]]],{'fields':reader.fields(model,fields),'limit':page_size,'order':'id asc'})
  if not batch:break
  ids=[r['id'] for r in batch]
  if ids!=sorted(set(ids)) or ids[0]<=cursor:raise RuntimeError('Invalid/duplicate ID page: '+model)
  rows+=batch;cursor=ids[-1]
 if len(rows)!=count or reader.call(model,'search_count',[domain])!=count:raise RuntimeError('Count changed or incomplete scan: '+model)
 return rows

def mapping_evidence(manifest,journal):
 maps={};conflicts={}
 def add(model,s,t):
  s,t=int(s),int(t);dest=maps.setdefault(model,{})
  if s in dest and dest[s]!=t:conflicts[(model,s)]=sorted({dest[s],t})
  dest[s]=t
 for evidence in [manifest,journal]:
  for model,pairs in evidence.get('maps',{}).items():
   for s,t in pairs.items():add(model,s,t)
 for key in ['supporting_source_transfers','standalone_source_receipts','supplementary_inventory_adjustments']:
  for row in journal.get(key,[]):
   if row.get('source_move') and row.get('target_move'):add('stock.move',row['source_move'],row['target_move'])
 for alias in journal.get('approved_opening_lot_aliases',[]):
  maps.setdefault('stock.lot',{})[alias['source_lot']]=alias['target_lot'];conflicts.pop(('stock.lot',alias['source_lot']),None)
 return maps,conflicts

def category(m,locations):
 src=locations.get(rid(m.get('location_id')),{}).get('usage');dst=locations.get(rid(m.get('location_dest_id')),{}).get('usage')
 if m.get('scrap_id') or m.get('scrapped'):return 'scrap'
 if m.get('unbuild_id') or m.get('consume_unbuild_id'):return 'unbuild'
 if m.get('raw_material_production_id'):return 'mo_raw'
 if m.get('production_id'):return 'mo_finished'
 if m.get('inventory_id') or m.get('is_inventory'):return 'inventory_adjustment'
 if m.get('origin_returned_move_id'):return 'return'
 if src=='supplier' and dst=='customer':return 'dropship'
 if (src=='inventory' and dst in {'internal','transit'}) or (dst=='inventory' and src in {'internal','transit'}):return 'inventory_adjustment'
 if src=='supplier' and dst in {'internal','transit'}:return 'receipt'
 if src in {'internal','transit'} and dst=='customer':return 'delivery'
 if src in {'internal','transit'} and dst in {'internal','transit'}:return 'internal_transfer'
 if src=='production' or dst=='production':return 'production_independent'
 return 'unclassified'

def verify_move(s,t,sl,tl,maps,conflicts,rounding):
 problems=[]
 if t is None:return ['missing_target_record']
 if t.get('state')!='done':problems.append('target_not_done')
 for model,field in [('product.product','product_id'),('uom.uom','product_uom'),('stock.location','location_id'),('stock.location','location_dest_id')]:
  sid=rid(s.get(field));expected=maps.get(model,{}).get(sid)
  if (model,sid) in conflicts:problems.append('conflicting_mapping:'+field)
  if not expected:problems.append('missing_mapping:'+field)
  elif expected!=rid(t.get(field)):problems.append('different:'+field)
 if rid(t.get('company_id'))!=COMPANY:problems.append('wrong_target_company')
 if s.get('date')!=t.get('date'):problems.append('different:date')
 sq,tq=s.get('quantity_done'),t.get('quantity')
 if sq is None or tq is None:problems.append('missing_done_quantity')
 elif abs(sq-tq)>1e-6:
  allowed=rounding.get(str(s['id']),{})
  if allowed.get('target_move')==t['id'] and abs(sq-allowed.get('source_qty',float('inf')))<1e-6 and abs(tq-allowed.get('target_qty',float('inf')))<1e-6:problems.append('approved_rounding')
  else:problems.append('different:done_quantity')
 dims=[('product.product','product_id'),('uom.uom','product_uom_id'),('stock.location','location_id'),('stock.location','location_dest_id'),('stock.lot','lot_id'),('stock.package','package_id'),('stock.package','result_package_id'),('res.partner','owner_id')]
 def ledger(rows,source):
  result=defaultdict(float)
  for line in rows:
   qty=line.get('qty_done' if source else 'quantity',0)
   if not qty:continue
   key=[]
   for model,field in dims:
    val=rid(line.get(field))
    if source and val:
     if (model,val) in conflicts:problems.append('conflicting_detail_mapping:'+field)
     mapped=maps.get(model,{}).get(val)
     if not mapped:problems.append('missing_detail_mapping:'+field)
     val=mapped
    key.append(val)
   result[tuple(key)]+=qty
  return result
 a,b=ledger(sl,True),ledger(tl,False)
 if sq and not a:problems.append('missing_source_done_lines')
 if tq and not b:problems.append('missing_target_done_lines')
 tol=0.00501 if 'approved_rounding' in problems else 1e-6
 if set(a)!=set(b) or any(abs(a[k]-b.get(k,0))>tol for k in a):problems.append('different:done_line_dimensions_or_quantity')
 return sorted(set(problems))

def scan(a,b,manifest,journal):
 maps,conflicts=mapping_evidence(manifest,journal)
 domain=[['company_id','=',COMPANY],['state','=','done'],['date','>=',START],['date','<',END]]
 moves=paged(a,'stock.move',domain,MOVE_FIELDS)
 lines=a.read('stock.move.line',[i for m in moves for i in m['move_line_ids']],LINE_FIELDS);sl=defaultdict(list)
 for line in lines:sl[rid(line['move_id'])].append(line)
 locs={x['id']:x for x in a.read('stock.location',[rid(m[f]) for m in moves for f in ['location_id','location_dest_id']],['usage','complete_name'])}
 mapped=maps.get('stock.move',{});tids=sorted({mapped[m['id']] for m in moves if m['id'] in mapped});targets=[]
 for n in range(0,len(tids),300):targets+=paged(b,'stock.move',[['id','in',tids[n:n+300]]],MOVE_FIELDS)
 ti={x['id']:x for x in targets};tl=defaultdict(list)
 for line in b.read('stock.move.line',[i for m in targets for i in m['move_line_ids']],LINE_FIELDS):tl[rid(line['move_id'])].append(line)
 inverse=Counter(mapped[m['id']] for m in moves if m['id'] in mapped);results=[]
 for m in moves:
  tid=mapped.get(m['id']);issues=verify_move(m,ti.get(tid),sl[m['id']],tl[tid],maps,conflicts,journal.get('precision_differences',{})) if tid else ['unmapped_move']
  if ('stock.move',m['id']) in conflicts:issues.append('conflicting_move_mapping')
  if tid and inverse[tid]>1:issues.append('target_move_shared_by_sources')
  group=category(m,locs)
  if group=='unclassified':issues.append('unclassified_source_move')
  status='verified' if not issues else 'approved_exception' if set(issues)=={'approved_rounding'} else 'unresolved'
  results.append({'source_move_id':m['id'],'target_move_id':tid,'category':group,'status':status,'issues':sorted(set(issues))})
 unresolved={x['source_move_id'] for x in results if x['status']=='unresolved'};pending=[m for m in moves if m['id'] in unresolved]
 picks=a.read('stock.picking',[rid(m['picking_id']) for m in moves if m.get('picking_id')],'name origin date_done state move_lines picking_type_id company_id'.split());pending_picks=[]
 for p in picks:
  unknown=sorted(set(p['move_lines'])&unresolved)
  if unknown:pending_picks.append({**p,'category':'in_period_moves','unknown_moves':unknown})
 counts=Counter(x['status'] for x in results)
 return {'schema_version':2,'read_only':True,'scan_complete':True,'checked_utc':datetime.now(timezone.utc).isoformat(),
  'scope':{'company_id':COMPANY,'start_utc_inclusive':START,'end_utc_exclusive':END,'timezone':'Asia/Singapore','basis':'stock.move.date; independent of order dates and product mapping'},
  'source_moves':moves,'source_lines':lines,'results':results,'pending_moves':pending,
  'source_pickings_in_july':len(picks),'pending_pickings':pending_picks,
  'pending_actual_adjustments':[m for m in pending if category(m,locs)=='inventory_adjustment'],
  'full_acceptance_ready':not unresolved and not counts['approved_exception'],
  'summary':{'source_moves_in_period':len(moves),'statuses':dict(counts),'categories':dict(Counter(x['category'] for x in results)),
   'other_pickings_not_replayed':len(pending_picks),'by_category':dict(Counter(category(m,locs) for m in pending)),
   'actual_adjustment_moves_not_replayed':sum(category(m,locs)=='inventory_adjustment' for m in pending),
   'inventory_groups_not_replayed':len({rid(m.get('inventory_id')) for m in pending if m.get('inventory_id')})}}

def acceptance_gate(path):
 path=Path(path)
 if not path.exists():return {'full_acceptance_ready':False,'reason':'missing_full_move_coverage'}
 report=load(path);rows=report.get('results',[]);counts=Counter(x['status'] for x in rows);scope=report.get('scope',{})
 valid=(report.get('schema_version')==2 and report.get('scan_complete') is True and scope.get('company_id')==COMPANY and scope.get('start_utc_inclusive')==START and scope.get('end_utc_exclusive')==END and len(rows)==report.get('summary',{}).get('source_moves_in_period') and len({x['source_move_id'] for x in rows})==len(rows) and {x['source_move_id'] for x in rows}=={x['id'] for x in report.get('source_moves',[])} and dict(counts)==report.get('summary',{}).get('statuses'))
 return {'full_acceptance_ready':bool(valid and set(counts)<={'verified'}),'coverage_valid':valid,'statuses':dict(counts),'reason':'move_coverage_only; inventory_totals_and_other_criteria_still_required','checked_utc':report.get('checked_utc')}

def readers():
 Reader=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/so-po-migration/scripts/test_prepare_july_2026_so_po_migration.py'))['OdooReader']
 a=Reader(ROOT/'mcp-server-odoo/envs/v14-prod/.env');b=Reader(ROOT/'mcp-server-odoo/envs/v19-staging/.env')
 if (a.url,a.db,b.url,b.db)!=('http://175.145.85.151','paoyeang_live','https://py-staging.odoo.com','py19-staging-39654560'):raise RuntimeError('Wrong source/target')
 return ReadOnly(a),ReadOnly(b)

def cli_args(description=__doc__):
 parser=argparse.ArgumentParser(description=description)
 parser.add_argument('--evidence-dir',type=Path,default=EVIDENCE)
 parser.add_argument('--output-dir',type=Path,default=ROOT/'outputs'/('pysb-stock-coverage-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')))
 return parser.parse_args()

def run_scan(evidence_dir,output_dir):
 if Path(output_dir).resolve()==Path(evidence_dir).resolve():raise RuntimeError('Use separate output directory; preserve historical evidence')
 if Path(output_dir).resolve()==EVIDENCE.resolve():raise RuntimeError('Never overwrite historical migration output')
 # Invalidate a previous report before any RPC: failure in downstream callers
 # must not leave an earlier successful scan looking current.
 save(Path(output_dir)/'july-other-stock-coverage.json',{'schema_version':2,'scan_complete':False,'full_acceptance_ready':False,'read_only':True,'phase':'scanning'})
 a,b=readers();report=scan(a,b,load(Path(evidence_dir)/'execution-manifest.json'),load(Path(evidence_dir)/'execution-journal.json'))
 save(Path(output_dir)/'july-other-stock-coverage.json',report);return a,b,report

def main():
 args=cli_args();socket.setdefaulttimeout(90)
 try:
  _,_,report=run_scan(args.evidence_dir,args.output_dir)
  print(json.dumps({'output_dir':str(args.output_dir),**report['summary']},ensure_ascii=False))
  return 0 if report['full_acceptance_ready'] else 1
 except Exception as error:
  if args.output_dir.resolve() not in {args.evidence_dir.resolve(),EVIDENCE.resolve()}:save(args.output_dir/'july-other-stock-coverage.json',{'schema_version':2,'scan_complete':False,'full_acceptance_ready':False,'error':str(error),'read_only':True})
  raise

if __name__=='__main__':raise SystemExit(main())
