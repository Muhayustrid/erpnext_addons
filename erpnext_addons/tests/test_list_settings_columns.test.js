const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const code = fs.readFileSync(path.resolve(__dirname, "../public/js/list_settings_columns.js"), "utf8");

// Stub ListView whose setup_columns records what it saw synchronously, like the real async one.
function load() {
	const calls = [];
	class ListView {
		async setup_columns(fields_override = null) {
			calls.push({ fields_override, layout: this.list_filter?.active_layout_name });
		}
	}
	vm.runInNewContext(code, { frappe: { views: { ListView } } });
	return { ListView, calls };
}

function view(ListView, fields, layout = "Purchase Order-To Receive") {
	const lv = new ListView();
	lv.list_view_settings = fields === undefined ? {} : { fields };
	lv.list_filter = { active_layout_name: layout };
	return lv;
}

test("saved List Settings win over the active layout's columns", async () => {
	const { ListView, calls } = load();
	const lv = view(ListView, JSON.stringify([{ fieldname: "supplier_name" }]));
	await lv.setup_columns([{ fieldname: "set_warehouse" }]);
	assert.deepEqual(calls, [{ fields_override: null, layout: "default_layout" }]);
	assert.equal(lv.list_filter.active_layout_name, "Purchase Order-To Receive", "layout restored");
});

test("without List Settings the layout columns stay", async () => {
	const { ListView, calls } = load();
	for (const fields of [undefined, "[]", null]) {
		await view(ListView, fields).setup_columns([{ fieldname: "set_warehouse" }]);
	}
	assert.deepEqual(
		calls.map((c) => c.layout),
		["Purchase Order-To Receive", "Purchase Order-To Receive", "Purchase Order-To Receive"]
	);
	assert.ok(calls.every((c) => c.fields_override[0].fieldname === "set_warehouse"));
});

test("works before the layout menu exists and on malformed settings", async () => {
	const { ListView, calls } = load();
	const lv = view(ListView, JSON.stringify([{ fieldname: "a" }]));
	lv.list_filter = undefined;
	await lv.setup_columns();
	await view(ListView, "{not json").setup_columns([{ fieldname: "x" }]);
	assert.deepEqual(calls[0], { fields_override: null, layout: undefined });
	assert.equal(calls[1].fields_override[0].fieldname, "x");
});

test("no-op when ListView is missing", () => {
	assert.doesNotThrow(() => vm.runInNewContext(code, { frappe: { views: {} } }));
});
