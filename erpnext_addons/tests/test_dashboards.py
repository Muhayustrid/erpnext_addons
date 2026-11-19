"""Dashboard cards for forward links; no site needed."""

import unittest
from types import SimpleNamespace
from unittest import mock

from erpnext_addons.tests.fakes import ensure_frappe_importable

ensure_frappe_importable()

from erpnext_addons import dashboards


class Doc(dict):
	__getattr__ = dict.get


def base_data():
	return {
		"transactions": [{"label": "Related", "items": ["Purchase Invoice"]}],
		"internal_links": {},
	}


class TestDashboardData(unittest.TestCase):
	def test_purchase_receipt_adds_delivery_note_to_related(self):
		data = base_data()
		dashboards.purchase_receipt(data)
		group = next(g for g in data["transactions"] if g["label"] == "Related")
		self.assertIn("Delivery Note", group["items"])
		self.assertEqual(data["internal_links"]["Delivery Note"], "inter_company_reference")
		self.assertEqual(data["method"], "erpnext_addons.dashboards.get_open_count")

	def test_adding_twice_does_not_duplicate(self):
		data = base_data()
		dashboards.purchase_receipt(data)
		dashboards.purchase_receipt(data)
		group = next(g for g in data["transactions"] if g["label"] == "Related")
		self.assertEqual(group["items"].count("Delivery Note"), 1)

	def test_purchase_order_keeps_native_internal_link(self):
		data = {
			"transactions": [{"label": "Related", "items": ["Sales Order"]}],
			"internal_links": {"Sales Order": ["items", "sales_order"]},
		}
		dashboards.purchase_order(data)
		self.assertEqual(data["internal_links"]["Sales Order"], ["items", "sales_order"])
		self.assertEqual(data["transactions"][0]["items"].count("Sales Order"), 1)

	def test_stock_entry_adds_three_groups(self):
		data = {
			"transactions": [{"label": "Stock Reservation", "items": ["Stock Reservation Entry"]}],
			"internal_links": {},
		}
		dashboards.stock_entry(data)
		groups = {g["label"]: g["items"] for g in data["transactions"]}
		self.assertEqual(
			groups["Related"],
			["Work Order", "Job Card", "Pick List", "Material Request", "Quality Inspection"],
		)
		self.assertEqual(groups["Reference"], ["BOM", "Project", "Asset Repair"])
		self.assertEqual(
			groups["Transactions"],
			[
				"Stock Entry",
				"Purchase Order",
				"Subcontracting Order",
				"Subcontracting Inward Order",
				"Purchase Receipt",
				"Delivery Note",
				"Sales Invoice",
			],
		)
		self.assertEqual(groups["Accounting"], ["Journal Entry"])
		self.assertEqual(groups["Stock Reservation"], ["Stock Reservation Entry"])
		self.assertEqual(data["internal_links"]["Material Request"], ("items", "material_request"))

	def test_payment_entry_adds_reference_doctypes(self):
		data = {"transactions": [], "internal_links": {}}
		dashboards.payment_entry(data)
		self.assertEqual([g["label"] for g in data["transactions"]], ["Related"])
		self.assertEqual(
			data["transactions"][0]["items"],
			["Sales Invoice", "Purchase Invoice", "Sales Order", "Purchase Order", "Journal Entry"],
		)
		self.assertEqual(data["internal_links"]["Purchase Invoice"], ("references", "reference_name"))
		self.assertEqual(data["fieldname"], "name")


class TestNames(unittest.TestCase):
	def test_header_and_item_links_dedupe_in_order(self):
		doc = Doc(
			inter_company_reference="DN-1",
			items=[
				{"material_request": "MR-1"},
				{"material_request": "MR-1"},
				{"material_request": ""},
			],
		)
		self.assertEqual(
			dashboards._names(doc, "Material Request", (("items", "material_request"),)),
			["MR-1"],
		)
		self.assertEqual(
			dashboards._names(doc, "Delivery Note", ("inter_company_reference",)),
			["DN-1"],
		)

	def test_payment_entry_references_are_filtered_by_type(self):
		doc = Doc(
			references=[
				{"reference_doctype": "Purchase Invoice", "reference_name": "PI-1"},
				{"reference_doctype": "Journal Entry", "reference_name": "JE-1"},
				{"reference_doctype": "Purchase Invoice", "reference_name": "PI-1"},
			]
		)
		self.assertEqual(dashboards._names(doc, "Purchase Invoice", "references"), ["PI-1"])
		self.assertEqual(dashboards._names(doc, "Sales Invoice", "references"), [])


class TestOpenCount(unittest.TestCase):
	def test_custom_items_use_doc_names_and_native_items_are_delegated(self):
		doc = Doc(inter_company_reference="DN-1")
		native = {
			"count": {
				"internal_links_found": [],
				"external_links_found": [
					{"doctype": "Purchase Order", "count": 2, "open_count": 0}
				],
			}
		}
		with (
			mock.patch.object(
				dashboards, "frappe", SimpleNamespace(get_lazy_doc=lambda *a, **k: doc)
			),
			mock.patch.object(dashboards, "_native_open_count", return_value=native) as native_count,
		):
			out = dashboards.get_open_count(
				"Purchase Receipt", "PR-1", ["Delivery Note", "Purchase Order"]
			)

		native_count.assert_called_once_with("Purchase Receipt", "PR-1", ["Purchase Order"])
		self.assertEqual(
			out["count"]["internal_links_found"],
			[{"doctype": "Delivery Note", "open_count": 0, "count": 1, "names": ["DN-1"]}],
		)
		self.assertEqual(out["count"]["external_links_found"], native["count"]["external_links_found"])

	def test_empty_custom_link_is_still_returned_for_native_zero_state(self):
		doc = Doc()
		with (
			mock.patch.object(
				dashboards, "frappe", SimpleNamespace(get_lazy_doc=lambda *a, **k: doc)
			),
			mock.patch.object(dashboards, "_native_open_count", return_value={"count": []}),
		):
			out = dashboards.get_open_count("Purchase Receipt", "PR-1", ["Delivery Note"])

		self.assertEqual(
			out["count"],
			{
				"internal_links_found": [
					{"doctype": "Delivery Note", "open_count": 0, "count": 0, "names": []}
				],
				"external_links_found": [],
			},
		)


if __name__ == "__main__":
	unittest.main()
