// Frappe 16.52 list layouts (e.g. ERPNext's "To Receive") carry their own columns and ignore
// List View Settings, so a saved column order looks lost after refresh. When a doctype has
// saved List Settings, build columns from them; the layout still drives filters and sort.
(() => {
	const ListView = frappe.views && frappe.views.ListView;
	if (!ListView || ListView.prototype.__erpnext_addons_columns) return;

	const has_saved_columns = (settings) => {
		try {
			const fields = JSON.parse((settings && settings.fields) || "[]");
			return Array.isArray(fields) && fields.length > 0;
		} catch {
			return false;
		}
	};

	const original = ListView.prototype.setup_columns;
	ListView.prototype.__erpnext_addons_columns = true;
	ListView.prototype.setup_columns = function (fields_override = null) {
		if (!has_saved_columns(this.list_view_settings)) {
			return original.call(this, fields_override);
		}
		// setup_columns reads the active layout synchronously before its first await
		const list_filter = this.list_filter;
		const layout = list_filter && list_filter.active_layout_name;
		if (list_filter) list_filter.active_layout_name = "default_layout";
		try {
			return original.call(this, null);
		} finally {
			if (list_filter) list_filter.active_layout_name = layout;
		}
	};
})();
