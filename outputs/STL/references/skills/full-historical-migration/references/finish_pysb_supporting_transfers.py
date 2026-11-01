"""Use reviewed native validation and quantity readback for supporting transfers."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[6]
code=(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/finish_pysb_old_po_receipts.py').read_text(encoding='utf8')
for a,b in [('old-po-late-receipts-discovery.json','supporting-transfer-discovery.json'),('standalone_source_receipts','supporting_source_transfers'),('PYSB-OLD-PO-SUPPLY','PYSB-SUPPORT-STOCK'),('old_po_auto_push_cleanup','supporting_auto_push_cleanup'),('old_po_receipt_exceptions','supporting_transfer_exceptions'),('all-old-po-receipts-report.json','supporting-transfers-report.json')]:code=code.replace(a,b)
exec(compile(code,'<supporting-transfer-validation>','exec'),{'__name__':'__main__','__file__':str(ROOT/'.agents/skills/FC+TC/6-Data migration/full-historical-migration/references/finish_pysb_old_po_receipts.py')})
