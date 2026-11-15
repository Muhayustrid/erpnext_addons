// Frappe 16.52 list layouts (e.g. ERPNext's "To Receive") carry their own columns and ignore
// List View Settings, so a saved column order looks lost after refresh. When a doctype has
// saved List Settings, build columns from them; the layout still drives filters and sort.
// Doctypes with a title field also get the ID column pinned last and missing from the
// settings dialog; it is offered there as a normal row and placed where it was saved.
(() => {
	const ListView = frappe.views && frappe.views.ListView;
	if (!ListView || ListView.prototype.__erpnext_addons_columns) return;

	const saved_fields = (settings) => {
		try {
			const fields = JSON.parse((settings && settings.fields) || "[]");
			return Array.isArray(fields) ? fields : [];
		} catch {
			return [];
		}
	};

	const has_title_field = (meta) => !!(meta && meta.title_field && meta.title_field !== "name");

	// move the native trailing ID column to its saved position (index among saved fields)
	const place_id_column = (view) => {
		const saved = saved_fields(view.list_view_settings);
		const at = saved.findIndex((f) => f.fieldname === "name");
		const columns = view.columns || [];
		const from = columns.findIndex((c) => c.type === "Field" && c.df && c.df.fieldname === "name");
		if (at < 1 || from < 0) return;
		const [id] = columns.splice(from, 1);
		if (saved[at].width) id.df = { ...id.df, width: saved[at].width };
		// columns[0] is the subject, columns[1] the Tag column; saved[0] is the subject
		const before = saved.slice(1, at).map((f) => f.fieldname);
		let insert = 2;
		for (let i = 2; i < columns.length; i++) {
			const c = columns[i];
			const key = c.type === "Status" ? "status_field" : c.df && c.df.fieldname;
			if (before.includes(key)) insert = i + 1;
		}
		columns.splice(insert, 0, id);
	};

	const original_setup = ListView.prototype.setup_columns;
	ListView.prototype.__erpnext_addons_columns = true;
	ListView.prototype.setup_columns = function (fields_override = null) {
		if (!saved_fields(this.list_view_settings).length) {
			return original_setup.call(this, fields_override);
		}
		// setup_columns reads the active layout synchronously before its first await
		const list_filter = this.list_filter;
		const layout = list_filter && list_filter.active_layout_name;
		if (list_filter) list_filter.active_layout_name = "default_layout";
		let result;
		try {
			result = original_setup.call(this, null);
		} finally {
			if (list_filter) list_filter.active_layout_name = layout;
		}
		return Promise.resolve(result).then((value) => {
			if (has_title_field(this.meta)) place_id_column(this);
			return value;
		});
	};

	const original_show = ListView.prototype.show_list_settings;
	if (original_show) {
		ListView.prototype.show_list_settings = function () {
			const fields = saved_fields(this.list_view_settings);
			if (has_title_field(this.meta) && fields.length && !fields.some((f) => f.fieldname === "name")) {
				fields.push({ fieldname: "name", label: __("ID") });
				this.list_view_settings = { ...this.list_view_settings, fields: JSON.stringify(fields) };
			}
			return original_show.call(this);
		};
	}
})();
