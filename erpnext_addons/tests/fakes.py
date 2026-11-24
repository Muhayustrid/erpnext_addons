"""In-memory Frappe stand-in for unit tests that must run without a site.

Tests patch the module-level `frappe` of the code under test with FakeFrappe,
so the real framework is never touched even when this runs under bench.
"""

import sys
import types


def _passthrough_whitelist(*args, **kwargs):
	return lambda fn: fn


def ensure_frappe_importable():
	"""Register a bare `frappe` stub only when the real framework is absent."""
	try:
		import frappe  # noqa: F401
		import frappe.model.naming  # noqa: F401
	except ImportError:
		frappe = types.ModuleType("frappe")
		model = types.ModuleType("frappe.model")
		naming = types.ModuleType("frappe.model.naming")
		document = types.ModuleType("frappe.model.document")
		desk = types.ModuleType("frappe.desk")
		query_report = types.ModuleType("frappe.desk.query_report")
		naming.get_default_naming_series = lambda doctype: None
		document.Document = type("Document", (), {})
		query_report.run = lambda *args, **kwargs: {}
		query_report.get_script = lambda report_name: {}
		frappe.model, model.naming, model.document = model, naming, document
		frappe.desk, desk.query_report = desk, query_report
		frappe.whitelist = _passthrough_whitelist
		frappe.read_only = _passthrough_whitelist
		frappe.parse_json = lambda value: value
		sys.modules.update(
			{
				"frappe": frappe,
				"frappe.model": model,
				"frappe.model.naming": naming,
				"frappe.model.document": document,
				"frappe.desk": desk,
				"frappe.desk.query_report": query_report,
			}
		)


class FakeValidationError(Exception):
	pass


class _Field:
	def __init__(self, default):
		self.default = default


class _Meta:
	def __init__(self, defaults):
		self._defaults = defaults

	def get_field(self, fieldname):
		return _Field(self._defaults.get(fieldname))


class _Doc(dict):
	def __getattr__(self, key):
		return self.get(key)

	def __setattr__(self, key, value):
		self[key] = value


class FakeDB:
	def __init__(self, frappe):
		self._frappe = frappe
		self.tables = {}
		self.columns = set()
		self.writes = []

	def _rows(self, doctype, filters):
		table = self.tables.get(doctype, {})
		if isinstance(filters, str):
			return [table[filters]] if filters in table else []
		return [r for r in table.values() if all(r.get(k) == v for k, v in filters.items())]

	def table_exists(self, doctype):
		return doctype in self.tables

	def has_column(self, doctype, column):
		return (doctype, column) in self.columns

	def exists(self, doctype, filters=None):
		rows = self._rows(doctype, filters)
		return rows[0]["name"] if rows else None

	def get_value(self, doctype, filters, fieldname="name"):
		rows = self._rows(doctype, filters)
		return rows[0].get(fieldname) if rows else None

	def set_value(self, doctype, name, fieldname, value):
		self.writes.append((doctype, name, fieldname, value))
		self.tables[doctype][name][fieldname] = value

	def commit(self):
		raise AssertionError("code under test must not commit")


class FakeFrappe:
	ValidationError = FakeValidationError

	def __init__(self):
		self.db = FakeDB(self)
		self.meta_defaults = {}
		self.cleared = []
		self.inserted = []

	# data helpers for tests
	def add(self, _doctype, _name, **values):
		self.db.tables.setdefault(_doctype, {})[_name] = {"name": _name, **values}

	def get_meta(self, doctype):
		return _Meta(self.meta_defaults.get(doctype, {}))

	def get_doc(self, doctype, name=None):
		if isinstance(doctype, dict):
			fake = self

			class _New(_Doc):
				def insert(self, ignore_permissions=False):
					key = self.get("name") or self.get("module_name") or f"hash-{len(fake.inserted)}"
					fake.add(self["doctype"], key, **{k: v for k, v in self.items() if k not in ("name", "doctype")})
					fake.inserted.append(dict(self))
					return self

			return _New(doctype)
		return _Doc(self.db.tables[doctype][name])

	def clear_cache(self, doctype=None):
		self.cleared.append(doctype)

	def throw(self, msg, exc=None):
		raise (exc or FakeValidationError)(msg)

	def _(self, msg):
		return msg


def new_doc(**values):
	return _Doc(values)
