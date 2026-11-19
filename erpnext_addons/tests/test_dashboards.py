"""Dashboard cards for intercompany chains; no site needed."""

import unittest
from types import SimpleNamespace
from unittest import mock

from erpnext_addons.tests.fakes import ensure_frappe_importable

ensure_frappe_importable()

from erpnext_addons import dashboards


class Doc(dict):
	__getattr__ = dict.get


CHAIN_FUNCS = {
	"Purchase Order": dashboards.purchase_order,
	"Sales Order": dashboards.sales_order,
	"Delivery Note": dashboards.delivery_note,
	"Purchase Receipt": dashboards.purchase_receipt,
	"Sales Invoice": dashboards.sales_invoice,
	"Purchase Invoice": dashboards.purchase_invoice,
}


class TestChainDashboard(unittest.TestCase):
	def test_every_chain_doctype_gets_the_other_chain_members_and_payment(self):
		for doctype, add_group in CHAIN_FUNCS.items():
			with self.subTest(doctype=doctype):
				data = {
					"transactions": [
						{
							"label": "Native",
							"items": [*dashboards.CHAIN_DOCTYPES, "Payment Entry", "Other"],
						}
					],
					"internal_links": {"Sales Order": ["items", "sales_order"]},
				}
				add_group(data)

				group = data["transactions"][0]
				self.assertEqual(group["label"], dashboards.GROUP)
				self.assertEqual(
					group["items"],
					[dt for dt in dashboards.CHAIN_DOCTYPES if dt != doctype]
					+ ["Payment Entry"],
				)
				self.assertEqual(data["transactions"][1]["items"], [doctype, "Other"])
				self.assertTrue(data["internal_links"]["Sales Order"])
				self.assertIs(data["internal_links"]["Payment Entry"], True)
				self.assertEqual(data["method"], "erpnext_addons.dashboards.get_open_count")

	def test_group_is_not_added_twice(self):
		data = {"transactions": [], "internal_links": {}}
		dashboards.purchase_order(data)
		dashboards.purchase_order(data)
		self.assertEqual(
			[group["label"] for group in data["transactions"]].count(dashboards.GROUP), 1
		)


