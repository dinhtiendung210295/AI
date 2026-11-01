"""Read back mapped stock moves; an External ID alone never proves completion."""
import argparse
import json
import runpy
import socket
from collections import Counter, defaultdict
from datetime import datetime,timezone
from pathlib import Path

BASE=Path(__file__).resolve().parent
I=runpy.run_path(str(BASE/'inspect_pysb_aug_oct_prod.py'))
S=runpy.run_path(str(BASE/'scan_pysb_july_other_stock_coverage.py'))
OUT,save,ReadOnly=I['OUT'],I['save'],I['ReadOnly']
def load(n):return json.loads((OUT/n).read_text(encoding='utf8'))

def incremental_selection(maps, moves, previous, cached):
    if not previous.get('scan_complete') or previous.get('schema_version')!=2:raise RuntimeError('Complete compatible baseline required')
    old={x['source_move_id']:x for x in previous['results']};cache={x['id']:x for x in cached};refresh=set()
    for move in moves:
        sid=move['id'];tid=maps.get('stock.move',{}).get(sid);row=old.get(sid,{})
        if tid and (tid not in cache or row.get('target_move_id')!=tid or row.get('status') not in ['verified','approved_exception']):refresh.add(tid)
    return refresh

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--after-run',action='store_true');parser.add_argument('--rescan-source',action='store_true');parser.add_argument('--source-only',action='store_true');parser.add_argument('--incremental',action='store_true');args=parser.parse_args()
    if args.incremental and (not args.after_run or args.rescan_source or args.source_only):raise RuntimeError('Incremental requires after-run without source rescan')
    if args.source_only:args.rescan_source=True
    if args.source_only and args.after_run:raise RuntimeError('Source-only scan must not rewrite target mapping')
    socket.setdefaulttimeout(120)
    manifest=load('discovery-manifest.json');moves=load('source-moves.json');lines=load('source-move-lines.json')
    maps={model:{int(s):t for s,t in pairs.items()} for model,pairs in manifest['maps'].items()}
    if args.after_run:maps=runpy.run_path(str(BASE/'stock_confirmation_handoff.py'))['apply'](maps,OUT)
    rounding_records={};unit_aliases={}
    if args.after_run:
        for name in ['independent-receipts-journal.json','independent-mo-journal.json','independent-delivery-journal.json','independent-inventory-journal.json','opening-lot-resolution.json']:
            if not (OUT/name).exists():continue
            journal=load(name)
            if name=='independent-inventory-journal.json':
                for group in journal['groups'].values():
                    if group['status']=='verified_done':
                        for row in group['before']:
                            if row.get('target_unit_alias_proof'):unit_aliases[row['source_move']]=row['target_unit_alias_proof']
            for row in journal.get('rounding_differences',[]):
                sid=int(row['source_line'])
                if sid in rounding_records and rounding_records[sid]!=row:raise RuntimeError('Conflicting rounding evidence')
                rounding_records[sid]=row
            for model,pairs in journal['maps'].items():
                for sid,tid in pairs.items():
                    sid=int(sid);old=maps.setdefault(model,{}).get(sid)
                    if old and old!=tid:raise RuntimeError('Journal/manifest mapping conflict')
                    maps[model][sid]=tid
        save('after-run-stock-mapping.json',{'maps':maps,'origin':'baseline manifest plus journal; completion requires live read-back'})
    conflicts={(x['model'],x['source_id']):x['targets'] for x in manifest['mapping_conflicts']}
    source_changes={};source_rescan=None
    if args.rescan_source:
        rescan_started=datetime.now(timezone.utc).isoformat()
        scope=load('scope.json');a=ReadOnly('v14-prod',('http://175.145.85.151','paoyeang_live'))
        current=a.scan('stock.move',[['company_id','=',1],['state','=','done'],['date','>=',scope['start_utc']],['date','<',scope['end_utc_exclusive']]],S['MOVE_FIELDS'])
        current_lines=a.read('stock.move.line',[i for x in current for i in x['move_line_ids']],S['LINE_FIELDS'])
        save('source-current-moves-rescan.json',current);save('source-current-lines-rescan.json',current_lines)
        ci={x['id']:x for x in current};cli={x['id']:x for x in current_lines};frozen_ids={x['id'] for x in moves}
        source_lines_by_mid=defaultdict(list)
        for row in lines:source_lines_by_mid[S['rid'](row['move_id'])].append(row)
        def differs(s,t,fields):
            if t is None:return ['missing_record']
            errors=[]
            for field in fields:
                have=t.get(field);want=s.get(field)
                if field.endswith('_ids'):bad=set(have or [])!=set(want or [])
                elif field.endswith('_id') or field=='product_uom':bad=S['rid'](have)!=S['rid'](want)
                elif isinstance(want,(int,float)) and not isinstance(want,bool):bad=have is None or abs(have-want)>1e-9
                else:bad=have!=want
                if bad:errors.append(field)
            return errors
        for move in moves:
            changed=differs(move,ci.get(move['id']),['name','state','date','company_id','product_id','product_uom','product_uom_qty','quantity_done','location_id','location_dest_id','picking_id','move_line_ids','move_orig_ids','move_dest_ids','origin_returned_move_id','purchase_line_id','sale_line_id','production_id','raw_material_production_id','unbuild_id','consume_unbuild_id','inventory_id','scrapped'])
            for row in source_lines_by_mid[move['id']]:
                changed.extend('line_'+field+':'+str(row['id']) for field in differs(row,cli.get(row['id']),['move_id','company_id','product_id','product_uom_id','qty_done','location_id','location_dest_id','lot_id','package_id','result_package_id','owner_id','date']))
            if changed:source_changes[move['id']]=changed
        source_rescan={'complete':True,'started_utc':rescan_started,'completed_utc':datetime.now(timezone.utc).isoformat(),'frozen_moves':len(moves),'current_moves':len(current),'added_since_snapshot':sorted(set(ci)-frozen_ids),'changed_frozen_moves':source_changes,'snapshot_unchanged':not source_changes and set(ci)==frozen_ids}
        save('source-frozen-rescan-comparison.json',source_rescan)
        if args.source_only:
            print(json.dumps({'frozen_moves':len(moves),'current_moves':len(current),'added':len(source_rescan['added_since_snapshot']),'changed':len(source_changes),'snapshot_unchanged':source_rescan['snapshot_unchanged']}),flush=True);return
    b=ReadOnly('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    tids=[maps.get('stock.move',{}).get(x['id']) for x in moves];tids=[x for x in tids if x]
    previous=load('after-run-stock-coverage.json') if args.incremental else None
    if args.incremental:
        if previous['snapshot_scope']!=load('scope.json'):raise RuntimeError('Incremental baseline belongs to another scope')
        cached=load('after-run-mapped-target-stock-moves.json');cached_lines=load('after-run-mapped-target-stock-lines.json')
        refresh=incremental_selection(maps,moves,previous,cached)
        fresh=b.scan('stock.move',[['id','in',sorted(refresh)]],S['MOVE_FIELDS']) if refresh else []
        fresh_lines=b.read('stock.move.line',[i for x in fresh for i in x['move_line_ids']],S['LINE_FIELDS'])
        target=[x for x in cached if x['id'] in set(tids) and x['id'] not in refresh]+fresh
        target_lines=[x for x in cached_lines if S['rid'](x['move_id']) in set(tids) and S['rid'](x['move_id']) not in refresh]+fresh_lines
    else:
        target=b.scan('stock.move',[['id','in',tids]],S['MOVE_FIELDS'])
        target_lines=b.read('stock.move.line',[i for x in target for i in x['move_line_ids']],S['LINE_FIELDS'])
    prefix='after-run-' if args.after_run else ''
    save(prefix+'mapped-target-stock-moves.json',target);save(prefix+'mapped-target-stock-lines.json',target_lines)
    ti={x['id']:x for x in target};sl,tl=defaultdict(list),defaultdict(list)
    for x in lines:sl[S['rid'](x['move_id'])].append(x)
    for x in target_lines:tl[S['rid'](x['move_id'])].append(x)
    locations={x['id']:x for x in load('source-stock.location.json')}
    alias_units={}
    if unit_aliases:
        alias_ids=sorted({x['id'] for proof in unit_aliases.values() for chain in ['mapped_chain','native_chain'] for x in proof[chain]})
        alias_units={x['id']:x for x in b.read('uom.uom',alias_ids,['factor','rounding','relative_factor','relative_uom_id'])}
    results=[];inverse=Counter(tids)
    adjust=runpy.run_path(str(BASE/'approved_stock_rounding.py'))['adjusted_source']
    su={x['id']:x for x in load('source-uom.uom.json')};tu={x['id']:x for x in load('target-uom.uom.json')}
    for move in moves:
        tid=maps.get('stock.move',{}).get(move['id'])
        move_maps=maps;alias=unit_aliases.get(move['id'])
        if alias:
            source_unit=S['rid'](move['product_uom']);mapped_unit=maps['uom.uom'][source_unit]
            runpy.run_path(str(BASE/'same_factor_unit_alias.py'))['check'](alias,mapped_unit,alias['native_target_unit'],alias_units)
            move_maps={**maps,'uom.uom':{**maps['uom.uom'],source_unit:alias['native_target_unit']}}
        issues=S['verify_move'](move,ti.get(tid),sl[move['id']],tl[tid],move_maps,conflicts,{}) if tid else ['unmapped_move']
        if tid and inverse[tid]>1:issues.append('target_move_shared_by_sources')
        if ('stock.move',move['id']) in conflicts:issues.append('conflicting_move_mapping')
        if move['id'] in source_changes:issues.append('source_changed_since_snapshot')
        status='verified' if not issues else 'unresolved';approved=[]
        if issues and tid and inverse[tid]==1 and any(x['id'] in rounding_records for x in sl[move['id']]):
            adjusted,adjusted_lines,approved=adjust(move,sl[move['id']],rounding_records,move_maps,su,tu)
            remaining=S['verify_move'](adjusted,ti.get(tid),adjusted_lines,tl[tid],move_maps,conflicts,{})
            if not remaining and move['id'] not in source_changes:status='approved_exception'
        results.append({'source_move_id':move['id'],'target_move_id':tid,'category':S['category'](move,locations),'status':status,'issues':issues,'approved_rounding_differences':approved,'target_unit_alias_proof':alias})
    report={'schema_version':2,'read_only':True,'scan_complete':True,'generated_utc':datetime.now(timezone.utc).isoformat(),'snapshot_scope':load('scope.json'),'source_rescan':source_rescan,'results':results,
            'summary':{'source_moves_in_period':len(moves),'statuses':dict(Counter(x['status'] for x in results))},
            'full_acceptance_ready':all(x['status']=='verified' for x in results) and bool(source_rescan and source_rescan['snapshot_unchanged'])}
    report['verification_mode']='incremental' if args.incremental else 'full'
    report['full_target_readback_utc']=previous.get('full_target_readback_utc',previous['generated_utc']) if args.incremental else report['generated_utc']
    report['target_moves_read_live']=len(refresh) if args.incremental else len(tids)
    if args.incremental:report['full_acceptance_ready']=False
    save('after-run-stock-coverage.json' if args.after_run else 'baseline-stock-coverage.json',report)
    print(json.dumps(report['summary']),flush=True)

if __name__=='__main__':main()
