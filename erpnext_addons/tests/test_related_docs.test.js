const test = require("node:test");
const assert = require("node:assert/strict");

const MODULE = "../public/js/related_docs.js";

function load({ unreadable = [] } = {}) {
	const handlers = {};
	const registered = [];
	const sections = [];

	global.__ = (s) => s;
	global.frappe = {
		ui: {
			form: {
				on: (doctype, handler) => {
					registered.push(doctype);
					handlers[doctype] = handler;
				},
			},
		},
		model: { can_read: (doctype) => !unreadable.includes(doctype) },
		utils: {
			// same shape as frappe.utils.get_form_link(doctype, name, true)
			get_form_link: (doctype, name, html) => {
				const route = `/desk/${doctype.toLowerCase().replace(/ /g, "-")}/${name}`;
				return html ? `<a href="${route}">${name}</a>` : route;
			},
		},
	};

	delete require.cache[require.resolve(MODULE)];
	const mod = require(MODULE);

	const frm = {
		doc: {},
		is_new: () => Boolean(frm.doc.__islocal),
		dashboard: { add_section: (html, label) => sections.push({ html, label }) },
	};
	return { mod, handlers, registered, sections, frm };
}

test("Stock Entry maps header links to their doctypes", () => {
	const { mod } = load();

	const docs = mod.collect_related_docs({
		doctype: "Stock Entry",
		work_order: "WO-1",
		subcontracting_order: "SCO-1",
		purchase_receipt_no: "PR-1",
		outgoing_stock_entry: "STE-2",
	});

	assert.deepEqual(docs, [
		{ doctype: "Work Order", name: "WO-1" },
		{ doctype: "Stock Entry", name: "STE-2" },
		{ doctype: "Subcontracting Order", name: "SCO-1" },
		{ doctype: "Purchase Receipt", name: "PR-1" },
	]);
});

test("dedupes the same Material Request across items", () => {
	const { mod } = load();

	const docs = mod.collect_related_docs({
		doctype: "Stock Entry",
		items: [
			{ material_request: "MREQ-1" },
			{ material_request: "MREQ-1" },
			{ material_request: "" },
		],
	});

	assert.deepEqual(docs, [{ doctype: "Material Request", name: "MREQ-1" }]);
});

test("Stock Entry maps BOM, project, accounting, and item-level links", () => {
	const { mod } = load();

	const docs = mod.collect_related_docs({
		doctype: "Stock Entry",
		amended_from: "STE-OLD",
		subcontracting_inward_order: "SIO-1",
		bom_no: "BOM-1",
		project: "PROJ-1",
		credit_note: "JE-1",
		asset_repair: "AR-1",
		items: [
			{
				bom_no: "BOM-1",
				project: "PROJ-1",
				reference_purchase_receipt: "PR-1",
				against_stock_entry: "STE-SRC",
				quality_inspection: "QI-1",
			},
		],
	});

	assert.deepEqual(docs, [
		{ doctype: "Stock Entry", name: "STE-OLD" },
		{ doctype: "Subcontracting Inward Order", name: "SIO-1" },
		{ doctype: "BOM", name: "BOM-1" },
		{ doctype: "Project", name: "PROJ-1" },
		{ doctype: "Journal Entry", name: "JE-1" },
		{ doctype: "Asset Repair", name: "AR-1" },
		{ doctype: "Purchase Receipt", name: "PR-1" },
		{ doctype: "Stock Entry", name: "STE-SRC" },
		{ doctype: "Quality Inspection", name: "QI-1" },
	]);
});

test("Purchase Receipt links its intercompany Delivery Note", () => {
	const { mod } = load();

	const docs = mod.collect_related_docs({
		doctype: "Purchase Receipt",
		inter_company_reference: "DN-1",
	});

	assert.deepEqual(docs, [{ doctype: "Delivery Note", name: "DN-1" }]);
});

test("Purchase Order links its intercompany Sales Order", () => {
	const { mod } = load();

	const docs = mod.collect_related_docs({
		doctype: "Purchase Order",
		inter_company_order_reference: "SO-1",
	});

	assert.deepEqual(docs, [{ doctype: "Sales Order", name: "SO-1" }]);
});

test("Purchase Invoice links its intercompany Sales Invoice", () => {
	const { mod } = load();

	const docs = mod.collect_related_docs({
		doctype: "Purchase Invoice",
		inter_company_invoice_reference: "SINV-1",
	});

	assert.deepEqual(docs, [{ doctype: "Sales Invoice", name: "SINV-1" }]);
});

test("Payment Entry links every document in its reference table", () => {
	const { mod } = load();

	const docs = mod.collect_related_docs({
		doctype: "Payment Entry",
		references: [
			{ reference_doctype: "Purchase Invoice", reference_name: "PI-1" },
			{ reference_doctype: "Purchase Invoice", reference_name: "PI-1" },
			{ reference_doctype: "Journal Entry", reference_name: "JE-1" },
			{ reference_doctype: "Purchase Invoice", reference_name: "" },
		],
	});

	assert.deepEqual(docs, [
		{ doctype: "Purchase Invoice", name: "PI-1" },
		{ doctype: "Journal Entry", name: "JE-1" },
	]);
});

test("doctypes with native connections get no extra card", () => {
	const { mod, sections, frm } = load();

	frm.doc = {
		doctype: "Sales Order",
		inter_company_order_reference: "PO-1",
	};
	mod.render_related_docs(frm);

	assert.deepEqual(sections, []);
});

test("init registers a refresh handler for every supported doctype", () => {
	const { handlers } = load();

	assert.deepEqual(Object.keys(handlers).sort(), [
		"Payment Entry",
		"Purchase Invoice",
		"Purchase Order",
		"Purchase Receipt",
		"Stock Entry",
	]);
});

test("init registers handlers only once per page", () => {
	const { mod, registered } = load();

	assert.equal(registered.length, 5);
	mod.init();
	assert.equal(registered.length, 5);
});

test("empty document yields no cards", () => {
	const { mod, sections, frm } = load();

	assert.deepEqual(mod.collect_related_docs({ doctype: "Purchase Receipt" }), []);
	mod.render_related_docs(frm);
	assert.deepEqual(sections, []);
});

test("render skips doctypes the user cannot read", () => {
	const { handlers, sections, frm } = load({ unreadable: ["Delivery Note"] });

	frm.doc = {
		doctype: "Purchase Receipt",
		inter_company_reference: "DN-1",
	};
	handlers["Purchase Receipt"].refresh(frm);

	assert.deepEqual(sections, []);
});

test("render writes one related-docs card", () => {
	const { handlers, sections, frm } = load();

	frm.doc = {
		doctype: "Purchase Order",
		inter_company_order_reference: "SO-1",
	};
	handlers["Purchase Order"].refresh(frm);

	assert.equal(sections.length, 1);
	assert.equal(sections[0].label, "Dokumen Terkait");
	assert.match(sections[0].html, /SO-1/);
});
