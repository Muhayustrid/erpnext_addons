const test = require("node:test");
const assert = require("node:assert/strict");

const MODULE = "../public/js/purchase_order_get_material_request.js";

// Fake MultiSelectDialog: records the header label write, ignores rendering otherwise.
function fake_dialog(columns) {
	const labels = [];
	const span = {
		text(value) {
			labels.push({ index: this.index, value });
			return this;
		},
		attr() {
			return this;
		},
	};
	const $results = {
		find: () => ({
			eq(index) {
				return { find: () => Object.assign(Object.create(span), { index }) };
			},
		}),
	};
	return {
		columns,
		labels,
		$results,
		init() {},
		get_datatable_columns() {
			return this.columns;
		},
	};
}

function load({ form = true, columns } = {}) {
	const handlers = {};
	const mapped = [];
	const dialog = fake_dialog(columns || ["name", "schedule_date", "title", "custom_requested_by"]);

	global.__ = (s) => s;
	global.frappe = { ui: form ? { form: { on: (doctype, handler) => (handlers[doctype] = handler) } } : {} };
	global.erpnext = { utils: { map_current_doc: (opts) => (mapped.push(opts), dialog) } };

	delete require.cache[require.resolve(MODULE)];
	const mod = require(MODULE);
	return { mod, handlers, mapped, dialog };
}

// Uncached Material Request meta: map_current_doc returns before init() renders the head row.
function delayed_dialog(columns) {
	const cells = ["checkbox", "name", "schedule_date", "title", "custom_requested_by"].map((column) => ({
		column,
		text: "",
		title: "",
	}));
	const dialog = {
		columns,
		cells,
		$results: undefined,
		built: false,
		init() {
			dialog.built = true;
			dialog.$results = {
				find: () => ({
					eq: (index) => ({
						find: () => ({
							text(value) {
								cells[index].text = value;
								return this;
							},
							attr(name, value) {
								cells[index][name] = value;
								return this;
							},
						}),
					}),
				}),
			};
		},
		get_datatable_columns() {
			return this.columns;
		},
	};
	return dialog;
}

function fake_frm(docstatus) {
	const calls = [];
	return {
		calls,
		doc: { docstatus, company: "Roti Ropi" },
		remove_custom_button: (...args) => calls.push(["remove", ...args]),
		add_custom_button: (...args) => calls.push(["add", ...args]),
	};
}

test("setters add title and requested by", () => {
	const { mod } = load();
	assert.deepEqual(Object.keys(mod.build_mr_setters()), ["schedule_date", "title", "custom_requested_by"]);
	assert.equal(mod.build_mr_setters().schedule_date, undefined);
});

test("header cell index counts only the checkbox", () => {
	const { mod } = load();
	const columns = ["name", "schedule_date", "title", "custom_requested_by"];
	assert.equal(mod.header_cell_index(columns, "custom_requested_by"), 4);
	assert.equal(mod.header_cell_index(columns, "missing"), -1);
});

test("refresh on a draft PO replaces the core button", () => {
	const { handlers, mapped, dialog } = load();
	const frm = fake_frm(0);

	handlers["Purchase Order"].refresh(frm);

	assert.deepEqual(frm.calls, [
		["remove", "Material Request", "Get Items From"],
		["add", "Material Request", frm.calls[1][2], "Get Items From"],
	]);

	frm.calls[1][2](); // click the button

	const opts = mapped[0];
	assert.equal(opts.method, "erpnext.stock.doctype.material_request.material_request.make_purchase_order");
	assert.equal(opts.source_doctype, "Material Request");
	assert.equal(opts.target, frm);
	assert.deepEqual(opts.setters, { schedule_date: undefined, title: undefined, custom_requested_by: undefined });
	assert.deepEqual(opts.get_query_filters, {
		material_request_type: "Purchase",
		docstatus: 1,
		status: ["!=", "Stopped"],
		per_ordered: ["<", 100],
		company: "Roti Ropi",
	});
	assert.equal(opts.allow_child_item_selection, true);
	assert.equal(opts.child_fieldname, "items");
	assert.deepEqual(opts.child_columns, ["item_code", "item_name", "qty", "ordered_qty"]);
	assert.deepEqual(dialog.labels, [{ index: 4, value: "Requested By" }]);
});

test("refresh on a submitted PO adds no picker button", () => {
	const { handlers, mapped } = load();
	const frm = fake_frm(1);

	handlers["Purchase Order"].refresh(frm);

	assert.deepEqual(frm.calls, []);
	assert.deepEqual(mapped, []);
});

test("retitle_column leaves a dialog without the column alone", () => {
	const { mod, dialog } = load({ columns: ["name", "schedule_date", "title"] });

	mod.retitle_column(dialog);

	assert.deepEqual(dialog.labels, []);
});

test("retitle_column labels the header once a delayed init renders it", () => {
	const { mod } = load();
	const dialog = delayed_dialog(["name", "schedule_date", "title", "custom_requested_by"]);

	assert.doesNotThrow(() => mod.retitle_column(dialog));
	assert.equal(dialog.built, false, "results not rendered yet");
	assert.deepEqual(
		dialog.cells.map((cell) => cell.text),
		["", "", "", "", ""],
		"nothing written before init"
	);

	dialog.init();

	assert.equal(dialog.cells[4].column, "custom_requested_by");
	assert.equal(dialog.cells[4].text, "Requested By");
	assert.equal(dialog.cells[4].title, "Requested By");
	assert.deepEqual(
		dialog.cells.slice(0, 4).map((cell) => cell.text),
		["", "", "", ""],
		"other header cells untouched"
	);
});

test("init is a no-op outside the desk", () => {
	const { mod } = load({ form: false });
	assert.equal(mod.init(), false);
});
