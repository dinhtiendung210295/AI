#!/usr/bin/env python3
"""Read-only post-import validation for the July 2026 PYSB SO/PO migration."""

from __future__ import annotations

import argparse
import json
import runpy
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


COMPANY_ID = 1
START = "2026-07-01 00:00:00"
END = "2026-08-01 00:00:00"
TOLERANCE = 0.01


def relation_id(value: Any) -> int | None:
    return int(value[0]) if isinstance(value, (list, tuple)) and value else None


def relation_name(value: Any) -> str:
    return str(value[1]) if isinstance(value, (list, tuple)) and len(value) > 1 else ""


def expected_uom_name(value: Any) -> str:
    name = relation_name(value)
    return {"UNIT": "Units"}.get(name, name)


def style(ws) -> None:
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E78")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for col in range(1, ws.max_column + 1):
        width = max(len(str(ws.cell(row, col).value or "")) for row in range(1, min(ws.max_row, 1000) + 1))
        ws.column_dimensions[get_column_letter(col)].width = min(max(width + 2, 11), 55)


def imported_external_ids(reader, model: str) -> dict[int, int]:
    records = reader.search_read("ir.model.data", [["module", "=", "pysb_v14"], ["model", "=", model]], ["name", "res_id"])
    result: dict[int, int] = {}
    prefix = model.replace(".", "_") + "_"
    for record in records:
        name = record["name"]
        if name.startswith(prefix):
            result[int(name.removeprefix(prefix))] = int(record["res_id"])
    return result


