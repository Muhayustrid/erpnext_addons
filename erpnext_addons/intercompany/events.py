"""Doc event hooks: collect changed intercompany documents, recompute after the business commit.

Progress is written by a background job queued after the transaction commits, so a failure
or lock conflict in progress code can never roll back a submit or cancel.
"""

import frappe

from erpnext_addons.intercompany.chain import is_intercompany, neighbours, refresh_chain
from erpnext_addons.intercompany.progress import FIELDS

QUEUE = "ic_progress_queue"
JOB = "erpnext_addons.intercompany.events.process"
LOCK = "erpnext_addons_ic_progress"
ATTEMPTS = 3


def _installed(doc):
	# new code can run before migrate created the columns; never break saving then
	return doc.meta.has_field("custom_ic_next_step")


def _add(doctype, name):
	queue = frappe.flags.get(QUEUE)
	if queue is None:
		queue = frappe.flags[QUEUE] = []
		frappe.db.after_commit.add(_enqueue)
		# a rolled back request must not leave a stale queue for the next transaction
		frappe.db.after_rollback.add(lambda: frappe.flags.pop(QUEUE, None))
	if [doctype, name] not in queue:
		queue.append([doctype, name])


def on_change(doc, method=None):
	"""Runs on submit, cancel, update after submit and status changes (Close/Reopen)."""
	if doc.docstatus == 0 or not is_intercompany(doc) or not _installed(doc):
		return
	_add(doc.doctype, doc.name)


def before_cancel(doc, method=None):
	"""Remember neighbours while native links still exist; ERPNext unlinks invoices on cancel."""
	if not is_intercompany(doc) or not _installed(doc):
		return
	for doctype, name in neighbours(doc.doctype, doc.name):
		_add(doctype, name)


def _enqueue():
	docs = frappe.flags.pop(QUEUE, None)
	if docs:
		frappe.enqueue(JOB, queue="short", docs=docs)


def filelock(name, timeout):
	from frappe.utils.synchronization import filelock as _filelock

	return _filelock(name, timeout=timeout)


def process(docs):
	"""Background job: recompute every chain touching `docs`, serialised across workers."""
	for attempt in range(1, ATTEMPTS + 1):
		try:
			with filelock(LOCK, timeout=120):
				done = set()
				for doctype, name in docs:
					refresh_chain(doctype, name, done=done)
				frappe.db.commit()
			return
		except frappe.QueryDeadlockError:
			frappe.db.rollback()
			if attempt == ATTEMPTS:
				raise


def guard(doc, method=None):
	"""Keep the progress fields system-owned: revert any value coming from form, API or import."""
	if not _installed(doc):
		return
	saved = frappe.db.get_value(doc.doctype, doc.name, FIELDS, as_dict=True) if not doc.is_new() else None
	for field in FIELDS:
		default = "" if field == "custom_ic_next_step" else 0
		doc.set(field, saved.get(field) if saved else default)
