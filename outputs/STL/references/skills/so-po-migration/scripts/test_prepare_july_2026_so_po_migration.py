#!/usr/bin/env python3
"""Prepare read-only v14 July 2026 SO/PO imports and a v19 preflight audit."""

from __future__ import annotations

import argparse
import json
import xmlrpc.client
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


COMPANY_ID = 1
START = "2026-07-01 00:00:00"
END = "2026-08-01 00:00:00"
OUTPUT_DIR = Path("Ref/PYSB_JULY_2026_SO_PO")
SO_BATCH_SIZE = 200


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


class OdooReader:
    def __init__(self, env_path: Path):
        env = load_env(env_path)
        self.url = env["ODOO_URL"].rstrip("/")
        self.db = env["ODOO_DB"]
        self.user = env.get("ODOO_USER") or env.get("ODOO_USERNAME")
        self.secret = env.get("ODOO_API_KEY") or env.get("ODOO_PASSWORD")
        common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common", allow_none=True)
        self.uid = common.authenticate(self.db, self.user, self.secret, {})
        if not self.uid:
            raise RuntimeError(f"Authentication failed for {self.url}")
        self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object", allow_none=True)

    def call(self, model: str, method: str, args: list[Any], kwargs: dict[str, Any] | None = None):
        options = dict(kwargs or {})
        context = dict(options.get("context") or {})
        context.update({"allowed_company_ids": [COMPANY_ID], "active_test": False})
        options["context"] = context
        return self.models.execute_kw(self.db, self.uid, self.secret, model, method, args, options)

    def search_read(self, model: str, domain: list[Any], fields: list[str], *, order="id asc"):
        return self.call(model, "search_read", [domain], {"fields": fields, "limit": 100000, "order": order})

    def read(self, model: str, ids: Iterable[int], fields: list[str]):
        ids = list(dict.fromkeys(int(record_id) for record_id in ids if record_id))
        result: list[dict[str, Any]] = []
        for start in range(0, len(ids), 500):
            result.extend(self.call(model, "read", [ids[start:start + 500]], {"fields": fields}))
        return result


def relation_id(value: Any) -> int | None:
    return int(value[0]) if isinstance(value, (list, tuple)) and value else None


def relation_name(value: Any) -> str:
    return str(value[1]) if isinstance(value, (list, tuple)) and len(value) > 1 else ""


def excel_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")


def chunks(values: list[Any], size: int = 500):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def search_read_in(reader: OdooReader, model: str, field: str, values: Iterable[Any], fields: list[str]):
    values = list(dict.fromkeys(value for value in values if value not in (None, False, "")))
    records: list[dict[str, Any]] = []
    for batch in chunks(values):
        records.extend(reader.search_read(model, [[field, "in", batch]], fields))
    return records


def style(ws) -> None:
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E78")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for col in range(1, ws.max_column + 1):
        width = max(len(str(ws.cell(row, col).value or "")) for row in range(1, min(ws.max_row, 500) + 1))
        ws.column_dimensions[get_column_letter(col)].width = min(max(width + 2, 11), 48)


