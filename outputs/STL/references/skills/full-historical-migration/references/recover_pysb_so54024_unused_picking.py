"""One-time cleanup of this run's own empty picking after approval rejection."""
import runpy
from pathlib import Path
M=runpy.run_path(str(Path(__file__).with_name('migrate_pysb_independent_deliveries.py')))

def main():
    r=M['Run']();lock=runpy.run_path(str(Path(__file__).with_name('production_write_lock.py')))['acquire'](M['OUT'])
    state=r.j['groups']['63347']
    if state.get('cleanup_completed'):print('Already cleaned; no writes');return
    if state['phase']!='order_confirmed' or state['source_name']!='SO-54024' or state['target_order']!=4671:raise RuntimeError('Unexpected recovery scope')
    if not any(o['model']=='stock.picking' and o['method']=='create' and o.get('result')==4309 and o['args'][0]['origin']=='SO-54024' for o in r.j['operations']):raise RuntimeError('Picking not owned by this run')
    if any(t in [4309,18301] for model in ['stock.picking','stock.move'] for t in r.maps.get(model,{}).values()):raise RuntimeError('Unexpected attached source mapping; review first')
    order=r.b.read('sale.order',[4671],['state','picking_ids'])[0]
    picking=r.b.read('stock.picking',[4309],['state','move_ids'])[0]
    move=r.b.read('stock.move',[18301],['state','quantity','picked','move_line_ids','move_orig_ids','move_dest_ids'])[0]
    if order['state']!='draft' or order['picking_ids']!=[4309] or picking['move_ids']!=[18301] or move['state'] not in ['draft','confirmed'] or move['quantity'] or move['picked'] or move['move_line_ids'] or move['move_orig_ids'] or move['move_dest_ids']:raise RuntimeError('Unused-object recovery preconditions failed')
    state['cleanup_before']={'order':order,'picking':picking,'move':move};r.persist()
    r.mutate('stock.picking','unlink',[[4309]])
    if r.b.call('stock.picking','search_count',[[['id','=',4309]]]) or r.b.call('stock.move','search_count',[[['id','=',18301]]]):raise RuntimeError('Cleanup read-back failed')
    after=r.b.read('sale.order',[4671],['state','picking_ids'])[0]
    if after['state']!='draft' or after['picking_ids']:raise RuntimeError('SO did not return to clean held draft state')
    state.update(phase='confirmation_held',execution_hold=True,hold_reason='An approval is missing; own empty unvalidated preparation removed',cleanup_completed=True,cleanup_after=after);r.persist()
    print('SO-54024 held for native approval; own empty picking removed; no stock consumed')

if __name__=='__main__':main()
