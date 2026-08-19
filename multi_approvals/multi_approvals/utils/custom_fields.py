"""Idempotent Custom Field synchronization.

sync_custom_fields() reads every registered row in Multi Approval Settings
and makes sure the fields the engine needs exist on that DocType, grouped
under their own "User Approvals" tab. It relies on frappe's own
create_custom_fields(), which already skips any fieldname that already
exists for a doctype - so calling this repeatedly (after_install,
after_migrate, or every time Multi Approval Settings is saved) never
creates duplicates and never touches admin-edited fields (update=False).

Disabling a configuration does NOT remove its fields - by design, fields
are only ever added here, never deleted.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from multi_approvals.multi_approvals.utils.approval_config import (
	APPROVAL_STATUS_FIELD,
	APPROVERS_FIELD,
	INFO_REQUESTS_FIELD,
	PENDING_WITH_FIELD,
	TODO_CREATED_FIELD,
)

APPROVAL_STATUS_OPTIONS = "Not Started\nPending\nInformation Requested\nApproved\nRejected"


TAB_FIELD = "custom_approval_tab"
COLUMN_BREAK_FIELD = "custom_approval_column_break"


def _last_fieldname(doctype):
	"""Anchor fieldname to insert after. Since the Approval fields are now
	wrapped in their own Tab Break, they always render as a self-contained
	"User Approvals" tab regardless of anchor - appending after the
	DocType's actual last field simply puts that tab last in the tab
	strip, which is the least surprising place for it to appear.
	"""
	meta = frappe.get_meta(doctype)
	if meta.fields:
		return meta.fields[-1].fieldname
	return None


def get_field_definitions(doctype):
	anchor = _last_fieldname(doctype)

	return [
		{
			"fieldname": TAB_FIELD,
			"label": "User Approvals",
			"fieldtype": "Tab Break",
			"insert_after": anchor,
		},
		{
			"fieldname": APPROVERS_FIELD,
			"label": "Approvers",
			"fieldtype": "Table",
			"options": "User Approval Table",
			"insert_after": TAB_FIELD,
		},
		{
			"fieldname": INFO_REQUESTS_FIELD,
			"label": "Information Requests",
			"fieldtype": "Table",
			"options": "Approval Information Request",
			"insert_after": APPROVERS_FIELD,
		},
		{
			"fieldname": COLUMN_BREAK_FIELD,
			"fieldtype": "Column Break",
			"insert_after": INFO_REQUESTS_FIELD,
		},
		{
			"fieldname": PENDING_WITH_FIELD,
			"label": "Approval Pending With",
			"fieldtype": "Link",
			"options": "User",
			"read_only": 1,
			"insert_after": COLUMN_BREAK_FIELD,
		},
		{
			"fieldname": APPROVAL_STATUS_FIELD,
			"label": "Approval Status",
			"fieldtype": "Select",
			"options": APPROVAL_STATUS_OPTIONS,
			"default": "Not Started",
			"read_only": 1,
			"insert_after": PENDING_WITH_FIELD,
		},
		{
			"fieldname": TODO_CREATED_FIELD,
			"label": "Approval ToDo Created",
			"fieldtype": "Check",
			"hidden": 1,
			"insert_after": APPROVAL_STATUS_FIELD,
		},
	]


def sync_custom_fields():
	if not frappe.db.exists("DocType", "Multi Approval Settings"):
		return

	settings = frappe.get_cached_doc("Multi Approval Settings")
	custom_fields = {}

	for row in settings.approval_configuration:
		if not row.document_type:
			continue
		if not frappe.db.exists("DocType", row.document_type):
			continue
		custom_fields[row.document_type] = get_field_definitions(row.document_type)

	if custom_fields:
		create_custom_fields(custom_fields, update=False)
