const test = require("node:test");
const assert = require("node:assert/strict");

const MODULE = "../public/js/purchase_order_get_material_request.js";
const METHOD = "erpnext_addons.buying.amendment.create_amendment_for_material_request";

function load({ doc, decline = false, xcall_failure } = {}) {
	const handlers = {};
	const calls = { confirm: [], xcall: [], set_route: [], dialogs: [], msgprint: [] };

	global.__ = (s) => s;
	global.flt = (value) => Number.parseFloat(value) || 0;
	global.frappe = {
		ui: {
			form: {
				on: (doctype, handler) => (handlers[doctype] = handler),
				MultiSelectDialog: function (opts) {
					calls.dialogs.push(opts);
					this.columns = ["name", "schedule_date", "title", "custom_requested_by"];
					this.get_datatable_columns = () => this.columns;
					this.init = () => {};
				},
			},
		},
		confirm: (message, accept, reject) => {
			calls.confirm.push(message);
			decline ? reject() : accept();
		},
		xcall: (...args) => {
			calls.xcall.push(args);
			return xcall_failure ? Promise.reject(xcall_failure) : Promise.resolve("PO-1-1");
		},
		set_route: (...args) => calls.set_route.push(args),
		msgprint: (message) => calls.msgprint.push(message),
	};
	global.erpnext = { utils: { map_current_doc: () => ({ get_datatable_columns: () => [], init() {} }) } };

	delete require.cache[require.resolve(MODULE)];
	const mod = require(MODULE);

	const frm = {
		doc: Object.assign({ docstatus: 1, name: "PO-1", company: "Roti Ropi" }, doc),
		calls: [],
		add_custom_button: (...args) => frm.calls.push(["add", ...args]),
		remove_custom_button: (...args) => frm.calls.push(["remove", ...args]),
		has_perm: () => true,
	};
	return { mod, handlers, calls, frm };
}

test("amendment dialog opts carry the PO filters", () => {
	const { mod, frm } = load();
	const opts = mod.amendment_dialog_opts(frm);

	assert.equal(opts.doctype, "Material Request");
	assert.equal(opts.filters.company, "Roti Ropi");
	assert.deepEqual(opts.filters.per_ordered, ["<", 100]);
	assert.deepEqual(opts.setters, {
		schedule_date: undefined,
		title: undefined,
		custom_requested_by: undefined,
	});
	assert.equal(opts.allow_child_item_selection, false);
	assert.equal(typeof opts.action, "function");
});

test("declining the confirmation calls no server method", async () => {
	const { mod, calls, frm } = load({ decline: true });

	const result = await mod.start_amendment(frm, ["MREQ-1"]);

	assert.equal(result, null);
	assert.equal(calls.confirm.length, 1);
	assert.deepEqual(calls.xcall, []);
	assert.deepEqual(calls.set_route, []);
});

test("accepting the confirmation calls the amendment and routes to the draft", async () => {
	const { mod, calls, frm } = load();

	await mod.start_amendment(frm, ["MREQ-1"]);

	assert.equal(calls.xcall.length, 1);
	assert.equal(calls.xcall[0][0], METHOD);
	assert.equal(calls.xcall[0][1].name, "PO-1");
	assert.equal(calls.xcall[0][1].material_requests, JSON.stringify(["MREQ-1"]));
	assert.deepEqual(calls.set_route, [["Form", "Purchase Order", "PO-1-1"]]);
});

test("a refused amendment rejects and routes nowhere", async () => {
	const reason = "Purchase Order ini sudah punya Purchase Receipt submitted, jadi tidak bisa di-amend.";
	const { mod, calls, frm } = load({ xcall_failure: reason });

	await assert.rejects(mod.start_amendment(frm, ["MREQ-1"]), (error) => error === reason);

	assert.equal(calls.xcall.length, 1);
	assert.deepEqual(calls.set_route, []);
});

test("submitted non-intercompany PO shows the button, intercompany does not", () => {
	const { mod, handlers, calls, frm } = load();

	handlers["Purchase Order"].refresh(frm);

	assert.equal(frm.calls.length, 1);
	const [kind, label, click, group] = frm.calls[0];
	assert.equal(kind, "add");
	assert.equal(label, "Tambah dari Material Request");
	assert.equal(group, "Get Items From");
	assert.equal(typeof click, "function");

	click();

	const opened = calls.dialogs[0];
	assert.equal(opened.doctype, "Material Request");
	assert.equal(opened.allow_child_item_selection, false);
	assert.deepEqual(opened.get_query(), {
		filters: {
			material_request_type: "Purchase",
			docstatus: 1,
			status: ["!=", "Stopped"],
			per_ordered: ["<", 100],
			company: "Roti Ropi",
		},
	});

	for (const doc of [{ inter_company_order_reference: "PO-1-1" }, { is_subcontracted: 1 }]) {
		const refused = load({ doc });
		refused.handlers["Purchase Order"].refresh(refused.frm);

		assert.deepEqual(refused.frm.calls, []);
	}
});

test("a received or billed PO shows no amendment button", () => {
	for (const doc of [{ per_received: 100 }, { per_billed: 100 }]) {
		const { handlers, frm } = load({ doc });

		handlers["Purchase Order"].refresh(frm);

		assert.deepEqual(frm.calls, []);
	}
});

test("empty selection asks for a Material Request instead of confirming", async () => {
	const { mod, calls, frm } = load();

	const result = await mod.start_amendment(frm, []);

	assert.equal(result, null);
	assert.deepEqual(calls.msgprint, ["Pilih dulu Material Request-nya."]);
	assert.deepEqual(calls.confirm, []);
	assert.deepEqual(calls.xcall, []);
});

test("the dialog action swallows a server refusal", async () => {
	const reason = "Purchase Order ini sudah punya Purchase Receipt submitted, jadi tidak bisa di-amend.";
	const { mod, calls, frm } = load({ xcall_failure: reason });

	await mod.amendment_dialog_opts(frm).action(["MREQ-1"]);

	assert.equal(calls.xcall.length, 1);
	assert.deepEqual(calls.set_route, []);
});