def add_exception(exceptions: list[dict[str, Any]], scope: str, source_id: int, reference: str, field: str, source_value: Any, target_value: Any) -> None:
    exceptions.append({"scope": scope, "source_id": source_id, "reference": reference, "field": field, "source": source_value, "target": target_value})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v14-env", type=Path, default=Path("mcp-server-odoo/.env.paoyeang.local"))
    parser.add_argument("--v19-env", type=Path, default=Path("mcp-server-odoo/.env"))
    parser.add_argument("--output", type=Path, default=Path("Ref/PYSB_JULY_2026_SO_PO/PYSB_SO_PO_JULY_2026_POST_IMPORT_VALIDATION.xlsx"))
    args = parser.parse_args()

    prepare = runpy.run_path(str(Path(__file__).with_name("test_prepare_july_2026_so_po_migration.py")))
    Reader = prepare["OdooReader"]
    source = Reader(args.v14_env)
    target = Reader(args.v19_env)
    exceptions: list[dict[str, Any]] = []

    sale_domain = [["company_id", "=", COMPANY_ID], ["date_order", ">=", START], ["date_order", "<", END], ["state", "in", ["sale", "done"]], ["is_quotation_template", "=", False]]
    purchase_domain = [["company_id", "=", COMPANY_ID], ["date_order", ">=", START], ["date_order", "<", END], ["state", "in", ["purchase", "done"]]]
    sale_fields = ["id", "name", "date_order", "partner_id", "warehouse_id", "amount_untaxed", "amount_tax", "amount_total", "order_line"]
    purchase_fields = ["id", "name", "date_order", "partner_id", "picking_type_id", "amount_untaxed", "amount_tax", "amount_total", "order_line"]
    source_sales = source.search_read("sale.order", sale_domain, sale_fields, order="id asc")
    source_purchases = source.search_read("purchase.order", purchase_domain, purchase_fields, order="id asc")

    sale_external = imported_external_ids(target, "sale.order")
    sale_line_external = imported_external_ids(target, "sale.order.line")
    purchase_external = imported_external_ids(target, "purchase.order")
    purchase_line_external = imported_external_ids(target, "purchase.order.line")
    target_sales = {record["id"]: record for record in target.read("sale.order", sale_external.values(), ["id", "name", "state", "x_studio_v14_reference_studio", "x_studio_date_reference_v14_studio", "partner_id", "warehouse_id", "amount_untaxed", "amount_tax", "amount_total", "order_line"])}
    target_purchases = {record["id"]: record for record in target.read("purchase.order", purchase_external.values(), ["id", "name", "state", "x_studio_v14_reference_studio", "x_studio_date_ref_v14_studio", "partner_id", "picking_type_id", "amount_untaxed", "amount_tax", "amount_total", "order_line"])}

    for record in source_sales:
        target_id = sale_external.get(record["id"])
        target_record = target_sales.get(target_id)
        if not target_record:
            add_exception(exceptions, "sale.order", record["id"], record["name"], "record", "present", "missing")
            continue
        checks = {
            "v14_reference": (record["name"], target_record.get("x_studio_v14_reference_studio")),
            "state": ("draft", target_record.get("state")),
            "warehouse": (relation_name(record.get("warehouse_id")), relation_name(target_record.get("warehouse_id"))),
            "line_count": (len(record["order_line"]), len(target_record["order_line"])),
        }
        for field, (source_value, target_value) in checks.items():
            if source_value != target_value:
                add_exception(exceptions, "sale.order", record["id"], record["name"], field, source_value, target_value)
        for field in ("amount_untaxed", "amount_tax", "amount_total"):
            if abs(float(record.get(field) or 0) - float(target_record.get(field) or 0)) > TOLERANCE:
                add_exception(exceptions, "sale.order", record["id"], record["name"], field, record.get(field) or 0, target_record.get(field) or 0)
        source_date = datetime.strptime(record["date_order"], "%Y-%m-%d %H:%M:%S")
        target_date = datetime.strptime(target_record["x_studio_date_reference_v14_studio"], "%Y-%m-%d %H:%M:%S") + timedelta(hours=7)
        if source_date != target_date:
            add_exception(exceptions, "sale.order", record["id"], record["name"], "date_reference_local", source_date, target_date)

    for record in source_purchases:
        target_id = purchase_external.get(record["id"])
        target_record = target_purchases.get(target_id)
        if not target_record:
            add_exception(exceptions, "purchase.order", record["id"], record["name"], "record", "present", "missing")
            continue
        checks = {
            "v14_reference": (record["name"], target_record.get("x_studio_v14_reference_studio")),
            "state": ("draft", target_record.get("state")),
            "deliver_to": (relation_name(record.get("picking_type_id")), relation_name(target_record.get("picking_type_id"))),
            "line_count": (len(record["order_line"]), len(target_record["order_line"])),
        }
        for field, (source_value, target_value) in checks.items():
            if source_value != target_value:
                add_exception(exceptions, "purchase.order", record["id"], record["name"], field, source_value, target_value)
        for field in ("amount_untaxed", "amount_tax", "amount_total"):
            if abs(float(record.get(field) or 0) - float(target_record.get(field) or 0)) > TOLERANCE:
                add_exception(exceptions, "purchase.order", record["id"], record["name"], field, record.get(field) or 0, target_record.get(field) or 0)

    source_sale_lines = {record["id"]: record for record in source.read("sale.order.line", [line_id for order in source_sales for line_id in order["order_line"]], ["id", "order_id", "display_type", "product_id", "name", "product_uom_qty", "product_uom", "price_unit", "discount", "price_subtotal", "route_id", "tax_id"])}
    target_sale_lines = {record["id"]: record for record in target.read("sale.order.line", sale_line_external.values(), ["id", "order_id", "display_type", "product_id", "name", "product_uom_qty", "product_uom_id", "price_unit", "discount", "price_subtotal", "route_ids", "tax_ids"])}
    for source_id, record in source_sale_lines.items():
        target_record = target_sale_lines.get(sale_line_external.get(source_id))
        reference = relation_name(record.get("order_id"))
        if not target_record:
            add_exception(exceptions, "sale.order.line", source_id, reference, "record", "present", "missing")
            continue
        pairs = {
            "display_type": (record.get("display_type") or False, target_record.get("display_type") or False),
            "description": (record.get("name") or "", target_record.get("name") or ""),
            "quantity": (record.get("product_uom_qty") or 0, target_record.get("product_uom_qty") or 0),
            "uom": (expected_uom_name(record.get("product_uom")), relation_name(target_record.get("product_uom_id"))),
            "route": (relation_name(record.get("route_id")), ", ".join(sorted(relation_name(route) if isinstance(route, (list, tuple)) else str(route) for route in []))),
        }
        target_route_names = []
        if target_record.get("route_ids"):
            route_records = target.read("stock.route", target_record["route_ids"], ["name"])
            target_route_names = sorted(item["name"] for item in route_records)
        pairs["route"] = (relation_name(record.get("route_id")), ", ".join(target_route_names))
        for field, (source_value, target_value) in pairs.items():
            if source_value != target_value:
                add_exception(exceptions, "sale.order.line", source_id, reference, field, source_value, target_value)
        for field in ("price_unit", "discount", "price_subtotal"):
            if abs(float(record.get(field) or 0) - float(target_record.get(field) or 0)) > TOLERANCE:
                add_exception(exceptions, "sale.order.line", source_id, reference, field, record.get(field) or 0, target_record.get(field) or 0)

    source_purchase_lines = {record["id"]: record for record in source.read("purchase.order.line", [line_id for order in source_purchases for line_id in order["order_line"]], ["id", "order_id", "display_type", "product_id", "name", "product_qty", "product_uom", "price_unit", "price_subtotal", "taxes_id"])}
    target_purchase_lines = {record["id"]: record for record in target.read("purchase.order.line", purchase_line_external.values(), ["id", "order_id", "display_type", "product_id", "name", "product_qty", "product_uom_id", "price_unit", "price_subtotal", "tax_ids"])}
    for source_id, record in source_purchase_lines.items():
        target_record = target_purchase_lines.get(purchase_line_external.get(source_id))
        reference = relation_name(record.get("order_id")).split(" (", 1)[0]
        if not target_record:
            add_exception(exceptions, "purchase.order.line", source_id, reference, "record", "present", "missing")
            continue
        pairs = {
            "display_type": (record.get("display_type") or False, target_record.get("display_type") or False),
            "description": (record.get("name") or "", target_record.get("name") or ""),
            "quantity": (record.get("product_qty") or 0, target_record.get("product_qty") or 0),
            "uom": (expected_uom_name(record.get("product_uom")), relation_name(target_record.get("product_uom_id"))),
        }
        for field, (source_value, target_value) in pairs.items():
            if source_value != target_value:
                add_exception(exceptions, "purchase.order.line", source_id, reference, field, source_value, target_value)
        for field in ("price_unit", "price_subtotal"):
            if abs(float(record.get(field) or 0) - float(target_record.get(field) or 0)) > TOLERANCE:
                add_exception(exceptions, "purchase.order.line", source_id, reference, field, record.get(field) or 0, target_record.get(field) or 0)

    route_counts = Counter()
    for record in target_sale_lines.values():
        for route_id in record.get("route_ids", []):
            route_counts[route_id] += 1
    route_names = {record["id"]: record["name"] for record in target.read("stock.route", route_counts.keys(), ["id", "name"])}
    warehouse_counts = Counter(relation_name(record.get("warehouse_id")) for record in target_sales.values())

    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.append(["Metric", "Value"])
    metrics = {
        "Source SO": len(source_sales), "Imported SO": len(target_sales), "Source SO lines": len(source_sale_lines), "Imported SO lines": len(target_sale_lines),
        "Source PO": len(source_purchases), "Imported PO": len(target_purchases), "Source PO lines": len(source_purchase_lines), "Imported PO lines": len(target_purchase_lines), "Validation exceptions": len(exceptions),
    }
    for key, value in metrics.items():
        ws.append([key, value])
    style(ws)
    ws = wb.create_sheet("Warehouse Route Counts")
    ws.append(["Type", "Name", "Count"])
    for name, count in sorted(warehouse_counts.items()):
        ws.append(["Warehouse", name, count])
    for route_id, count in sorted(route_counts.items(), key=lambda item: route_names.get(item[0], "")):
        ws.append(["Route", route_names.get(route_id, route_id), count])
    style(ws)
    ws = wb.create_sheet("Exceptions")
    ws.append(["scope", "source_id", "reference", "field", "source", "target"])
    for exception in exceptions:
        ws.append([exception[key] for key in ["scope", "source_id", "reference", "field", "source", "target"]])
    style(ws)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(args.output)
    print(json.dumps({**metrics, "warehouse_counts": warehouse_counts, "route_counts": {route_names.get(route_id, str(route_id)): count for route_id, count in route_counts.items()}, "output": str(args.output)}, indent=2, default=str))
    if exceptions:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
