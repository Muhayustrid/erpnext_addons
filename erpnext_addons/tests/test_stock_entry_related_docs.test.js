const test = require("node:test");
const assert = require("node:assert/strict");

const MODULE = "../public/js/stock_entry_related_docs.js";

function load({ unreadable = [] } = {}) {
	const handlers = {};
	const sections = [];

	global.__ = (s) => s;
	global.frappe = {
		ui: { form: { on: (doctype, handler) => (handlers[doctype] = handler) } },
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
	return { mod, handlers, sections, frm };
}

test("maps header links to their doctypes", () => {
	const { mod } = load();

	const docs = mod.collect_related_docs({
		work_order: "WO-1",
		purchase_receipt_no: "PR-1",
		outgoing_stock_entry: "STE-2",
	});

	assert.deepEqual(docs, [
		{ doctype: "Work Order", name: "WO-1" },
		{ doctype: "Stock Entry", name: "STE-2" },
		{ doctype: "Purchase Receipt", name: "PR-1" },
	]);
});

test("dedupes the same Material Request across items", () => {
	const { mod } = load();

	const docs = mod.collect_related_docs({
		items: [
			{ material_request: "MREQ-1" },
			{ material_request: "MREQ-1" },
			{ material_request: "" },
		],
	});

	assert.deepEqual(docs, [{ doctype: "Material Request", name: "MREQ-1" }]);
});

test("empty document yields no cards", () => {
	const { mod, sections, frm } = load();

	assert.deepEqual(mod.collect_related_docs({}), []);
	mod.render_related_docs(frm);
	assert.deepEqual(sections, []);
});

test("render skips doctypes the user cannot read", () => {
	const { mod, handlers, sections, frm } = load({ unreadable: ["Work Order"] });

	frm.doc = { work_order: "WO-1", purchase_receipt_no: "PR-1" };
	handlers["Stock Entry"].refresh(frm);

	assert.equal(sections.length, 1);
	assert.equal(sections[0].label, "Dokumen Terkait");
	assert.match(sections[0].html, /PR-1/);
	assert.doesNotMatch(sections[0].html, /WO-1/);
});
