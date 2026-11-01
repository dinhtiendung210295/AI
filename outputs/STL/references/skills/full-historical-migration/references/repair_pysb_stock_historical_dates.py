"""Restore source UTC dates after Odoo load timezone conversion; no validation."""
import runpy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[6]
H=runpy.run_path(str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/execute_pysb_stock_migration.py'))
def main():
 m=H['Migration']();matrix=m.matrix
 def write(model,fields,rows):matrix(model,fields,rows,batch_size=500)
 ps=H['index'](m.b.read('stock.picking',list(m.maps['stock.picking'].values()),['state']))
 write('stock.picking',['.id','scheduled_date','date_done'],[[t,m.sp[s]['scheduled_date'],m.sp[s]['date_done'] if ps[t]['state']=='done' else False] for s,t in m.maps['stock.picking'].items() if ps[t]['state']!='cancel'])
 ms=H['index'](m.b.read('mrp.production',list(m.maps['mrp.production'].values()),['state']))
 write('mrp.production',['.id','date_finished'],[[t,m.mos[s]['date_finished']] for s,t in m.maps['mrp.production'].items() if ms[t]['state']=='done'])
 write('stock.move',['.id','date'],[[t,(m.sm.get(s) or m.mm[s])['date']] for s,t in m.maps['stock.move'].items()])
 write('stock.move.line',['.id','date'],[[t,(m.sl.get(s) or m.ml[s])['date']] for s,t in m.maps['stock.move.line'].items()])
 m.j['historical_dates_utc_corrected']=True;m.persist()
if __name__=='__main__':main()
