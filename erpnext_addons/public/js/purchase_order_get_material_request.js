/**
 * Purchase Order MR picker columns
 *
 * Re-registers the native "Get Items From > Material Request" dialog so its
 * filter row also offers Title and the custom Requested By field, and adds
 * "Tambah dari Material Request" on a submitted Purchase Order, which amends
 * the Purchase Order instead of mapping into it.
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
	const AMENDMENT_METHOD = "erpnext_addons.buying.amendment.create_amendment_for_material_request";

	function build_mr_setters() {
		return { schedule_date: undefined, title: undefined, custom_requested_by: undefined };
	}

	function mr_query_filters(frm) {
		return {
			material_request_type: "Purchase",
			docstatus: 1,
			status: ["!=", "Stopped"],
			per_ordered: ["<", 100],
			company: frm.doc.company,
		};
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
		// New-style frappe.ui.form.on handlers run before ERPNext's cscript refresh, so our button
		// already wins by being registered first; removing the native one is only a safety net.
		frm.remove_custom_button(__("Material Request"), __("Get Items From"));
		frm.add_custom_button(
			__("Material Request"),
			function () {
				const dialog = erpnext.utils.map_current_doc({
					method: "erpnext.stock.doctype.material_request.material_request.make_purchase_order",
					source_doctype: "Material Request",
					target: frm,
					setters: build_mr_setters(),
					get_query_filters: mr_query_filters(frm),
					allow_child_item_selection: true,
					child_fieldname: "items",
					child_columns: ["item_code", "item_name", "qty", "ordered_qty"],
				});
				retitle_column(dialog);
			},
			__("Get Items From")
		);
	}

	function amendment_dialog_opts(frm) {
		return {
			doctype: "Material Request",
			filters: mr_query_filters(frm),
			setters: build_mr_setters(),
			allow_child_item_selection: false,
			action(selections) {
				// the dialog calls action with itself as this: hide the picker behind the confirmation
				this?.dialog?.hide();
				// a server refusal already shows its own error dialog, so swallow it to keep the console clean
				return start_amendment(frm, selections).catch(() => {});
			},
		};
	}

	function start_amendment(frm, selected) {
		if (!selected || !selected.length) {
			frappe.msgprint(__("Pilih dulu Material Request-nya."));
			return Promise.resolve(null);
		}

		return new Promise((resolve, reject) => {
			frappe.confirm(
				__(
					"Purchase Order {0} akan di-cancel dan nomornya berganti menjadi versi amendannya. Item dari Material Request yang dipilih masuk ke draft amend tersebut, jadi periksa draftnya lalu submit. Draft ini baru menutup Material Request setelah kamu submit.",
					[frm.doc.name]
				),
				() => {
					frappe
						.xcall(AMENDMENT_METHOD, {
							name: frm.doc.name,
							material_requests: JSON.stringify(selected),
						})
						.then((name) => {
							frappe.set_route("Form", "Purchase Order", name);
							resolve(name);
						})
						.catch(reject);
				},
				() => resolve(null)
			);
		});
	}

	function add_amendment_button(frm) {
		frm.add_custom_button(
			__("Tambah dari Material Request"),
			function () {
				const { filters, ...opts } = amendment_dialog_opts(frm);
				retitle_column(
					new frappe.ui.form.MultiSelectDialog({
						...opts,
						get_query: () => ({ filters }),
					})
				);
			},
			__("Get Items From")
		);
	}

	// mirrors the server guard so the button never shows on a PO that would be refused
	function can_amend(frm) {
		return (
			frm.doc.docstatus === 1 &&
			!frm.doc.inter_company_order_reference &&
			!frm.doc.is_subcontracted &&
			!flt(frm.doc.per_received) &&
			!flt(frm.doc.per_billed) &&
			!["Closed", "Completed", "On Hold", "Cancelled"].includes(frm.doc.status) &&
			frm.has_perm("cancel") &&
			frm.has_perm("create")
		);
	}

	function init() {
		if (typeof frappe === "undefined" || !frappe.ui || !frappe.ui.form) {
			return false;
		}

		frappe.ui.form.on("Purchase Order", {
			refresh(frm) {
				if (frm.doc.docstatus === 0) {
					add_mr_button(frm);
				} else if (can_amend(frm)) {
					add_amendment_button(frm);
				}
			},
		});
		return true;
	}

	init();

	return {
		build_mr_setters,
		header_cell_index,
		retitle_column,
		amendment_dialog_opts,
		start_amendment,
		init,
	};
});
