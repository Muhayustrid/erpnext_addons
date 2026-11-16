"""Amending a submitted Purchase Order with new Material Requests.

Unit classes run anywhere against FakeFrappe. The integration class needs a real
site (`bench run-tests`) and skips otherwise.
"""

import json
import unittest
from contextlib import suppress
from unittest import mock

from erpnext_addons.tests.fakes import FakeFrappe, FakeValidationError, ensure_frappe_importable, new_doc

ensure_frappe_importable()

import frappe

from erpnext_addons.buying import amendment

try:
	from frappe.tests import IntegrationTestCase

	HAS_SITE = bool(getattr(frappe.local, "site", None))
except ImportError:
	IntegrationTestCase, HAS_SITE = unittest.TestCase, False


class AmendBlockerCase(unittest.TestCase):
	def test_passes_submitted_po(self):
		po = new_doc(name="PO-1", docstatus=1, inter_company_order_reference=None)
		self.assertIsNone(amendment.amend_blocker(po))

	def test_refuses_draft_po(self):
		po = new_doc(name="PO-1", docstatus=0, inter_company_order_reference=None)
		self.assertIn("Purchase Order", amendment.amend_blocker(po))

	def test_refuses_intercompany_po(self):
		po = new_doc(name="PO-1", docstatus=1, inter_company_order_reference="PO-2")
		self.assertIn("intercompany", amendment.amend_blocker(po))

	def test_refuses_subcontracted_po(self):
		po = new_doc(name="PO-1", docstatus=1, inter_company_order_reference=None, is_subcontracted=1)
		self.assertIn("subkontrak", amendment.amend_blocker(po))


class AssertCanAmendCase(unittest.TestCase):
	def setUp(self):
		self.f = FakeFrappe()
		p = mock.patch.object(amendment, "frappe", self.f)
		p.start()
		self.addCleanup(p.stop)
		self.po = new_doc(name="PO-1", docstatus=1, inter_company_order_reference=None)

	def assert_refused(self, fragment):
		with self.assertRaises(FakeValidationError) as ctx:
			amendment.assert_can_amend(self.po)
		self.assertIn(fragment, str(ctx.exception))

	def test_refuses_submitted_receipt(self):
		self.f.add("Purchase Receipt Item", "PRI-1", purchase_order="PO-1", docstatus=1)
		self.assert_refused("Purchase Receipt submitted")

	def test_refuses_draft_receipt(self):
		self.f.add("Purchase Receipt Item", "PRI-1", purchase_order="PO-1", docstatus=0)
		self.assert_refused("Purchase Receipt draft")

	def test_refuses_submitted_invoice(self):
		self.f.add("Purchase Invoice Item", "PII-1", purchase_order="PO-1", docstatus=1)
		self.assert_refused("Purchase Invoice submitted")

	def test_refuses_draft_invoice(self):
		self.f.add("Purchase Invoice Item", "PII-1", purchase_order="PO-1", docstatus=0)
		self.assert_refused("Purchase Invoice draft")

	def test_refuses_existing_amendment(self):
		self.f.add("Purchase Order", "PO-2", amended_from="PO-1", docstatus=0)
		self.assert_refused("sudah pernah di-amend")

	def test_refuses_submitted_payment_entry(self):
		self.f.add(
			"Payment Entry Reference",
			"PER-1",
			parent="PE-1",
			reference_doctype="Purchase Order",
			reference_name="PO-1",
			docstatus=1,
		)
		self.assert_refused("Payment Entry PE-1")

	def test_refuses_submitted_journal_entry(self):
		self.f.add(
			"Journal Entry Account",
			"JEA-1",
			parent="JE-1",
			reference_type="Purchase Order",
			reference_name="PO-1",
			docstatus=1,
		)
		self.assert_refused("Journal Entry JE-1")

	def test_passes_cancelled_or_foreign_references(self):
		self.f.add(
			"Payment Entry Reference",
			"PER-1",
			parent="PE-1",
			reference_doctype="Purchase Order",
			reference_name="PO-1",
			docstatus=2,
		)
		self.f.add(
			"Journal Entry Account",
			"JEA-1",
			parent="JE-1",
			reference_type="Purchase Order",
			reference_name="PO-9",
			docstatus=1,
		)
		amendment.assert_can_amend(self.po)

	def test_passes_clean_po(self):
		self.f.add("Purchase Receipt Item", "PRI-1", purchase_order="PO-9", docstatus=1)
		amendment.assert_can_amend(self.po)

	def test_blocked_po_is_refused_without_db_lookup(self):
		self.po.docstatus = 0
		with mock.patch.object(self.f.db, "exists", side_effect=AssertionError("no db read")):
			self.assert_refused("Purchase Order")


