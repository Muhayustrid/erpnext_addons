// Quick Posting Date ranges for the accounting list views. The preset applies
// one `posting_date between` filter, so the Filter popover stays at one row.
(() => {
	const ListView = frappe.views && frappe.views.ListView;
	if (!ListView || !ListView.prototype.setup_view || ListView.prototype.__erpnext_addons_date_range) {
		return;
	}

	const TARGETS = new Set([
		"Journal Entry",
		"Payment Entry",
		"Purchase Invoice",
		"Sales Invoice",
	]);
	const pad = (value) => String(value).padStart(2, "0");
	const iso = (date) =>
		`${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
	const day = (value) => new Date(`${value}T00:00:00`);
	const normalize_date = (value) => {
		if (!value) return "";
		if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
		return frappe.datetime.user_to_obj ? frappe.datetime.user_to_obj(value) : value;
	};

	const ranges = () => {
		const today = day(frappe.datetime.get_today());
		const year = today.getFullYear();
		const month = today.getMonth();
		return {
			today: [iso(today), iso(today)],
			last_7_days: [iso(new Date(year, month, today.getDate() - 6)), iso(today)],
			this_month: [iso(new Date(year, month, 1)), iso(new Date(year, month + 1, 0))],
			last_month: [iso(new Date(year, month - 1, 1)), iso(new Date(year, month, 0))],
			this_year: [iso(new Date(year, 0, 1)), iso(new Date(year, 11, 31))],
		};
	};

	const apply_range = (list_view, from_date, to_date) => {
		const filter_area = list_view.filter_area;
		if (!filter_area || !from_date || !to_date) return Promise.resolve();

		const remove_existing = () => {
			const exists = filter_area.get().some((filter) => filter[1] === "posting_date");
			if (!exists) return Promise.resolve();
			return Promise.resolve(filter_area.remove("posting_date")).then(remove_existing);
		};

		return remove_existing().then(() =>
			filter_area.add(list_view.doctype, "posting_date", "Between", [from_date, to_date])
		);
	};

	const current_range = (list_view) => {
		const filters = (list_view.filter_area && list_view.filter_area.get()) || [];
		const current = filters.find(
			(filter) => filter[1] === "posting_date" && Array.isArray(filter[3]) && filter[3].length === 2
		);
		const today = frappe.datetime.get_today();
		return current ? current[3] : [today, today];
	};

	const custom_range = (list_view) => {
		const [from_date, to_date] = current_range(list_view);
		const dialog = new frappe.ui.Dialog({
			title: __("Custom Date Range"),
			fields: [
				{
					fieldtype: "Date",
					fieldname: "from_date",
					label: __("From Date"),
					reqd: 1,
					default: from_date,
				},
				{
					fieldtype: "Date",
					fieldname: "to_date",
					label: __("To Date"),
					reqd: 1,
					default: to_date,
				},
			],
			primary_action_label: __("Apply"),
			primary_action(values) {
				const from = normalize_date(values.from_date);
				const to = normalize_date(values.to_date);
				if (!from || !to) {
					frappe.msgprint(__("Select both dates."));
					return;
				}
				if (from > to) {
					frappe.msgprint(__("From Date cannot be after To Date."));
					return;
				}
				apply_range(list_view, from, to);
				dialog.hide();
			},
		});
		dialog.show();
	};

	const add_button = (list_view) => {
		if (list_view.__erpnext_addons_date_range_button) return;
		const filter_section = list_view.$filter_section;
		if (!filter_section || !frappe.ui || !frappe.ui.Dropdown) return;

		const selector = filter_section.find(".filter-selector");
		if (!selector || !selector.length) return;

		list_view.__erpnext_addons_date_range_button = true;
		const preset = (key) => () => {
			const [from_date, to_date] = ranges()[key];
			return apply_range(list_view, from_date, to_date);
		};
		const dropdown = new frappe.ui.Dropdown({
			button: {
				label: __("Date Range"),
				icon: "calendar",
				css_class: "quick-date-range",
				attrs: { "aria-label": __("Date Range") },
			},
			align: "end",
			options: [
				{ label: __("Today"), onclick: preset("today") },
				{ label: __("Last 7 Days"), onclick: preset("last_7_days") },
				{ label: __("This Month"), onclick: preset("this_month") },
				{ label: __("Last Month"), onclick: preset("last_month") },
				{ label: __("This Year"), onclick: preset("this_year") },
				{ label: __("Custom Range..."), onclick: () => custom_range(list_view) },
			],
		});

		const filter_button = selector.find(".filter-button");
		const target = filter_button.length ? filter_button.parent() : selector;
		target.prepend(dropdown.$trigger);
		dropdown.$trigger.find(".es-button__label").addClass("max-sm:hidden");
	};

	const original_setup_view = ListView.prototype.setup_view;
	ListView.prototype.setup_view = async function () {
		const result = await original_setup_view.call(this);
		if (TARGETS.has(this.doctype)) add_button(this);
		return result;
	};
	ListView.prototype.__erpnext_addons_date_range = true;
})();
