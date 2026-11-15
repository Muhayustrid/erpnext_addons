"""Pure intercompany progress calculator (no Frappe needed)."""

import unittest

from erpnext_addons.intercompany.progress import FIELDS, compute

FULL = {"po": 10, "so": 10, "dn": 10, "pr": 10, "si": 10, "pi": 10}
CHECKS = (
	"custom_ic_ordered",
	"custom_ic_delivered",
	"custom_ic_received",
	"custom_ic_sales_invoiced",
	"custom_ic_purchase_invoiced",
)


def step(qty, **kw):
	return compute(qty, **kw)["custom_ic_next_step"]


def checks(qty):
	r = compute(qty)
	return tuple(r[f] for f in CHECKS)


class TestCompute(unittest.TestCase):
	def test_result_has_exactly_the_fields(self):
		self.assertEqual(set(compute({})), set(FIELDS))
		self.assertEqual(FIELDS[:5], CHECKS)

	def test_full_chain_is_completed(self):
		self.assertEqual(step({"A": FULL}), "Completed")
		self.assertEqual(checks({"A": FULL}), (1, 1, 1, 1, 1))

	def test_po_without_so(self):
		self.assertEqual(step({"A": {"po": 10}}), "To Create Sales Order")
		self.assertEqual(checks({"A": {"po": 10}}), (0, 0, 0, 0, 0))

	def test_so_without_po(self):
		self.assertEqual(step({"A": {"so": 10, "dn": 10}}), "To Create Purchase Order")

	def test_split_po_partially_delivered(self):
		r = compute({"A": {"po": 10, "so": 10, "dn": 6}})
		self.assertEqual(r["custom_ic_next_step"], "To Deliver (60%)")
		self.assertEqual((r["custom_ic_ordered"], r["custom_ic_delivered"]), (1, 0))

	def test_percent_is_floored_and_capped_per_item(self):
		self.assertEqual(step({"A": {"po": 3, "so": 3, "dn": 2}}), "To Deliver (66%)")
		# B over-delivered must not hide A being short
		self.assertEqual(
			step({"A": {"po": 10, "so": 10, "dn": 0}, "B": {"po": 10, "so": 10, "dn": 20}}),
			"To Deliver (50%)",
		)

	def test_delivered_but_not_received(self):
		qty = {"A": {"po": 10, "so": 10, "dn": 10}}
		self.assertEqual(step(qty), "To Receive (0%)")
		self.assertEqual(checks(qty), (1, 1, 0, 0, 0))

	def test_sales_return_without_purchase_return(self):
		r = compute({"A": {"po": 10, "so": 10, "dn": 8, "pr": 10, "dn_ret": 2}})
		self.assertEqual(r["custom_ic_next_step"], "To Create Purchase Return")
		self.assertEqual(r["custom_ic_received"], 0)

	def test_matched_returns_go_back_to_delivery(self):
		qty = {"A": {"po": 10, "so": 10, "dn": 8, "pr": 8, "dn_ret": 2, "pr_ret": 2}}
		self.assertEqual(step(qty), "To Deliver (80%)")

	def test_closed_order_still_needs_receipt_and_billing(self):
		# SO closed after delivering 6: delivery requirement drops to 6, receipt and billing remain
		qty = {"A": {"po": 10, "so": 10, "sod": 6, "dn": 6}}
		self.assertEqual(step(qty, closed=True), "To Receive (0%)")
		self.assertEqual(checks(qty)[1], 1)
		done = {"A": {"po": 10, "so": 10, "sod": 6, "dn": 6, "pr": 6, "si": 6, "pi": 6}}
		self.assertEqual(step(done, closed=True), "Closed")

	def test_one_closed_branch_does_not_close_an_open_branch(self):
		# PO 10 split into SO1 6 (closed after delivering 6) and SO2 4 (open, nothing delivered)
		qty = {"A": {"po": 10, "so": 10, "sod": 10, "dn": 6}}
		self.assertEqual(step(qty, closed=True), "To Deliver (60%)")

	def test_closed_po_does_not_ask_for_sales_order(self):
		self.assertEqual(step({"A": {"po": 10, "por": 0}}, closed=True), "Closed")
		self.assertEqual(step({"A": {"po": 10, "por": 4, "so": 4, "dn": 4, "pr": 4, "si": 4, "pi": 4}}, closed=True), "Closed")

	def test_purchase_return_without_sales_return(self):
		self.assertEqual(
			step({"A": {"po": 10, "so": 10, "dn": 10, "pr": 8, "pr_ret": 2}}), "To Create Sales Return"
		)

	def test_received_not_billed(self):
		self.assertEqual(step({"A": {"po": 10, "so": 10, "dn": 10, "pr": 10, "si": 5}}), "To Bill (50%)")

	def test_billed_more_than_delivered_needs_credit_note(self):
		self.assertEqual(step({"A": {"po": 8, "so": 8, "dn": 8, "pr": 8, "si": 10}}), "To Create Credit Note")

	def test_credit_note_without_debit_note(self):
		qty = {"A": {**FULL, "si": 8, "si_ret": 2}}
		self.assertEqual(step(qty), "To Create Debit Note")
		qty = {"A": {"po": 8, "so": 8, "dn": 8, "pr": 8, "si": 8, "si_ret": 2, "pi": 10}}
		self.assertEqual(step(qty), "To Create Debit Note")

	def test_debit_note_without_credit_note(self):
		qty = {"A": {**FULL, "pi": 8, "pi_ret": 2}}
		self.assertEqual(step(qty), "To Create Credit Note")

	def test_sales_invoice_without_purchase_invoice(self):
		qty = {"A": {**FULL, "pi": 0}}
		self.assertEqual(step(qty), "To Create Purchase Invoice")
		self.assertEqual(checks(qty), (1, 1, 1, 1, 0))

	def test_per_item_mismatch_hidden_by_equal_totals(self):
		qty = {"A": {**FULL, "pr": 12}, "B": {**FULL, "pr": 8}}
		self.assertNotEqual(step(qty), "Completed")
		self.assertEqual(checks(qty)[2], 0)

	def test_invoice_amount_must_match(self):
		qty = {"A": {**FULL, "si_amt": 100000, "pi_amt": 90000}}
		self.assertEqual(step(qty), "To Match Invoice Amount")
		self.assertEqual(checks(qty)[4], 0)
		qty = {"A": {**FULL, "si_amt": 100000, "pi_amt": 100000.4}}
		self.assertEqual(step(qty), "Completed")
		self.assertEqual(checks(qty)[4], 1)

	def test_float_tolerance(self):
		self.assertEqual(step({"A": {**FULL, "pi": 10.0004}}), "Completed")

	def test_closed_before_any_delivery(self):
		# SO and PO both closed with nothing delivered: requirements drop to zero
		self.assertEqual(step({"A": {"po": 10, "so": 10, "sod": 0, "por": 0}}, closed=True), "Closed")

	def test_empty_chain_has_no_checks(self):
		self.assertEqual(checks({}), (0, 0, 0, 0, 0))


if __name__ == "__main__":
	unittest.main()
