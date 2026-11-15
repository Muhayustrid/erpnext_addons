"""Turn net stock quantities of an intercompany chain into checkboxes and a Next Step.

Pure: no Frappe import. `qty[item_code][key]` holds net stock qty per document kind
(returns are negative in ERPNext, so sums are already net) plus `*_ret` absolute
return quantities used to tell an unmatched return from plain "not yet received/billed".
"""

import math

TOL = 0.001
KEYS = ("po", "so", "dn", "pr", "si", "pi", "dn_ret", "pr_ret", "si_ret", "pi_ret", "si_amt", "pi_amt")
# required order qty after Close: "sod" = delivered part of closed SOs + full open SOs,
# "por" = received part of closed POs + full open POs (missing = full order qty)
REQUIRED = {"sod": "so", "por": "po"}
AMOUNT_TOL = 1.0
FIELDS = (
	"custom_ic_ordered",
	"custom_ic_delivered",
	"custom_ic_received",
	"custom_ic_sales_invoiced",
	"custom_ic_purchase_invoiced",
	"custom_ic_next_step",
)


def compute(qty, closed=False):
	rows = []
	for v in qty.values():
		row = {k: float(v.get(k) or 0) for k in KEYS}
		for req, full in REQUIRED.items():
			row[req] = float(v[req]) if v.get(req) is not None else row[full]
		rows.append(row)

	def total(k):
		return sum(r[k] for r in rows)

	def lt(a, b):
		return any(r[a] < r[b] - TOL for r in rows)

	def gt(a, b):
		return lt(b, a)

	def eq(a, b):
		return not lt(a, b) and not gt(a, b) and total(b) > TOL

	def pct(a, b):
		done = sum(min(max(r[a], 0), r[b]) for r in rows if r[b] > 0)
		return f"{math.floor(100 * done / total(b) + 1e-9)}%" if total(b) > TOL else "0%"

	amount_matched = abs(total("si_amt") - total("pi_amt")) <= AMOUNT_TOL

	result = {
		"custom_ic_ordered": int(eq("po", "so")),
		"custom_ic_delivered": int(total("sod") > TOL and not lt("dn", "sod")),
		"custom_ic_received": int(eq("pr", "dn")),
		"custom_ic_sales_invoiced": int(eq("si", "dn")),
		"custom_ic_purchase_invoiced": int(eq("pi", "si") and amount_matched),
	}
	result["custom_ic_next_step"] = _next_step(rows, closed, lt, gt, pct, amount_matched)
	return result


def _next_step(rows, closed, lt, gt, pct, amount_matched):
	if not rows:
		return ""
	# order matters: missing order side, unmatched returns or excess, then progress.
	# A closed order lowers only its own requirement (sod/por); open branches still count.
	rules = (
		(lt("so", "por"), "To Create Sales Order"),
		(not closed and lt("po", "so"), "To Create Purchase Order"),
		(gt("pr", "dn"), "To Create Purchase Return"),
		(gt("pr_ret", "dn_ret"), "To Create Sales Return"),
		(gt("si", "dn"), "To Create Credit Note"),
		(gt("pi", "si"), "To Create Debit Note"),
		(gt("pi_ret", "si_ret"), "To Create Credit Note"),
		(lt("dn", "sod"), lambda: f"To Deliver ({pct('dn', 'sod')})"),
		(lt("pr", "dn"), lambda: f"To Receive ({pct('pr', 'dn')})"),
		(lt("si", "dn"), lambda: f"To Bill ({pct('si', 'dn')})"),
		(lt("pi", "si"), "To Create Purchase Invoice"),
		(not amount_matched, "To Match Invoice Amount"),
	)
	for hit, label in rules:
		if hit:
			return label() if callable(label) else label
	return "Closed" if closed else "Completed"
