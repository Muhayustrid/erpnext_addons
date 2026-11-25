const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const code = fs.readFileSync(
	path.resolve(__dirname, "../public/js/account_tree_company_search.js"),
	"utf8"
);

function load(filters) {
	filters = filters || [
		{ fieldname: "company", fieldtype: "Select", options: ["A", "B"], default: "A" },
		{ fieldname: "root_company", fieldtype: "Data" },
	];
	vm.runInNewContext(code, { frappe: { treeview_settings: { Account: { filters } } } });
	return filters;
}

test("turns the Account tree company filter into a searchable Autocomplete", () => {
	const filters = load();
	assert.equal(filters[0].fieldtype, "Autocomplete");
	assert.deepEqual(filters[0].options, ["A", "B"]);
	assert.equal(filters[1].fieldtype, "Data");
});

test("keeps the last valid company when the typed text matches no option", () => {
	const filters = load();
	const control = { value: "A", validate: (value) => (value === "B" ? "B" : "") };
	filters[0].on_make(control);
	assert.equal(control.validate("B"), "B");
	assert.equal(control.validate("nonsense"), "A");
});

test("leaves tree settings without a company filter untouched", () => {
	const filters = load([{ fieldname: "root_company", fieldtype: "Data" }]);
	assert.deepEqual(filters, [{ fieldname: "root_company", fieldtype: "Data" }]);
});
