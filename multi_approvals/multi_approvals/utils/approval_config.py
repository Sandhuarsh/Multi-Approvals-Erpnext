"""Shared constants and configuration lookup for the Multi Approvals engine.

This is the only place that reads Multi Approval Settings. Every other
module (and every DocType) goes through get_approval_config() instead of
querying Multi Approval Settings directly, so the "HOW" of approval always
comes from a single source of truth.
"""

import frappe

APPROVE = "Approve"
REJECT = "Reject"
NEED_MORE_INFORMATION = "Need More Information"

# Fieldnames of the custom fields synced onto every registered DocType.
APPROVERS_FIELD = "custom_add_approvers"
INFO_REQUESTS_FIELD = "custom_approval_information_requests"
PENDING_WITH_FIELD = "custom_approval_pending_with"
TODO_CREATED_FIELD = "custom_todo_created"
APPROVAL_STATUS_FIELD = "custom_approval_status"

APPROVER_DOCTYPE = "User Approval Table"
INFO_REQUEST_DOCTYPE = "Approval Information Request"


def get_approval_config(doctype):
	"""Return the active Approval Configuration row for doctype, or None.

	None is returned when the DocType is not registered, is registered but
	disabled, or Multi Approval Settings has no matching row at all.
	"""
	if not doctype:
		return None

	settings = frappe.get_cached_doc("Multi Approval Settings")
	for row in settings.approval_configuration:
		if row.document_type == doctype and row.is_enabled:
			return row
	return None


def get_allowed_actions(config):
	"""Expand the three allow_* checkboxes on a config row into a list."""
	actions = []
	if config.allow_approve:
		actions.append(APPROVE)
	if config.allow_reject:
		actions.append(REJECT)
	if config.allow_need_more_information:
		actions.append(NEED_MORE_INFORMATION)
	return actions


def find_child_row(doc, fieldname, row_name):
	for row in doc.get(fieldname) or []:
		if row.name == row_name:
			return row
	frappe.throw("The specified row could not be found on this document.")
