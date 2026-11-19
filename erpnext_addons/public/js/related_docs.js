/**
 * Related documents
 *
 * Adds a "Dokumen Terkait" card to the Connections tab for header link fields
 * the native Connections tab cannot show (the current document holds the
 * reference to its counterpart), plus Payment Entry's reference table.
 */

(function (root, factory) {
	if (typeof module === "object" && module.exports) {
		module.exports = factory();
	} else {
		root.related_docs = factory();
	}
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
	"use strict";

	const LINKS = {
		"Stock Entry": {
			header: {
				work_order: "Work Order",
				job_card: "Job Card",
				pick_list: "Pick List",
				source_stock_entry: "Stock Entry",
				outgoing_stock_entry: "Stock Entry",
				amended_from: "Stock Entry",
				purchase_order: "Purchase Order",
				subcontracting_order: "Subcontracting Order",
				subcontracting_inward_order: "Subcontracting Inward Order",
				purchase_receipt_no: "Purchase Receipt",
				delivery_note_no: "Delivery Note",
				sales_invoice_no: "Sales Invoice",
				bom_no: "BOM",
				project: "Project",
				credit_note: "Journal Entry",
				asset_repair: "Asset Repair",
			},
			items: {
				material_request: "Material Request",
				reference_purchase_receipt: "Purchase Receipt",
				against_stock_entry: "Stock Entry",
				quality_inspection: "Quality Inspection",
				project: "Project",
				bom_no: "BOM",
			},
		},
		"Purchase Order": {
			header: { inter_company_order_reference: "Sales Order" },
		},
		"Purchase Receipt": {
			header: { inter_company_reference: "Delivery Note" },
		},
		"Purchase Invoice": {
			header: { inter_company_invoice_reference: "Sales Invoice" },
		},
		"Payment Entry": { references: true },
	};

	function collect_related_docs(doc) {
		const links = LINKS[doc.doctype] || {};
		const found = [];
		const seen = new Set();

		const add = (doctype, name) => {
			const key = `${doctype}|${name}`;
			if (!doctype || !name || seen.has(key)) return;
			seen.add(key);
			found.push({ doctype, name });
		};

		for (const [fieldname, doctype] of Object.entries(links.header || {})) {
			add(doctype, doc[fieldname]);
		}
		for (const [fieldname, doctype] of Object.entries(links.items || {})) {
			for (const item of doc.items || []) {
				add(doctype, item[fieldname]);
			}
		}
		if (links.references) {
			for (const ref of doc.references || []) {
				add(ref.reference_doctype, ref.reference_name);
			}
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
		// this file is inlined per form meta, so guard against re-registering on every form open
		if (frappe.__related_docs_registered) return true;
		frappe.__related_docs_registered = true;

		// dashboard.reset() drops every .custom section before refresh, so this never duplicates
		for (const doctype of Object.keys(LINKS)) {
			frappe.ui.form.on(doctype, { refresh: render_related_docs });
		}
		return true;
	}

	init();

	return { collect_related_docs, render_related_docs, init };
});
