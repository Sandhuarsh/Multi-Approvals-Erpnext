"""ToDo lifecycle for both approval rows and information-request rows.

Idempotency rule: a row's own `todo` link field is the source of truth.
If it already points at an Open ToDo we never create a second one for the
same document + user + row.

Every create/close here also keeps the parent document's `_assign` field
in sync (the same field Frappe's own "Assign To" sidebar reads). Without
that, a plain ToDo insert() still creates a real, working ToDo record, but
it never shows up as an "Assigned To" avatar on the document or in the
user's "Assigned to Me" filters - the two places people actually look for
it - even though the record itself exists.
"""

import json

import frappe


def _is_open(todo_name):
	if not todo_name:
		return False
	return bool(frappe.db.exists("ToDo", {"name": todo_name, "status": "Open"}))


def _persist_todo_link(doctype, row_name, todo_name):
	# Only existing (already-saved) child rows can be targeted directly;
	# brand-new in-memory rows will be persisted by their own insert() call.
	if frappe.db.exists(doctype, row_name):
		frappe.db.set_value(doctype, row_name, "todo", todo_name)


def _get_assigned_users(doctype, name):
	value = frappe.db.get_value(doctype, name, "_assign")
	if not value:
		return []
	try:
		return json.loads(value)
	except Exception:
		return []


def _add_to_assign_field(doctype, name, user):
	if not user:
		return
	users = _get_assigned_users(doctype, name)
	if user not in users:
		users.append(user)
		frappe.db.set_value(doctype, name, "_assign", json.dumps(users), update_modified=False)


def _remove_from_assign_field(doctype, name, user):
	if not user:
		return
	users = _get_assigned_users(doctype, name)
	if user in users:
		users.remove(user)
		frappe.db.set_value(doctype, name, "_assign", json.dumps(users), update_modified=False)


def create_approval_todo(doc, row):
	"""Create (or reuse) the Open ToDo for one User Approval Table row."""
	if _is_open(row.todo):
		return row.todo

	todo = frappe.get_doc(
		{
			"doctype": "ToDo",
			"allocated_to": row.user,
			"reference_type": doc.doctype,
			"reference_name": doc.name,
			"description": "Please review and take action on {0} {1}".format(doc.doctype, doc.name),
			"status": "Open",
			"assigned_by": frappe.session.user,
		}
	).insert(ignore_permissions=True)

	row.todo = todo.name
	_persist_todo_link("User Approval Table", row.name, todo.name)
	_add_to_assign_field(doc.doctype, doc.name, row.user)
	return todo.name


def create_information_request_todo(doc, row):
	"""Create (or reuse) the Open ToDo for one Approval Information Request row."""
	if _is_open(row.todo):
		return row.todo

	todo = frappe.get_doc(
		{
			"doctype": "ToDo",
			"allocated_to": row.requested_from,
			"reference_type": doc.doctype,
			"reference_name": doc.name,
			"description": "{0} requested information on {1} {2}: {3}".format(
				row.requested_by, doc.doctype, doc.name, row.request
			),
			"status": "Open",
			"assigned_by": row.requested_by,
		}
	).insert(ignore_permissions=True)

	row.todo = todo.name
	_persist_todo_link("Approval Information Request", row.name, todo.name)
	_add_to_assign_field(doc.doctype, doc.name, row.requested_from)
	return todo.name


def _close(todo_name, cancel=False):
	if not todo_name or not frappe.db.exists("ToDo", todo_name):
		return
	current_status = frappe.db.get_value("ToDo", todo_name, "status")
	if current_status == "Open":
		frappe.db.set_value("ToDo", todo_name, "status", "Cancelled" if cancel else "Closed")


def close_approval_todo(row, cancel=False):
	_close(row.todo, cancel=cancel)
	_remove_from_assign_field(row.parenttype, row.parent, row.user)


def close_information_request_todo(row, cancel=False):
	_close(row.todo, cancel=cancel)
	_remove_from_assign_field(row.parenttype, row.parent, row.requested_from)