class UniqueMaterialRequestsCase(unittest.TestCase):
	def test_empty(self):
		self.assertEqual(amendment.unique_material_requests([]), [])

	def test_drops_repeats_keeping_first_seen_order(self):
		self.assertEqual(amendment.unique_material_requests(["A", "B", "A"]), ["A", "B"])

	def test_drops_empty_values(self):
		self.assertEqual(amendment.unique_material_requests(["", None, "A"]), ["A"])


class MaterialRequestBlockerCase(unittest.TestCase):
	def setUp(self):
		self.po = new_doc(name="PO-1", company="Roti Ropi")

	def mr(self, **values):
		row = {
			"name": "MREQ-1",
			"material_request_type": "Purchase",
			"company": "Roti Ropi",
			"docstatus": 1,
			"status": "Pending",
			"per_ordered": 0,
		}
		row.update(values)
		return row

	def test_passes_orderable_material_request(self):
		self.assertIsNone(amendment.material_request_blocker(self.mr(), self.po))

	def test_refuses_missing_material_request(self):
		self.assertIn("tidak ditemukan", amendment.material_request_blocker(None, self.po))

	def test_refuses_non_purchase_material_request(self):
		self.assertIn(
			"Purchase", amendment.material_request_blocker(self.mr(material_request_type="Material Transfer"), self.po)
		)

	def test_refuses_other_company(self):
		self.assertIn("company lain", amendment.material_request_blocker(self.mr(company="Other"), self.po))

	def test_refuses_draft_material_request(self):
		self.assertIn("belum submitted", amendment.material_request_blocker(self.mr(docstatus=0), self.po))

	def test_refuses_stopped_material_request(self):
		self.assertIn("Stopped", amendment.material_request_blocker(self.mr(status="Stopped"), self.po))

	def test_refuses_fully_ordered_material_request(self):
		self.assertIn("sudah dipesan", amendment.material_request_blocker(self.mr(per_ordered=100), self.po))


class AssertNewMaterialRequestsCase(unittest.TestCase):
	def setUp(self):
		self.f = FakeFrappe()
		p = mock.patch.object(amendment, "frappe", self.f)
		p.start()
		self.addCleanup(p.stop)

	def po_with(self, *material_requests):
		return new_doc(items=[new_doc(material_request=mr) for mr in material_requests])

	def test_passes_disjoint_material_requests(self):
		amendment.assert_new_material_requests(self.po_with("MR-1"), ["MR-2"])

	def test_refuses_material_request_already_on_po(self):
		with self.assertRaises(FakeValidationError) as ctx:
			amendment.assert_new_material_requests(self.po_with("MR-1"), ["MR-2", "MR-1"])
		self.assertIn("MR-1", str(ctx.exception))

	def test_passes_rows_without_material_request(self):
		po = new_doc(items=[new_doc(item_code="ITEM-1", material_request=None)])
		amendment.assert_new_material_requests(po, ["MR-2"])


class CreateAmendmentCase(unittest.TestCase):
	def setUp(self):
		self.f = FakeFrappe()
		p = mock.patch.object(amendment, "frappe", self.f)
		p.start()
		self.addCleanup(p.stop)
		self.f.add("Purchase Order", "PO-1", docstatus=1, inter_company_order_reference=None)

	def test_refuses_empty_material_request_list(self):
		self.f.parse_json = lambda value: []
		with self.assertRaises(FakeValidationError) as ctx:
			amendment.create_amendment_for_material_request("PO-1", "[]")
		self.assertIn("Material Request", str(ctx.exception))

	def test_refuses_material_requests_that_are_not_a_list(self):
		self.f.parse_json = lambda value: {"MREQ-1": True}
		with self.assertRaises(FakeValidationError) as ctx:
			amendment.create_amendment_for_material_request("PO-1", '{"MREQ-1": true}')
		self.assertIn("tidak valid", str(ctx.exception))

	def test_refuses_intercompany_po_before_cancelling(self):
		self.f.parse_json = json.loads
		po = self.f.db.tables["Purchase Order"]["PO-1"]
		po["inter_company_order_reference"] = "PO-2"
		po["cancel"] = mock.Mock()

		with self.assertRaises(FakeValidationError):
			amendment.create_amendment_for_material_request("PO-1", '["MREQ-1"]')

		po["cancel"].assert_not_called()


