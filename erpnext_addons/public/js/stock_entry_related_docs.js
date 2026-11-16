/**
 * Stock Entry related documents
 *
 * Adds a "Dokumen Terkait" card to the Connections tab listing the documents
 * this Stock Entry already links to, including the Material Requests its items
 * came from.
 */

(function (root, factory) {
	if (typeof module === "object" && module.exports) {
		module.exports = factory();
	} else {
		root.stock_entry_related_docs = factory();
	}
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
	"use strict";

	const HEADER_LINKS = {
		work_order: "Work Order",
		job_card: "Job Card",
		pick_list: "Pick List",
		source_stock_entry: "Stock Entry",
		outgoing_stock_entry: "Stock Entry",
		purchase_order: "Purchase Order",
		subcontracting_order: "Subcontracting Order",
		purchase_receipt_no: "Purchase Receipt",
		delivery_note_no: "Delivery Note",
		sales_invoice_no: "Sales Invoice",
	};

	function collect_related_docs(doc) {
		const found = [];
		const seen = new Set();

		const add = (doctype, name) => {
			const key = `${doctype}|${name}`;
			if (!name || seen.has(key)) return;
			seen.add(key);
			found.push({ doctype, name });
		};

		for (const [fieldname, doctype] of Object.entries(HEADER_LINKS)) {
			add(doctype, doc[fieldname]);
		}
		for (const item of doc.items || []) {
			add("Material Request", item.material_request);
		}

		return found;
	}

	function render_related_docs(frm) {
		if (frm.is_new()) return;

		const docs = collect_related_docs(frm.doc).filter((d) =>
			frappe.model.can_read(d.doctype)
		);
		if (!docs.length) return;

		const html = docs
			.map((d) => frappe.utils.get_form_link(d.doctype, d.name, true))
			.join("<br>");
		frm.dashboard.add_section(html, __("Dokumen Terkait"));
	}

	function init() {
		if (typeof frappe === "undefined" || !frappe.ui || !frappe.ui.form) {
			return false;
		}

		// dashboard.reset() drops every .custom section before refresh, so this never duplicates
		frappe.ui.form.on("Stock Entry", { refresh: render_related_docs });
		return true;
	}

	init();

	return { collect_related_docs, render_related_docs, init };
});
