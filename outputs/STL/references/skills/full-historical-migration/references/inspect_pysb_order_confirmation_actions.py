"""Read server action definitions; never executes an action."""
import json
from pathlib import Path
import runpy

BASE = Path(__file__).parent
I = runpy.run_path(str(BASE / 'inspect_pysb_aug_oct_prod.py'))


def main():
    reader = I['ReadOnly']('v19-prod', ('https://py19.odoo.com', 'py19-main-33843450'))
    models = reader.scan('ir.model', [['model', 'in', ['purchase.order', 'sale.order']]], ['model'])
    actions = reader.scan('ir.actions.server', [['binding_model_id', 'in', [x['id'] for x in models]]], ['name', 'model_id', 'binding_model_id', 'state', 'code'])
    result = dict(database=reader.r.db, company_id=1, read_only=True, actions=actions)
    path = I['OUT'] / 'phases/order-confirmation-actions.json'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    for row in actions:
        if 'confirm' in row['name'].lower():
            print(json.dumps(row, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