def save_rows(path: Path, headers: list[str], rows: list[list[Any]]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(headers)
    for row in rows:
        ws.append(row)
    style(ws)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


class TargetMapper:
    def __init__(self, target: OdooReader):
        self.target = target
        self.exceptions: list[dict[str, Any]] = []

    def record_exception(self, scope: str, source_id: int, field: str, value: Any, reason: str) -> None:
        self.exceptions.append({"scope": scope, "source_id": source_id, "field": field, "value": value, "reason": reason})

    def by_exact_name(self, model: str, source: list[dict[str, Any]], *, name_field="name", company_scoped=False):
        names = [record.get(name_field) for record in source if record.get(name_field)]
        fields = ["id", name_field, "display_name"] + (["company_id"] if company_scoped else [])
        candidates = search_read_in(self.target, model, name_field, names, fields)
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for candidate in candidates:
            grouped[str(candidate.get(name_field) or "").casefold()].append(candidate)
        result: dict[int, int] = {}
        for record in source:
            name = str(record.get(name_field) or "")
            matches = grouped.get(name.casefold(), [])
            if company_scoped and len(matches) > 1:
                source_company = relation_id(record.get("company_id"))
                scoped = [item for item in matches if relation_id(item.get("company_id")) == source_company]
                matches = scoped or [item for item in matches if relation_id(item.get("company_id")) is None]
            if len(matches) == 1:
                result[record["id"]] = matches[0]["id"]
            else:
                self.record_exception(model, record["id"], name_field, name, "missing" if not matches else "ambiguous")
        return result

    def partners(self, source: list[dict[str, Any]]) -> dict[int, int]:
        refs = [record.get("ref") for record in source if record.get("ref")]
        vats = [record.get("vat") for record in source if record.get("vat")]
        names = [record.get("name") for record in source if record.get("name")]
        candidates: dict[int, dict[str, Any]] = {}
        for field, values in (("ref", refs), ("vat", vats), ("name", names)):
            for record in search_read_in(self.target, "res.partner", field, values, ["id", "name", "display_name", "ref", "vat", "company_id", "is_company", "parent_id", "type", "email", "phone", "street", "street2", "city", "zip"]):
                candidates[record["id"]] = record
        result: dict[int, int] = {}
        for record in source:
            matches = [item for item in candidates.values() if str(item.get("name") or "").casefold() == str(record.get("name") or "").casefold()]
            vat_only_candidates: list[dict[str, Any]] = []
            if not matches:
                # Foreign VAT identifiers may be shared by unrelated vendors.
                # A different name must not be accepted on VAT alone, even
                # when only one target candidate exists. XMLID verification
                # or review is required outside this legacy name/ref mapper.
                matches = [item for item in candidates.values() if record.get("ref") and item.get("ref") == record.get("ref")]
                vat_only_candidates = [item for item in candidates.values() if record.get("vat") and item.get("vat") == record.get("vat")]
            company_matches = [item for item in matches if relation_id(item.get("company_id")) in (None, COMPANY_ID)]
            matches = company_matches or matches
            if len(matches) > 1:
                structural = [item for item in matches if bool(item.get("is_company")) == bool(record.get("is_company")) and item.get("type") == record.get("type")]
                matches = structural or matches
            if len(matches) > 1:
                scored: list[tuple[int, dict[str, Any]]] = []
                for item in matches:
                    score = sum(
                        1 for field in ("ref", "vat", "email", "phone", "street", "street2", "city", "zip")
                        if record.get(field) not in (None, False, "") and str(item.get(field) or "").casefold() == str(record.get(field) or "").casefold()
                    )
                    scored.append((score, item))
                best = max((score for score, _item in scored), default=-1)
                best_matches = [item for score, item in scored if score == best]
                if best > 0:
                    matches = best_matches
            if len(matches) == 1:
                result[record["id"]] = matches[0]["id"]
            else:
                reason = "ambiguous" if matches else "name_mismatch_vat_only" if vat_only_candidates else "missing"
                self.record_exception("res.partner", record["id"], "name", record.get("name"), reason)
        return result

    def products(self, source: list[dict[str, Any]]) -> dict[int, int]:
        codes = [record.get("default_code") for record in source if record.get("default_code")]
        barcodes = [record.get("barcode") for record in source if record.get("barcode")]
        names = [record.get("name") for record in source if record.get("name")]
        candidates: dict[int, dict[str, Any]] = {}
        for field, values in (("default_code", codes), ("barcode", barcodes), ("name", names)):
            for record in search_read_in(self.target, "product.product", field, values, ["id", "name", "display_name", "default_code", "barcode", "company_id", "active"]):
                candidates[record["id"]] = record
        result: dict[int, int] = {}
        for record in source:
            if record.get("barcode"):
                matches = [item for item in candidates.values() if item.get("barcode") == record["barcode"]]
            elif record.get("default_code"):
                matches = [item for item in candidates.values() if item.get("default_code") == record["default_code"]]
            else:
                matches = [item for item in candidates.values() if str(item.get("name") or "").casefold() == str(record.get("name") or "").casefold()]
            exact_names = [item for item in matches if str(item.get("name") or "").casefold() == str(record.get("name") or "").casefold()]
            matches = exact_names or matches
            if len(matches) > 1:
                source_company = relation_id(record.get("company_id"))
                scoped = [item for item in matches if relation_id(item.get("company_id")) == source_company]
                matches = scoped or [item for item in matches if relation_id(item.get("company_id")) is None]
            if len(matches) > 1 and record.get("barcode"):
                barcode_matches = [item for item in matches if item.get("barcode") == record.get("barcode")]
                matches = barcode_matches or matches
            if len(matches) > 1 and not record.get("default_code") and not record.get("barcode"):
                blank_identifier_matches = [item for item in matches if not item.get("default_code") and not item.get("barcode")]
                matches = blank_identifier_matches or matches
            if len(matches) > 1:
                active_matches = [item for item in matches if item.get("active")]
                matches = active_matches or matches
            if len(matches) == 1:
                result[record["id"]] = matches[0]["id"]
            else:
                self.record_exception("product.product", record["id"], "default_code/name", record.get("default_code") or record.get("name"), "missing" if not matches else "ambiguous")
        return result


def display_type(value: Any) -> str | None:
    return {"line_note": "Note", "line_section": "Section"}.get(value) if value else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v14-env", type=Path, default=Path("mcp-server-odoo/.env.paoyeang.local"))
    parser.add_argument("--v19-env", type=Path, default=Path("mcp-server-odoo/.env"))
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    source = OdooReader(args.v14_env)
    target = OdooReader(args.v19_env)
    mapper = TargetMapper(target)

    sale_domain = [["company_id", "=", COMPANY_ID], ["date_order", ">=", START], ["date_order", "<", END], ["state", "in", ["sale", "done"]]]
    purchase_domain = [["company_id", "=", COMPANY_ID], ["date_order", ">=", START], ["date_order", "<", END], ["state", "in", ["purchase", "done"]]]
    sale_fields = ["id", "name", "partner_id", "date_order", "quote_ref", "pricelist_id", "payment_term_id", "attn", "user_id", "company_id", "warehouse_id", "is_quotation_template", "woo_order_number", "is_service_woo_order", "order_line"]
    purchase_fields = ["id", "name", "partner_id", "partner_ref", "date_order", "date_approve", "user_id", "company_id", "currency_id", "payment_term_id", "picking_type_id", "notes", "attn", "order_line"]
    all_sales = source.search_read("sale.order", sale_domain, sale_fields, order="date_order asc,id asc")
    template_sales = [record for record in all_sales if record.get("is_quotation_template")]
    sales = [record for record in all_sales if not record.get("is_quotation_template")]
    purchases = source.search_read("purchase.order", purchase_domain, purchase_fields, order="date_order asc,id asc")

    existing_sales = target.search_read("sale.order", [["company_id", "=", COMPANY_ID], ["x_studio_v14_reference_studio", "in", [record["name"] for record in sales]]], ["id", "x_studio_v14_reference_studio"])
    existing_purchases = target.search_read("purchase.order", [["company_id", "=", COMPANY_ID], ["x_studio_v14_reference_studio", "in", [record["name"] for record in purchases]]], ["id", "x_studio_v14_reference_studio"])
    existing_sale_refs = {record["x_studio_v14_reference_studio"] for record in existing_sales}
    existing_purchase_refs = {record["x_studio_v14_reference_studio"] for record in existing_purchases}
    sales = [record for record in sales if record["name"] not in existing_sale_refs]
    purchases = [record for record in purchases if record["name"] not in existing_purchase_refs]

    sale_lines = source.read("sale.order.line", [line_id for order in sales for line_id in order["order_line"]], ["id", "order_id", "sequence", "display_type", "product_id", "name", "product_uom_qty", "product_uom", "price_unit", "discount", "tax_id", "route_id", "purchase_price", "packing_ratio", "base_price", "is_free"])
    purchase_lines = source.read("purchase.order.line", [line_id for order in purchases for line_id in order["order_line"]], ["id", "order_id", "sequence", "display_type", "product_id", "name", "product_qty", "product_uom", "price_unit", "taxes_id", "date_planned"])

    partner_ids = {relation_id(order["partner_id"]) for order in sales + purchases}
    product_ids = {relation_id(line["product_id"]) for line in sale_lines + purchase_lines}
    uom_ids = {relation_id(line.get("product_uom")) for line in sale_lines + purchase_lines}
    user_ids = {relation_id(order.get("user_id")) for order in sales + purchases}
    pricelist_ids = {relation_id(order.get("pricelist_id")) for order in sales}
    payment_term_ids = {relation_id(order.get("payment_term_id")) for order in sales + purchases}
    warehouse_ids = {relation_id(order.get("warehouse_id")) for order in sales}
    picking_type_ids = {relation_id(order.get("picking_type_id")) for order in purchases}
    route_ids = {relation_id(line.get("route_id")) for line in sale_lines}
    tax_ids = {tax_id for line in sale_lines for tax_id in line.get("tax_id", [])} | {tax_id for line in purchase_lines for tax_id in line.get("taxes_id", [])}

    partner_map = mapper.partners(source.read("res.partner", partner_ids, ["id", "name", "display_name", "ref", "vat", "company_id", "is_company", "parent_id", "type", "email", "phone", "street", "street2", "city", "zip"]))
    source_products = source.read("product.product", product_ids, ["id", "name", "display_name", "default_code", "barcode", "company_id", "active", "packing_ratio"])
    product_map = mapper.products(source_products)
    product_code_aliases = {
        'HOTRONIX AUTO OPEN CLAM STX11 [11" x 15"]': '702/H A C 11"x15"/UNIT',
    }
    for source_product in source.read("product.product", product_ids, ["id", "name"]):
        if source_product["id"] in product_map or source_product.get("name") not in product_code_aliases:
            continue
        matches = target.search_read("product.product", [["default_code", "=", product_code_aliases[source_product["name"]]]], ["id", "default_code"])
        if len(matches) == 1:
            product_map[source_product["id"]] = matches[0]["id"]
            mapper.exceptions = [item for item in mapper.exceptions if not (item["scope"] == "product.product" and item["source_id"] == source_product["id"])]
    target_product_ratios = {item["id"]: item.get("packing_ratio") or 0 for item in target.read("product.product", product_map.values(), ["id", "packing_ratio"])}
    for source_product in source_products:
        target_product_id = product_map.get(source_product["id"])
        if target_product_id and abs(float(source_product.get("packing_ratio") or 0) - float(target_product_ratios.get(target_product_id, 0))) > 1e-9:
            mapper.record_exception("product.product", source_product["id"], "packing_ratio", f"v14={source_product.get('packing_ratio') or 0}, v19={target_product_ratios.get(target_product_id, 0)}", "mismatch")
    source_uoms = source.read("uom.uom", uom_ids, ["id", "name"])
    target_uoms = target.search_read("uom.uom", [], ["id", "name"])
    uom_aliases = {"unit": "units"}
    uom_map: dict[int, int] = {}
    for record in source_uoms:
        wanted = uom_aliases.get(str(record["name"]).casefold(), str(record["name"]).casefold())
        exact_matches = [item for item in target_uoms if str(item["name"]) == str(record["name"])]
        matches = exact_matches or [item for item in target_uoms if str(item["name"]).casefold() == wanted]
        if len(matches) == 1:
            uom_map[record["id"]] = matches[0]["id"]
        else:
            mapper.record_exception("uom.uom", record["id"], "name", record["name"], "missing" if not matches else "ambiguous")
    user_map = mapper.by_exact_name("res.users", source.read("res.users", user_ids, ["id", "name"]))
    source_pricelists = source.read("product.pricelist", pricelist_ids, ["id", "name", "company_id", "currency_id"])
    target_pricelists = target.search_read("product.pricelist", [["company_id", "in", [False, COMPANY_ID]]], ["id", "name", "company_id", "currency_id"])
    pricelist_aliases = {"woo wc live pricelist": "woo wc live pricelist (myr)"}
    pricelist_map: dict[int, int] = {}
    for record in source_pricelists:
        wanted = pricelist_aliases.get(str(record["name"]).casefold(), str(record["name"]).casefold())
        matches = [item for item in target_pricelists if str(item["name"]).casefold() == wanted and relation_name(item.get("currency_id")) == relation_name(record.get("currency_id"))]
        if len(matches) == 1:
            pricelist_map[record["id"]] = matches[0]["id"]
        else:
            mapper.record_exception("product.pricelist", record["id"], "name/currency", f"{record['name']} / {relation_name(record.get('currency_id'))}", "missing" if not matches else "ambiguous")
    source_payment_terms = source.read("account.payment.term", payment_term_ids, ["id", "name", "company_id"])
    target_payment_terms = target.search_read("account.payment.term", [], ["id", "name", "company_id", "active"])
    # The original v19 term is translated as "14 Days" in en_GB, while its
    # en_US/API name remains "15 Days". Its due line is maintained at 14 days.
    payment_term_aliases = {"advance payment": "ad", "14 days": "15 days"}
    payment_term_map: dict[int, int] = {}
    for record in source_payment_terms:
        wanted = payment_term_aliases.get(str(record["name"]).casefold(), str(record["name"]).casefold())
        matches = [item for item in target_payment_terms if item.get("active", True) and str(item["name"]).casefold() == wanted and relation_id(item.get("company_id")) in (None, relation_id(record.get("company_id")))]
        if len(matches) == 1:
            payment_term_map[record["id"]] = matches[0]["id"]
        else:
            mapper.record_exception("account.payment.term", record["id"], "name", record["name"], "missing" if not matches else "ambiguous")

    source_warehouses = source.read("stock.warehouse", warehouse_ids, ["id", "name", "code"])
    target_warehouses = search_read_in(target, "stock.warehouse", "code", [record["code"] for record in source_warehouses], ["id", "name", "code"])
    warehouse_by_code = {record["code"]: record["id"] for record in target_warehouses}
    warehouse_map = {record["id"]: warehouse_by_code[record["code"]] for record in source_warehouses if record["code"] in warehouse_by_code}
    for record in source_warehouses:
        if record["id"] not in warehouse_map:
            mapper.record_exception("stock.warehouse", record["id"], "code", record["code"], "missing")

    source_picking_types = source.read("stock.picking.type", picking_type_ids, ["id", "name", "code", "warehouse_id"])
    target_picking_types = target.search_read("stock.picking.type", [["company_id", "=", COMPANY_ID]], ["id", "name", "code", "warehouse_id"])
    target_wh_by_id = {record["id"]: record["code"] for record in target_warehouses}
    picking_map: dict[int, int] = {}
    for record in source_picking_types:
        source_wh_code = next((item["code"] for item in source_warehouses if item["id"] == relation_id(record.get("warehouse_id"))), None)
        matches = [item for item in target_picking_types if item.get("code") == record.get("code") and item.get("name") == record.get("name") and target_wh_by_id.get(relation_id(item.get("warehouse_id"))) == source_wh_code]
        if len(matches) == 1:
            picking_map[record["id"]] = matches[0]["id"]
        else:
            mapper.record_exception("stock.picking.type", record["id"], "name", record.get("name"), "missing" if not matches else "ambiguous")

    source_routes = source.read("stock.location.route", route_ids, ["id", "name"])
    route_map = mapper.by_exact_name("stock.route", source_routes)
    source_taxes = source.read("account.tax", tax_ids, ["id", "name", "type_tax_use", "amount", "amount_type"])
    target_taxes = target.search_read("account.tax", [["company_id", "=", COMPANY_ID]], ["id", "name", "type_tax_use", "amount", "amount_type"])
    tax_map: dict[int, int] = {}
    for record in source_taxes:
        matches = [item for item in target_taxes if item.get("type_tax_use") == record.get("type_tax_use") and item.get("amount_type") == record.get("amount_type") and abs(float(item.get("amount") or 0) - float(record.get("amount") or 0)) < 1e-9 and str(item.get("name") or "").casefold() == str(record.get("name") or "").casefold()]
        if len(matches) == 1:
            tax_map[record["id"]] = matches[0]["id"]
        else:
            mapper.record_exception("account.tax", record["id"], "name", record.get("name"), "missing" if not matches else "ambiguous")

    dependency_files: list[str] = []
    missing_product_ids = [item["source_id"] for item in mapper.exceptions if item["scope"] == "product.product" and item["reason"] == "missing"]
    if missing_product_ids:
        source_variants = source.read("product.product", missing_product_ids, ["id", "product_tmpl_id"])
        source_templates = source.read("product.template", [relation_id(item["product_tmpl_id"]) for item in source_variants], ["id", "name", "type", "sale_ok", "purchase_ok", "list_price", "standard_price", "uom_id", "categ_id", "company_id", "invoice_policy", "tracking", "barcode", "default_code", "active"])
        category_aliases = {
            "All / Machine / Machine": "Printing Machines / Machine",
            "All / Machine / Paper": "Printing Machines / Paper",
            "All / Machine / License": "Printing Machines / License",
        }
        target_categories = target.search_read("product.category", [["complete_name", "in", list(category_aliases.values())]], ["id", "complete_name"])
        category_by_name = {item["complete_name"]: item["id"] for item in target_categories}
        buy_routes = target.search_read("stock.route", [["name", "=", "Buy"], ["company_id", "=", False]], ["id", "name"])
        buy_route_id = buy_routes[0]["id"] if len(buy_routes) == 1 else None
        headers = ["ID", "Name", "Product Type", "Track Inventory", "Sales", "Purchase", "Sales Price", "Cost", "Unit/Database ID", "Product Category/Database ID", "Company/Database ID", "Invoicing Policy", "Tracking", "Barcode", "Internal Reference", "Routes/Database ID", "Active"]
        rows: list[list[Any]] = []
        for record in source_templates:
            target_category_id = category_by_name.get(category_aliases.get(relation_name(record.get("categ_id")), ""))
            if not target_category_id:
                mapper.record_exception("product.category", relation_id(record.get("categ_id")) or 0, "complete_name", relation_name(record.get("categ_id")), "missing")
            rows.append([
                f"pysb_v14.product_template_{record['id']}", record["name"], "Goods" if record.get("type") == "product" else "Service", record.get("type") == "product", bool(record.get("sale_ok")), bool(record.get("purchase_ok")), record.get("list_price") or 0, record.get("standard_price") or 0, uom_map.get(relation_id(record.get("uom_id"))), target_category_id, COMPANY_ID,
                "Delivered quantities" if record.get("invoice_policy") == "delivery" else "Ordered quantities",
                {"serial": "By Unique Serial Number", "lot": "By Lots", "none": "By Quantity"}.get(record.get("tracking"), "By Quantity"),
                record.get("barcode") or None, record.get("default_code") or None, buy_route_id, bool(record.get("active")),
            ])
        path = args.output_dir / "DEPENDENCY_01_PRODUCTS.xlsx"
        save_rows(path, headers, rows)
        dependency_files.append(str(path))

    missing_term_ids = [item["source_id"] for item in mapper.exceptions if item["scope"] == "account.payment.term" and item["reason"] == "missing"]
    if missing_term_ids:
        terms = source.read("account.payment.term", missing_term_ids, ["id", "name", "line_ids"])
        term_lines = {item["id"]: item for item in source.read("account.payment.term.line", [line_id for term in terms for line_id in term["line_ids"]], ["id", "value", "value_amount", "days", "sequence"])}
        headers = ["ID", "Payment Terms", "Company/Database ID", "Terms/ID", "Terms/Value", "Terms/Due", "Terms/Delay Type", "Terms/Days"]
        rows = []
        for term in terms:
            for index, line_id in enumerate(term["line_ids"]):
                line = term_lines[line_id]
                rows.append([
                    f"pysb_v14.payment_term_{term['id']}" if index == 0 else None, term["name"] if index == 0 else None, False if index == 0 else None,
                    f"pysb_v14.payment_term_line_{line['id']}", "Percent", 100 if line.get("value") == "balance" else line.get("value_amount") or 0, "Days after invoice date", line.get("days") or 0,
                ])
        path = args.output_dir / "DEPENDENCY_02_PAYMENT_TERMS.xlsx"
        save_rows(path, headers, rows)
        dependency_files.append(str(path))

    missing_route_ids = [item["source_id"] for item in mapper.exceptions if item["scope"] == "stock.route" and item["reason"] == "missing"]
    if missing_route_ids:
        routes = source.read("stock.location.route", missing_route_ids, ["id", "name", "rule_ids"])
        source_rules = source.read("stock.rule", [rule_id for route in routes for rule_id in route["rule_ids"]], ["id", "name", "route_id", "location_src_id"])
        source_rule_by_route: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for rule in source_rules:
            source_rule_by_route[relation_id(rule.get("route_id"))].append(rule)
        location_rows = []
        route_location_external_ids: dict[int, str] = {}
        for route in routes:
            final_rules = [rule for rule in source_rule_by_route[route["id"]] if "Consignment" in str(rule.get("name")) and "Customers" in str(rule.get("name"))]
            if len(final_rules) != 1:
                mapper.record_exception("stock.rule", route["id"], "final consignment rule", route["name"], "missing")
                continue
            location_name = relation_name(final_rules[0].get("location_src_id")).split("/", 1)[-1]
            external_id = f"pysb_v14.stock_location_{relation_id(final_rules[0].get('location_src_id'))}"
            route_location_external_ids[route["id"]] = external_id
            location_rows.append([external_id, location_name, 99, "Internal", COMPANY_ID, True])
        location_path = args.output_dir / "DEPENDENCY_03_CONSIGNMENT_LOCATIONS.xlsx"
        save_rows(location_path, ["ID", "Location Name", "Parent Location/Database ID", "Location Type", "Company/Database ID", "Active"], location_rows)
        dependency_files.append(str(location_path))

        standard_locations = target.search_read("stock.location", [["complete_name", "in", ["HQ/Stock", "HQ/Packing Zone", "HQ/Output"]]], ["id", "complete_name"])
        location_by_complete_name = {item["complete_name"]: item["id"] for item in standard_locations}
        target_consignment_locations = target.search_read("stock.location", [["complete_name", "in", [f"Consignment/{row[1]}" for row in location_rows]]], ["id", "complete_name"])
        consignment_location_by_name = {item["complete_name"].split("/", 1)[-1]: item["id"] for item in target_consignment_locations}
        customer_locations = target.search_read("stock.location", [["usage", "=", "customer"], ["name", "=", "Customers"]], ["id", "name"])
        operation_types = target.search_read("stock.picking.type", [["company_id", "=", COMPANY_ID], ["display_name", "in", ["HQ Warehouse: Pick", "HQ Warehouse: Pack", "HQ Warehouse: Delivery Orders", "HQ Warehouse: Consignment"]]], ["id", "display_name"])
        operation_by_name = {item["display_name"]: item["id"] for item in operation_types}
        headers = ["ID", "Route", "Company/Database ID", "Selectable on Sales Order Line", "Applicable on Product", "Applicable on Warehouse", "Rules/ID", "Rules/Name", "Rules/Action", "Rules/Supply Method", "Rules/Source Location/Database ID", "Rules/Destination Location/Database ID", "Rules/Operation Type/Database ID", "Rules/Company/Database ID", "Rules/Sequence", "Rules/Active", "Rules/Automatic Move", "Rules/Cancel Next Move"]
        rows = []
        rule_specs = [
            ("KL: Stock → Packing Zone", "Take From Stock", "HQ/Stock", None, "HQ/Packing Zone", None, "HQ Warehouse: Pick"),
            ("KL: Packing Zone → Output", "Trigger Another Rule", "HQ/Packing Zone", None, "HQ/Output", None, "HQ Warehouse: Pack"),
            ("KL: Output → Consignment", "Trigger Another Rule", "HQ/Output", None, None, "consignment", "HQ Warehouse: Delivery Orders"),
            ("KL: Consignment→ Customers", "Trigger Another Rule", None, "consignment", "Customers", None, "HQ Warehouse: Consignment"),
        ]
        for route in routes:
            for index, (rule_name, supply_method, src_name, src_external, dest_name, dest_external, operation_name) in enumerate(rule_specs):
                final_rule = next((rule for rule in source_rule_by_route[route["id"]] if "Consignment" in str(rule.get("name")) and "Customers" in str(rule.get("name"))), None)
                consignment_name = relation_name(final_rule.get("location_src_id")).split("/", 1)[-1] if final_rule else None
                consignment_database_id = consignment_location_by_name.get(consignment_name)
                rows.append([
                    f"pysb_v14.stock_route_{route['id']}" if index == 0 else None, route["name"] if index == 0 else None, COMPANY_ID if index == 0 else None, True if index == 0 else None, False if index == 0 else None, False if index == 0 else None,
                    f"pysb_v14.stock_rule_{route['id']}_{index + 1}", rule_name, "Pull From", supply_method,
                    consignment_database_id if src_external else (location_by_complete_name.get(src_name) if src_name else None),
                    consignment_database_id if dest_external else ((customer_locations[0]["id"] if dest_name == "Customers" and len(customer_locations) == 1 else location_by_complete_name.get(dest_name)) if dest_name else None),
                    operation_by_name.get(operation_name), COMPANY_ID, 20, True, "Manual Operation", False,
                ])
        route_path = args.output_dir / "DEPENDENCY_04_CONSIGNMENT_ROUTES.xlsx"
        save_rows(route_path, headers, rows)
        dependency_files.append(str(route_path))

    sale_lines_by_order: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for line in sale_lines:
        sale_lines_by_order[relation_id(line["order_id"])].append(line)
    purchase_lines_by_order: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for line in purchase_lines:
        purchase_lines_by_order[relation_id(line["order_id"])].append(line)

    def mapped(mapping: dict[int, int], value: Any) -> int | None:
        source_id = relation_id(value)
        return mapping.get(source_id) if source_id else None

    sale_headers = ["ID", "v14 Reference (studio)", "Customer/Database ID", "Order Date", "Date Reference v14 (Studio)", "Quote Ref v14 (Studio)", "Pricelist/Database ID", "Payment Terms/Database ID", "Attn", "Salesperson/Database ID", "Company/Database ID", "Warehouse/Database ID", "Order Lines/ID", "Order Lines/Display Type", "Order Lines/Product/Database ID", "Order Lines/Description", "Order Lines/Product Qty", "Order Lines/Sample", "Order Lines/Base Price", "Order Lines/Unit Price", "Order Lines/Unit/Database ID", "Order Lines/Discount (%)", "Order Lines/Routes/Database ID", "Order Lines/Cost", "Order Lines/Taxes/Database ID", "Woo Order Reference", "Is Service Woo Order"]
    sale_rows_by_order: list[tuple[dict[str, Any], list[list[Any]]]] = []
    for order in sales:
        rows: list[list[Any]] = []
        for index, line in enumerate(sorted(sale_lines_by_order[order["id"]], key=lambda item: (item.get("sequence", 0), item["id"]))):
            first = index == 0
            rows.append([
                f"pysb_v14.sale_order_{order['id']}" if first else None,
                order["name"] if first else None,
                mapped(partner_map, order["partner_id"]) if first else None,
                excel_datetime(order["date_order"]) if first else None,
                excel_datetime(order["date_order"]) if first else None,
                order.get("quote_ref") or None if first else None,
                mapped(pricelist_map, order.get("pricelist_id")) if first else None,
                mapped(payment_term_map, order.get("payment_term_id")) if first else None,
                order.get("attn") or None if first else None,
                mapped(user_map, order.get("user_id")) if first else None,
                COMPANY_ID if first else None,
                mapped(warehouse_map, order.get("warehouse_id")) if first else None,
                f"pysb_v14.sale_order_line_{line['id']}", display_type(line.get("display_type")), mapped(product_map, line.get("product_id")), line.get("name"), line.get("product_uom_qty") or 0, bool(line.get("is_free")), line.get("base_price") or 0, line.get("price_unit") or 0, mapped(uom_map, line.get("product_uom")), line.get("discount") or 0, mapped(route_map, line.get("route_id")), line.get("purchase_price") or 0, ",".join(str(tax_map[tax_id]) for tax_id in line.get("tax_id", []) if tax_id in tax_map) or None,
                order.get("woo_order_number") or None if first else None, bool(order.get("is_service_woo_order")) if first else None,
            ])
        sale_rows_by_order.append((order, rows))

    sale_files: list[str] = []
    for batch_no, batch in enumerate(chunks(sale_rows_by_order, SO_BATCH_SIZE), start=1):
        rows = [row for _order, order_rows in batch for row in order_rows]
        path = args.output_dir / f"PYSB_SO_JULY_2026_IMPORT_{batch_no:02d}.xlsx"
        save_rows(path, sale_headers, rows)
        sale_files.append(str(path))

    purchase_headers = ["ID", "v14 Reference (studio)", "Date Ref v14 (Studio)", "Vendor/Database ID", "Vendor Reference", "Order Deadline", "Buyer/Database ID", "Company/Database ID", "Currency", "Payment Terms/Database ID", "Deliver To/Database ID", "Terms and Conditions", "Order Lines/ID", "Order Lines/Display Type", "Order Lines/Product/Database ID", "Order Lines/Description", "Order Lines/Quantity", "Order Lines/Unit/Database ID", "Order Lines/Expected Arrival", "Order Lines/Unit Price", "Order Lines/Discount (%)", "Order Lines/Taxes/Database ID"]
    purchase_rows: list[list[Any]] = []
    for order in purchases:
        for index, line in enumerate(sorted(purchase_lines_by_order[order["id"]], key=lambda item: (item.get("sequence", 0), item["id"]))):
            first = index == 0
            purchase_rows.append([
                f"pysb_v14.purchase_order_{order['id']}" if first else None, order["name"] if first else None, excel_datetime(order.get("date_approve") or order["date_order"]) if first else None, mapped(partner_map, order["partner_id"]) if first else None, order.get("partner_ref") or None if first else None, excel_datetime(order["date_order"]) if first else None, mapped(user_map, order.get("user_id")) if first else None, COMPANY_ID if first else None, relation_name(order.get("currency_id")) if first else None, mapped(payment_term_map, order.get("payment_term_id")) if first else None, mapped(picking_map, order.get("picking_type_id")) if first else None, ((f"Attn: {order['attn']}\n\n" if order.get("attn") else "") + (order.get("notes") or "")) or None if first else None,
                f"pysb_v14.purchase_order_line_{line['id']}", display_type(line.get("display_type")), mapped(product_map, line.get("product_id")), line.get("name"), line.get("product_qty") or 0, mapped(uom_map, line.get("product_uom")), excel_datetime(line.get("date_planned")), line.get("price_unit") or 0, line.get("discount") or 0, ",".join(str(tax_map[tax_id]) for tax_id in line.get("taxes_id", []) if tax_id in tax_map) or None,
            ])
    purchase_path = args.output_dir / "PYSB_PO_JULY_2026_IMPORT_01.xlsx"
    save_rows(purchase_path, purchase_headers, purchase_rows)

    audit_path = args.output_dir / "PYSB_SO_PO_JULY_2026_PREFLIGHT.xlsx"
    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"
    summary.append(["Metric", "Value"])
    metrics = {
        "Source confirmed SO": len(all_sales), "Excluded quotation templates": len(template_sales), "Existing SO skipped": len(existing_sale_refs), "SO ready": len(sales), "SO lines": len(sale_lines),
        "Source confirmed PO": len(purchases) + len(existing_purchase_refs), "Existing PO skipped": len(existing_purchase_refs), "PO ready": len(purchases), "PO lines": len(purchase_lines), "Preflight exceptions": len(mapper.exceptions),
    }
    for key, value in metrics.items():
        summary.append([key, value])
    summary.append(["SO files", json.dumps(sale_files)])
    summary.append(["PO file", str(purchase_path)])
    summary.append(["Dependency files", json.dumps(dependency_files)])
    style(summary)
    for title, records, fields in (
        ("Excluded SO Templates", template_sales, ["id", "name", "date_order", "partner_id"]),
        ("SO Scope", sales, ["id", "name", "date_order", "partner_id", "warehouse_id"]),
        ("PO Scope", purchases, ["id", "name", "date_order", "partner_id", "picking_type_id"]),
    ):
        ws = wb.create_sheet(title)
        ws.append(fields)
        for record in records:
            ws.append([relation_name(record.get(field)) if isinstance(record.get(field), (list, tuple)) else record.get(field) for field in fields])
        style(ws)
    ws = wb.create_sheet("Exceptions")
    ws.append(["scope", "source_id", "field", "value", "reason"])
    for exception in mapper.exceptions:
        ws.append([exception[key] for key in ["scope", "source_id", "field", "value", "reason"]])
    style(ws)
    ws = wb.create_sheet("Warehouse Route Counts")
    ws.append(["Type", "Value", "Line or order count"])
    for value, count in Counter(relation_name(order.get("warehouse_id")) for order in sales).items():
        ws.append(["Warehouse", value, count])
    for value, count in Counter(relation_name(line.get("route_id")) or "(blank)" for line in sale_lines).items():
        ws.append(["Route", value, count])
    for value, count in Counter(relation_name(order.get("picking_type_id")) for order in purchases).items():
        ws.append(["PO Deliver To", value, count])
    style(ws)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(audit_path)

    print(json.dumps({**metrics, "audit": str(audit_path), "dependency_files": dependency_files, "so_files": sale_files, "po_file": str(purchase_path)}, indent=2))
    if mapper.exceptions:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
