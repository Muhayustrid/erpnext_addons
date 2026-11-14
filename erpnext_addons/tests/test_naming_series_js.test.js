const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

// Minimal Frappe stub: captures form handlers and serves frappe.db.get_value.
function loadForm(file, doctype, dbValue) {
	const handlers = {};
	const frappe = {
		ui: { form: { on: (dt, h) => (handlers[dt] = h) } },
		db: { get_value: () => Promise.resolve({ message: dbValue }) },
	};
	const code = fs.readFileSync(path.resolve(__dirname, "../public/js", file), "utf8");
	vm.runInNewContext(code, { frappe });
	assert.ok(handlers[doctype], `${file} must register ${doctype}`);
	return handlers[doctype];
}

function mockFrm(doc, options = "") {
	const frm = {
		doc: { __islocal: 1, ...doc },
		fields_dict: { naming_series: { df: { options, default: "" } } },
		is_new: () => true,
		set_df_property: (field, prop, value) => (frm.fields_dict[field].df[prop] = value),
		set_value: (field, value) => (frm.doc[field] = value),
	};
	return frm;
}

const flush = () => new Promise((r) => setImmediate(r));

const cases = [
	["item_form.js", "Item", "item_group", { item_group: "Bahan Baku" }, { custom_naming_series: "BB.YY..####." }, "BB.YY..####.", "ITEM.YY..####."],
	["stock_entry_form.js", "Stock Entry", "stock_entry_type", { stock_entry_type: "Material Transfer" }, { custom_naming_series: "MTR-.YY.-.####" }, "MTR-.YY.-.####", "MAT-STE-.YYYY.-"],
	["material_request_form.js", "Material Request", "material_request_type", { material_request_type: "Purchase" }, { naming_series: "MREQ-PUR-.YY.-.####" }, "MREQ-PUR-.YY.-.####", "MAT-MR-.YYYY.-"],
];

for (const [file, doctype, trigger, doc, dbValue, expected, fallback] of cases) {
	test(`${doctype}: handler invoked twice keeps one option and a stable series`, async () => {
		const h = loadForm(file, doctype, dbValue);
		const frm = mockFrm(doc, "EXISTING-.###");
		h[trigger](frm);
		h[trigger](frm);
		await flush();
		assert.equal(frm.doc.naming_series, expected);
		const options = frm.fields_dict.naming_series.df.options.split("\n");
		assert.deepEqual(options, ["EXISTING-.###", expected]);
	});

	test(`${doctype}: missing configuration falls back to ${fallback}`, async () => {
		const h = loadForm(file, doctype, {});
		const frm = mockFrm(doc);
		h[trigger](frm);
		await flush();
		assert.equal(frm.doc.naming_series, fallback);
	});

	test(`${doctype}: saved documents are left alone`, async () => {
		const h = loadForm(file, doctype, dbValue);
		const frm = mockFrm({ ...doc, naming_series: "KEEP" });
		frm.is_new = () => false;
		h[trigger](frm);
		await flush();
		assert.equal(frm.doc.naming_series, "KEEP");
	});
}