class TestLinkGroups(unittest.TestCase):
	def test_stock_entry_adds_native_groups(self):
		data = {
			"transactions": [{"label": "Stock Reservation", "items": ["Stock Reservation Entry"]}],
			"internal_links": {},
		}
		dashboards.stock_entry(data)
		groups = {group["label"]: group["items"] for group in data["transactions"]}
		self.assertEqual(
			groups["Dokumen Terkait"],
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
		self.assertEqual([group["label"] for group in data["transactions"]], ["Dokumen Terkait"])
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
	def test_chain_names_and_payments_are_returned_native_items_delegated(self):
		members = {
			("Purchase Order", "PO-1"): {},
			("Sales Order", "SO-1"): {},
			("Delivery Note", "DN-1"): {},
			("Purchase Receipt", "PR-1"): {},
		}
		native = {
			"count": {
				"internal_links_found": [],
				"external_links_found": [{"doctype": "Project", "count": 3, "open_count": 0}],
			}
		}
		with (
			mock.patch.object(
				dashboards,
				"frappe",
				SimpleNamespace(
					get_lazy_doc=lambda *a, **k: object(),
					get_all=lambda *a, **k: [],
				),
			),
			mock.patch.object(dashboards, "_chain_members", return_value=members),
			mock.patch.object(dashboards, "_payment_names", return_value=["PE-1"]),
			mock.patch.object(dashboards, "_native_open_count", return_value=native) as native_count,
		):
			out = dashboards.get_open_count(
				"Purchase Order",
				"PO-1",
				[
					"Sales Order",
					"Delivery Note",
					"Purchase Receipt",
					"Sales Invoice",
					"Purchase Invoice",
					"Payment Entry",
					"Project",
				],
			)

		native_count.assert_called_once_with("Purchase Order", "PO-1", ["Project"])
		found = {entry["doctype"]: entry for entry in out["count"]["internal_links_found"]}
		self.assertEqual(found["Sales Order"]["names"], ["SO-1"])
		self.assertEqual(found["Delivery Note"]["names"], ["DN-1"])
		self.assertEqual(found["Purchase Receipt"]["names"], ["PR-1"])
		self.assertEqual(found["Sales Invoice"]["count"], 0)
		self.assertEqual(found["Purchase Invoice"]["count"], 0)
		self.assertEqual(found["Payment Entry"]["names"], ["PE-1"])
		self.assertEqual(out["count"]["external_links_found"], native["count"]["external_links_found"])

	def test_amended_originals_are_included(self):
		members = {
			("Purchase Order", "PO-1"): {},
			("Purchase Receipt", "PR-1"): {},
		}
		fake = SimpleNamespace(
			get_lazy_doc=lambda *a, **k: object(),
			get_all=lambda doctype, **kwargs: (
				[SimpleNamespace(amended_from="PR-OLD")]
				if doctype == "Purchase Receipt"
				else []
			),
		)
		with (
			mock.patch.object(dashboards, "frappe", fake),
			mock.patch.object(dashboards, "_chain_members", return_value=members),
			mock.patch.object(dashboards, "_direct_names", return_value={}),
			mock.patch.object(dashboards, "_payment_names", return_value=[]),
			mock.patch.object(
				dashboards,
				"_native_open_count",
				return_value={"count": {"internal_links_found": [], "external_links_found": []}},
			),
		):
			out = dashboards.get_open_count(
				"Purchase Order", "PO-1", ["Purchase Receipt"]
			)

		found = {entry["doctype"]: entry for entry in out["count"]["internal_links_found"]}
		self.assertEqual(found["Purchase Receipt"]["names"], ["PR-1", "PR-OLD"])

	def test_direct_links_survive_without_a_chain(self):
		with (
			mock.patch.object(
				dashboards,
				"frappe",
				SimpleNamespace(
					get_lazy_doc=lambda *a, **k: object(),
					get_all=lambda *a, **k: [],
				),
			),
			mock.patch.object(dashboards, "_chain_members", return_value={}),
			mock.patch.object(
				dashboards,
				"_direct_names",
				return_value={"Purchase Receipt": {"PR-1"}},
			),
			mock.patch.object(
				dashboards, "_payment_names", return_value=["PE-1"]
			) as payment_names,
			mock.patch.object(
				dashboards,
				"_native_open_count",
				return_value={"count": {"internal_links_found": [], "external_links_found": []}},
			),
		):
			out = dashboards.get_open_count(
				"Purchase Order", "PO-1", ["Purchase Receipt", "Payment Entry"]
			)

		payment_names.assert_called_once_with(
			{("Purchase Order", "PO-1"), ("Purchase Receipt", "PR-1")}
		)
		found = {entry["doctype"]: entry for entry in out["count"]["internal_links_found"]}
		self.assertEqual(found["Purchase Receipt"]["names"], ["PR-1"])
		self.assertEqual(found["Payment Entry"]["names"], ["PE-1"])

	def test_empty_chain_returns_zero_cards(self):
		with (
			mock.patch.object(
				dashboards,
				"frappe",
				SimpleNamespace(
					get_lazy_doc=lambda *a, **k: object(),
					get_all=lambda *a, **k: [],
				),
			),
			mock.patch.object(
				dashboards,
				"_chain_members",
				return_value={("Purchase Order", "PO-1"): {}},
			),
			mock.patch.object(dashboards, "_payment_names", return_value=[]),
			mock.patch.object(
				dashboards,
				"_native_open_count",
				return_value={"count": {"internal_links_found": [], "external_links_found": []}},
			),
		):
			out = dashboards.get_open_count(
				"Purchase Order", "PO-1", ["Sales Order", "Payment Entry"]
			)

		found = {entry["doctype"]: entry for entry in out["count"]["internal_links_found"]}
		self.assertEqual(found["Sales Order"], {"doctype": "Sales Order", "open_count": 0, "count": 0, "names": []})
		self.assertEqual(found["Payment Entry"]["count"], 0)

	def test_stock_entry_forward_links_are_custom_and_others_delegate(self):
		doc = Doc(work_order="WO-1", bom_no="BOM-1", items=[{"material_request": "MR-1"}])
		native = {"count": {"internal_links_found": [], "external_links_found": []}}
		with (
			mock.patch.object(
				dashboards, "frappe", SimpleNamespace(get_lazy_doc=lambda *a, **k: doc)
			),
			mock.patch.object(dashboards, "_native_open_count", return_value=native) as native_count,
		):
			out = dashboards.get_open_count(
				"Stock Entry",
				"SE-1",
				["Work Order", "Material Request", "BOM", "Stock Reservation Entry"],
			)

		native_count.assert_called_once_with("Stock Entry", "SE-1", ["Stock Reservation Entry"])
		found = {entry["doctype"]: entry for entry in out["count"]["internal_links_found"]}
		self.assertEqual(found["Work Order"]["names"], ["WO-1"])
		self.assertEqual(found["Material Request"]["names"], ["MR-1"])
		self.assertEqual(found["BOM"]["names"], ["BOM-1"])

	def test_payment_entry_references_are_custom(self):
		doc = Doc(
			references=[
				{"reference_doctype": "Purchase Invoice", "reference_name": "PI-1"},
				{"reference_doctype": "Purchase Invoice", "reference_name": "PI-1"},
			]
		)
		with (
			mock.patch.object(
				dashboards, "frappe", SimpleNamespace(get_lazy_doc=lambda *a, **k: doc)
			),
			mock.patch.object(
				dashboards,
				"_native_open_count",
				return_value={"count": {"internal_links_found": [], "external_links_found": []}},
			),
		):
			out = dashboards.get_open_count(
				"Payment Entry", "PE-1", ["Purchase Invoice", "Sales Invoice"]
			)

		found = {entry["doctype"]: entry for entry in out["count"]["internal_links_found"]}
		self.assertEqual(found["Purchase Invoice"]["names"], ["PI-1"])
		self.assertEqual(found["Sales Invoice"]["count"], 0)


if __name__ == "__main__":
	unittest.main()
