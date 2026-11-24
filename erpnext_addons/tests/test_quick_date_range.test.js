const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const code = fs.readFileSync(path.resolve(__dirname, "../public/js/quick_date_range.js"), "utf8");
const TARGETS = ["Journal Entry", "Payment Entry", "Purchase Invoice", "Sales Invoice"];
const plain = (value) => JSON.parse(JSON.stringify(value));

function load() {
	const dropdowns = [];
	const dialogs = [];
	const messages = [];

	class Dropdown {
		constructor(opts) {
			this.opts = opts;
			this.$trigger = { find: () => ({ addClass() {} }) };
			dropdowns.push(this);
		}
	}
	class Dialog {
		constructor(opts) {
			this.opts = opts;
			dialogs.push(this);
		}
		show() {
			this.shown = true;
		}
		hide() {
			this.hidden = true;
		}
	}
	class ListView {
		async setup_view() {
			this.setup_called = true;
		}
	}
	const frappe = {
		views: { ListView },
		ui: { Dropdown, Dialog },
		datetime: { get_today: () => "2026-11-24" },
		msgprint: (message) => messages.push(message),
	};

	vm.runInNewContext(code, { frappe, __: (value) => value });
	return { ListView, dropdowns, dialogs, messages };
}

function view(ListView, doctype, filters = []) {
	let current = filters.slice();
	const added = [];
	const removed = [];
	const prepended = [];
	const filter_area = {
		get: () => current.slice(),
		remove: (fieldname) => {
			removed.push(fieldname);
			current = current.filter((filter) => filter[1] !== fieldname);
			return Promise.resolve();
		},
		add: (dt, fieldname, condition, value) => added.push([dt, fieldname, condition, value]),
	};
	const $target = { length: 1, prepend: (element) => prepended.push(element) };
	const $selector = {
		length: 1,
		find: (selector) =>
			selector === ".filter-button" ? { length: 1, parent: () => $target } : { length: 0 },
	};
	const lv = new ListView();
	lv.doctype = doctype;
	lv.$filter_section = {
		find: (selector) => (selector === ".filter-selector" ? $selector : { length: 0 }),
	};
	lv.filter_area = filter_area;
	lv._added = added;
	lv._removed = removed;
	lv._prepended = prepended;
	return lv;
}

async function button_for(doctype, filters = []) {
	const { ListView, dropdowns } = load();
	const lv = view(ListView, doctype, filters);
	await lv.setup_view();
	return { lv, dropdown: dropdowns.at(-1), dropdowns };
}

test("adds the date range button to the four accounting list views", async () => {
	for (const doctype of TARGETS) {
		const { lv, dropdowns } = await button_for(doctype);
		assert.equal(dropdowns.length, 1, doctype);
		assert.equal(lv._prepended.length, 1, doctype);
	}
});

test("leaves other list views alone", async () => {
	const { lv, dropdowns } = await button_for("Sales Order");
	assert.equal(dropdowns.length, 0);
	assert.equal(lv._prepended.length, 0);
});

test("does not add the button twice", async () => {
	const { ListView, dropdowns } = load();
	const lv = view(ListView, "Journal Entry");
	await lv.setup_view();
	await lv.setup_view();
	assert.equal(dropdowns.length, 1);
	assert.equal(lv._prepended.length, 1);
});

test("offers the preset ranges", async () => {
	const { dropdown } = await button_for("Journal Entry");
	assert.deepEqual(plain(dropdown.opts.options.map((option) => option.label)), [
		"Today",
		"Last 7 Days",
		"This Month",
		"Last Month",
		"This Year",
		"Custom Range...",
	]);
});

test("presets apply one posting_date between filter", async () => {
	const ranges = [
		["Today", ["2026-11-24", "2026-11-24"]],
		["Last 7 Days", ["2026-11-18", "2026-11-24"]],
		["This Month", ["2026-11-01", "2026-11-30"]],
		["Last Month", ["2026-10-01", "2026-10-31"]],
		["This Year", ["2026-01-01", "2026-12-31"]],
	];
	for (const [label, expected] of ranges) {
		const { lv, dropdown } = await button_for("Journal Entry");
		const option = dropdown.opts.options.find((item) => item.label === label);
		await option.onclick();
		assert.deepEqual(plain(lv._added.at(-1)), [
			"Journal Entry",
			"posting_date",
			"Between",
			expected,
		]);
	}
});

test("replaces an existing posting_date filter", async () => {
	const existing = [
		["Journal Entry", "posting_date", "Between", ["2026-01-01", "2026-01-31"]],
	];
	const { lv, dropdown } = await button_for("Journal Entry", existing);
	const today = dropdown.opts.options.find((option) => option.label === "Today");
	await today.onclick();
	assert.deepEqual(lv._removed, ["posting_date"]);
	assert.deepEqual(plain(lv._added.at(-1)), [
		"Journal Entry",
		"posting_date",
		"Between",
		["2026-11-24", "2026-11-24"],
	]);
});

test("custom range opens a dialog and applies the picked dates", async () => {
	const { ListView, dropdowns, dialogs } = load();
	const lv = view(ListView, "Journal Entry");
	await lv.setup_view();
	const custom = dropdowns[0].opts.options.find((option) => option.label === "Custom Range...");
	custom.onclick();

	assert.equal(dialogs.length, 1);
	assert.equal(dialogs[0].shown, true);
	assert.deepEqual(plain(dialogs[0].opts.fields.map((field) => field.fieldname)), [
		"from_date",
		"to_date",
	]);

	dialogs[0].opts.primary_action({ from_date: "2026-11-01", to_date: "2026-11-10" });
	await Promise.resolve();
	assert.deepEqual(plain(lv._added.at(-1)), [
		"Journal Entry",
		"posting_date",
		"Between",
		["2026-11-01", "2026-11-10"],
	]);
	assert.equal(dialogs[0].hidden, true);
});

test("custom range rejects a reversed range without touching the filter", async () => {
	const { ListView, dropdowns, dialogs, messages } = load();
	const lv = view(ListView, "Journal Entry");
	await lv.setup_view();
	const custom = dropdowns[0].opts.options.find((option) => option.label === "Custom Range...");
	custom.onclick();

	dialogs[0].opts.primary_action({ from_date: "2026-11-10", to_date: "2026-11-01" });
	assert.equal(messages.length, 1);
	assert.equal(lv._added.length, 0);
	assert.ok(!dialogs[0].hidden);
});

test("missing ListView is a no-op", () => {
	assert.doesNotThrow(() =>
		vm.runInNewContext(code, { frappe: { views: {} }, __: (value) => value })
	);
});
