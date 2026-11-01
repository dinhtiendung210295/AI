"""Read-only native PO dependency for the one dropship SO."""
import runpy
from pathlib import Path
BASE=Path(__file__).parent;M=runpy.run_path(str(BASE/'inspect_pysb_so_remediation.py'));D=M['DEST'];OUT=M['OUT'];load=M['load'];save=M['save'];rid=M['rid']
def main():
    a=M['M']['I']['ReadOnly']('v14-prod',('http://175.145.85.151','paoyeang_live'));b=M['M']['I']['ReadOnly']('v19-prod',('https://py19.odoo.com','py19-main-33843450'))
    source_move=a.read('stock.move',[533596],['state','product_id','product_uom_qty','product_uom','sale_line_id','purchase_line_id','location_id','location_dest_id','picking_id'])[0]
    sp=a.read('purchase.order.line',[21059],['order_id','product_id','product_qty','product_uom','move_ids'])[0]
    tp=b.read('purchase.order.line',[3888],['order_id','product_id','product_qty','product_uom_id','move_ids'])[0]
    so=b.read('sale.order',[9481],['state','order_line','picking_ids','company_id','x_studio_v14_reference_studio'])[0]
    po=b.read('purchase.order',[rid(tp['order_id'])],['name','state','picking_ids','picking_type_id','company_id','dest_address_id','order_line'])[0]
    moves=b.read('stock.move',tp['move_ids'],['state','company_id','product_id','product_uom','product_uom_qty','sale_line_id','purchase_line_id','location_id','location_dest_id','picking_id'])
    save(D/'dropship-65338-dependency.json',dict(source_move=source_move,source_purchase_line=sp,target_purchase_line=tp,target_po=po,target_so=so,target_moves=moves,read_only=True))
    print(dict(target_po=po['name'],target_po_state=po['state'],picking_type=po['picking_type_id'],target_moves=len(moves),so_state=so['state']),flush=True)
if __name__=='__main__':main()
