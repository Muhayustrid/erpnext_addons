// The Account tree toolbar overrides this file after account_tree.js: ERPNext
// defines the Company filter as a native Select, which cannot be searched.
(() => {
	const settings = frappe.treeview_settings && frappe.treeview_settings["Account"];
	const company =
		settings && settings.filters && settings.filters.find((f) => f.fieldname === "company");
	if (!company) return;

	company.fieldtype = "Autocomplete";
	// Free text can now be unmatched; keeping the old value stops the tree from
	// reloading with an empty company.
	company.on_make = (control) => {
		const validate = control.validate.bind(control);
		control.validate = (value) => validate(value) || control.value || company.default;
	};
})();
