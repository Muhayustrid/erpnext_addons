import frappe

from erpnext_addons.buying.setup import ensure_fields

SQL = (
	"UPDATE `tabMaterial Request` mr LEFT JOIN `tabUser` u ON u.name = mr.owner "
	"SET mr.custom_requested_by = COALESCE(u.full_name, mr.owner) "
	"WHERE ifnull(mr.custom_requested_by, '') = ''"
)


def execute():
	"""Create the field, then fill it on rows created before it existed."""
	ensure_fields()
	frappe.db.sql(SQL)
