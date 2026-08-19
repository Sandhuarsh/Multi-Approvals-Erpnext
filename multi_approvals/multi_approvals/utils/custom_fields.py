"""Idempotent Custom Field synchronization.

sync_custom_fields() reads every registered row in Multi Approval Settings
and makes sure the five fields the engine needs exist on that DocType. It
relies on frappe's own create_custom_fields(), which already skips any
fieldname that already exists for a doctype - so calling this repeatedly
(after_install, after_migrate, or every time Multi Approval Settings is
saved) never creates duplicates and never touches admin-edited fields
(update=False).

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


def _last_fieldname(doctype):
	meta = frappe.get_meta(doctype)
	if meta.fields:
		return meta.fields[-1].fieldname
	return None


def get_field_definitions(doctype):
	insert_after = _last_fieldname(doctype)

	return [
		{
			"fieldname": APPROVERS_FIELD,
			"label": "Approvers",
			"fieldtype": "Table",
			"options": "User Approval Table",
			"insert_after": insert_after,
		},
		{
			"fieldname": INFO_REQUESTS_FIELD,
			"label": "Information Requests",
			"fieldtype": "Table",
			"options": "Approval Information Request",
			"insert_after": APPROVERS_FIELD,
		},
		{
			"fieldname": PENDING_WITH_FIELD,
			"label": "Approval Pending With",
			"fieldtype": "Link",
			"options": "User",
			"read_only": 1,
			"insert_after": INFO_REQUESTS_FIELD,
		},
		{
			"fieldname": TODO_CREATED_FIELD,
			"label": "Approval ToDo Created",
			"fieldtype": "Check",
			"hidden": 1,
			"insert_after": PENDING_WITH_FIELD,
		},
		{
			"fieldname": APPROVAL_STATUS_FIELD,
			"label": "Approval Status",
			"fieldtype": "Select",
			"options": APPROVAL_STATUS_OPTIONS,
			"default": "Not Started",
			"read_only": 1,
			"insert_after": TODO_CREATED_FIELD,
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
