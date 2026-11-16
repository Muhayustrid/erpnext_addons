/**
 * Purchase Order MR picker columns
 *
 * Re-registers the native "Get Items From > Material Request" dialog so its
 * filter row also offers Title and the custom Requested By field.
 */

(function (root, factory) {
	if (typeof module === "object" && module.exports) {
		module.exports = factory();
	} else {
		root.purchase_order_get_material_request = factory();
	}
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
	"use strict";

	const REQUESTED_BY = "custom_requested_by";
	const REQUESTED_BY_LABEL = "Requested By";

	function build_mr_setters() {
		return { schedule_date: undefined, title: undefined, custom_requested_by: undefined };
	}

	// get_datatable_columns() is ["name", ...setters], but the head row starts with the checkbox cell.
	function header_cell_index(columns, fieldname) {
		const index = columns.indexOf(fieldname);
		return index === -1 ? -1 : index + 1;
	}

	function retitle_column(dialog) {
		const index = header_cell_index(dialog.get_datatable_columns(), REQUESTED_BY);
		if (index === -1) return;

		const apply = () => {
			const cells = dialog.$results && dialog.$results.find(".list-item--head .list-item__content");
			if (!cells) return;
			cells.eq(index).find("span").text(__(REQUESTED_BY_LABEL)).attr("title", __(REQUESTED_BY_LABEL));
		};

		// The dialog builds its results inside init(), which runs after map_current_doc returns
		// when the Material Request meta is not cached yet.
		const native_init = dialog.init;
		dialog.init = function () {
			const result = native_init.apply(this, arguments);
			apply();
			return result;
		};
		apply();
	}

	function add_mr_button(frm) {
		frm.remove_custom_button(__("Material Request"), __("Get Items From"));
		frm.add_custom_button(
			__("Material Request"),
			function () {
				const dialog = erpnext.utils.map_current_doc({
					method: "erpnext.stock.doctype.material_request.material_request.make_purchase_order",
					source_doctype: "Material Request",
					target: frm,
					setters: build_mr_setters(),
					get_query_filters: {
						material_request_type: "Purchase",
						docstatus: 1,
						status: ["!=", "Stopped"],
						per_ordered: ["<", 100],
						company: frm.doc.company,
					},
					allow_child_item_selection: true,
					child_fieldname: "items",
					child_columns: ["item_code", "item_name", "qty", "ordered_qty"],
				});
				retitle_column(dialog);
			},
			__("Get Items From")
		);
	}

	function init() {
		if (typeof frappe === "undefined" || !frappe.ui || !frappe.ui.form) {
			return false;
		}

		frappe.ui.form.on("Purchase Order", {
			refresh(frm) {
				if (frm.doc.docstatus === 0) add_mr_button(frm);
			},
		});
		return true;
	}

	init();

	return { build_mr_setters, header_cell_index, retitle_column, init };
});
