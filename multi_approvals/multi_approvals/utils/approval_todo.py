"""ToDo lifecycle for both approval rows and information-request rows.

Idempotency rule: a row's own `todo` link field is the source of truth.
If it already points at an Open ToDo we never create a second one for the
same document + user + row.
"""

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
	return todo.name


def _close(todo_name, cancel=False):
	if not todo_name or not frappe.db.exists("ToDo", todo_name):
		return
	current_status = frappe.db.get_value("ToDo", todo_name, "status")
	if current_status == "Open":
		frappe.db.set_value("ToDo", todo_name, "status", "Cancelled" if cancel else "Closed")


def close_approval_todo(row, cancel=False):
	_close(row.todo, cancel=cancel)


def close_information_request_todo(row, cancel=False):
	_close(row.todo, cancel=cancel)