SUPPLIER = "_Test Supplier PO Amendment"
ITEM = "_Test Item PO Amendment"


@unittest.skipUnless(HAS_SITE, "needs a Frappe site (bench run-tests)")
class AmendmentIntegrationCase(IntegrationTestCase):
	def setUp(self):
		self.company = frappe.defaults.get_global_default("company")
		supplier_group = frappe.db.get_value("Supplier Group", {"is_group": 0}, "name")
		item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
		if not (self.company and supplier_group and item_group):
			self.skipTest("site lacks a company or a leaf supplier/item group")
		self.supplier = self._ensure_supplier(supplier_group)
		self.item = self._ensure_item(item_group)
		self.created = []
		self.addCleanup(self._cleanup)

	# _Test fixtures stay on the site, like the ERPNext test records
	def _ensure_supplier(self, supplier_group):
		if not frappe.db.exists("Supplier", SUPPLIER):
			frappe.get_doc(
				{"doctype": "Supplier", "supplier_name": SUPPLIER, "supplier_group": supplier_group}
			).insert(ignore_permissions=True)
		return SUPPLIER

	def _ensure_item(self, item_group):
		if not frappe.db.exists("Item", ITEM):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": ITEM,
					"item_name": ITEM,
					"item_group": item_group,
					"stock_uom": frappe.db.get_value("UOM", {}, "name") or "Nos",
					"is_stock_item": 1,
					"is_purchase_item": 1,
				}
			).insert(ignore_permissions=True)
		return ITEM

	def _cleanup(self):
		for doctype, name in reversed(self.created):
			with suppress(Exception):
				doc = frappe.get_doc(doctype, name)
				if doc.docstatus == 1:
					doc.cancel()
				frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)

	def _track(self, doc):
		self.created.append((doc.doctype, doc.name))
		return doc

	def _material_request(self, qty):
		mr = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Purchase",
				"company": self.company,
				"items": [
					{
						"item_code": self.item,
						"qty": qty,
						"schedule_date": frappe.utils.add_days(frappe.utils.nowdate(), 7),
					}
				],
			}
		)
		mr.insert()
		mr.submit()
		self._track(mr)
		return mr

	def _purchase_order(self, mr_name, qty=None):
		from erpnext.stock.doctype.material_request.material_request import make_purchase_order

		po = make_purchase_order(mr_name)
		po.supplier = self.supplier
		if qty is not None:
			po.items[0].qty = qty
		po.insert()
		po.submit()
		self._track(po)
		return po

	def test_amendment_merges_pending_qty_of_new_material_request(self):
		mr1 = self._material_request(10)
		po1 = self._purchase_order(mr1.name)

		with self.assertRaises(frappe.ValidationError):
			amendment.create_amendment_for_material_request(po1.name, frappe.as_json([mr1.name]))
		self.assertEqual(frappe.db.get_value("Purchase Order", po1.name, "docstatus"), 1)

		mr2 = self._material_request(10)
		# a second PO orders 4 of mr2, so mr2 still has 6 pending
		self._purchase_order(mr2.name, qty=4)

		new_name = amendment.create_amendment_for_material_request(po1.name, frappe.as_json([mr2.name]))
		new = frappe.get_doc("Purchase Order", new_name)
		self._track(new)

		self.assertEqual(new.docstatus, 0)
		self.assertEqual(new.amended_from, po1.name)
		self.assertEqual(frappe.db.get_value("Purchase Order", po1.name, "docstatus"), 2)

		qty_by_mr = {}
		for row in new.items:
			qty_by_mr[row.material_request] = qty_by_mr.get(row.material_request, 0) + row.qty
		self.assertEqual(qty_by_mr[mr1.name], 10)
		self.assertEqual(qty_by_mr[mr2.name], 6)


if __name__ == "__main__":
	unittest.main()
