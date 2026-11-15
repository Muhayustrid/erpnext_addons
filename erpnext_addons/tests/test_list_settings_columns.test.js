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

// ID column: Frappe pins it last when the doctype has a title field; saved order must win.
function loadFull({ title_field = "supplier_name", hide_name_column = false } = {}) {
	class ListView {
		async setup_columns() {
			// shape of Frappe's result after reorder_listview_fields: Subject, Tag, ordered fields, ID last
			const saved = JSON.parse(this.list_view_settings.fields || "[]").map((f) => f.fieldname);
			const cols = [{ type: "Subject", df: { fieldname: title_field } }, { type: "Tag" }];
			for (const f of saved.slice(1)) {
				if (f === "name") continue;
				cols.push(f === "status_field" ? { type: "Status" } : { type: "Field", df: { fieldname: f } });
			}
			if (!hide_name_column) cols.push({ type: "Field", df: { label: "ID", fieldname: "name" } });
			this.columns = cols;
		}
		show_list_settings() {
			this.opened_with = this.list_view_settings.fields;
		}
	}
	vm.runInNewContext(code, { frappe: { views: { ListView } }, __: (s) => s });
	const lv = new ListView();
	lv.meta = { title_field };
	return lv;
}

const names = (lv) => lv.columns.map((c) => (c.type === "Field" || c.type === "Subject" ? c.df.fieldname : c.type));

test("saved ID position is honoured instead of pinned last", async () => {
	const lv = loadFull();
	lv.list_view_settings = {
		fields: JSON.stringify([
			{ fieldname: "supplier_name" },
			{ fieldname: "name", width: 140 },
			{ fieldname: "status_field" },
			{ fieldname: "company" },
		]),
	};
	await lv.setup_columns();
	assert.deepEqual(names(lv), ["supplier_name", "Tag", "name", "Status", "company"]);
	assert.equal(lv.columns[2].df.width, 140);
});

test("without a saved ID the native last position stays", async () => {
	const lv = loadFull();
	lv.list_view_settings = { fields: JSON.stringify([{ fieldname: "supplier_name" }, { fieldname: "company" }]) };
	await lv.setup_columns();
	assert.deepEqual(names(lv), ["supplier_name", "Tag", "company", "name"]);
});

test("List Settings dialog offers ID as a movable row when missing", () => {
	const lv = loadFull();
	lv.list_view_settings = { fields: JSON.stringify([{ fieldname: "supplier_name" }, { fieldname: "company" }]) };
	lv.show_list_settings();
	assert.deepEqual(
		JSON.parse(lv.opened_with).map((f) => f.fieldname),
		["supplier_name", "company", "name"]
	);
	lv.show_list_settings();
	assert.equal(JSON.parse(lv.opened_with).filter((f) => f.fieldname === "name").length, 1, "added once");
});

test("doctypes whose subject is the ID are left alone", () => {
	const lv = loadFull({ title_field: undefined });
	lv.meta = {};
	lv.list_view_settings = { fields: JSON.stringify([{ fieldname: "name" }, { fieldname: "company" }]) };
	lv.show_list_settings();
	assert.deepEqual(JSON.parse(lv.opened_with).map((f) => f.fieldname), ["name", "company"]);
});
