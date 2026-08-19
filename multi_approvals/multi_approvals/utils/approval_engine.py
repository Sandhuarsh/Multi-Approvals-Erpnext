"""Generic multi-level approval engine.

Nothing in this file ever branches on doc.doctype. Every entry point below
starts by asking approval_config.get_approval_config(doc.doctype) whether
an active configuration exists; if not, it is a no-op. This file is what
implements HOW approval works (sequential/parallel, reject, need-more-info,
final approval + auto-submit) - never WHO approves, which lives entirely on
the actual business document's Approvers table.
"""

import frappe
from frappe.utils import now_datetime

from multi_approvals.multi_approvals.utils.approval_config import (
	APPROVE,
	APPROVER_DOCTYPE,
	APPROVERS_FIELD,
	INFO_REQUEST_DOCTYPE,
	INFO_REQUESTS_FIELD,
	NEED_MORE_INFORMATION,
	REJECT,
	find_child_row,
	get_allowed_actions,
	get_approval_config,
)
from multi_approvals.multi_approvals.utils.approval_todo import (
	close_approval_todo,
	close_information_request_todo,
	create_approval_todo,
)
from multi_approvals.multi_approvals.utils.information_request import create_information_request

VALID_ACTIONS = {APPROVE, REJECT, NEED_MORE_INFORMATION}


# ---------------------------------------------------------------------------
# Hook entry points - registered against "*" in hooks.py
# ---------------------------------------------------------------------------

def validate(doc, method=None):
	config = get_approval_config(doc.doctype)
	if not config:
		return

	_guard_role_based(config, doc.doctype)

	approvers = doc.get(APPROVERS_FIELD) or []
	if approvers:
		validate_no_duplicate_approvers(approvers)

	if doc.get("custom_todo_created") and not doc.is_new():
		_prevent_approver_list_changes(doc)


def on_update(doc, method=None):
	if doc.docstatus != 0:
		return
	config = get_approval_config(doc.doctype)
	if not config:
		return
	start_approval_process(doc)


def validate_before_submit(doc, method=None):
	config = get_approval_config(doc.doctype)
	if not config:
		return

	approvers = doc.get(APPROVERS_FIELD) or []

	if not approvers:
		frappe.throw("Approvers are required before this document can be submitted.")

	if any(row.action == REJECT for row in approvers):
		frappe.throw("This document has been rejected and cannot be submitted.")

	if any(not row.action for row in approvers):
		frappe.throw("You cannot submit until all approvers have approved.")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _guard_role_based(config, doctype):
	if config.approver_source == "Role Based":
		frappe.throw(
			"Role Based approver source is not implemented yet for '{0}'. "
			"Please switch Approver Source to Manual in Multi Approval Settings.".format(doctype)
		)


def validate_no_duplicate_approvers(approvers):
	seen = set()
	for row in approvers:
		if not row.user:
			continue
		if row.user in seen:
			frappe.throw(
				"Duplicate approver found: {0}. Each user can only be added once as an approver.".format(row.user)
			)
		seen.add(row.user)


def _prevent_approver_list_changes(doc):
	before = doc.get_doc_before_save()
	if not before:
		return
	old_users = [row.user for row in (before.get(APPROVERS_FIELD) or [])]
	new_users = [row.user for row in (doc.get(APPROVERS_FIELD) or [])]
	if old_users != new_users:
		frappe.throw("Approvers cannot be changed once the approval process has started.")


def get_pending_approvers(doc):
	return [row for row in (doc.get(APPROVERS_FIELD) or []) if not row.action]


def _result(doc):
	return {
		"approval_status": doc.custom_approval_status,
		"pending_with": doc.custom_approval_pending_with,
	}


def _has_open_information_request(doc, user):
	return any(
		row.requested_by == user and row.status == "Pending" for row in (doc.get(INFO_REQUESTS_FIELD) or [])
	)


# ---------------------------------------------------------------------------
# Starting the approval process
# ---------------------------------------------------------------------------

def start_approval_process(doc):
	config = get_approval_config(doc.doctype)
	if not config:
		return
	if doc.get("custom_todo_created"):
		return

	approvers = doc.get(APPROVERS_FIELD) or []
	if not approvers:
		return

	_guard_role_based(config, doc.doctype)
	validate_no_duplicate_approvers(approvers)

	if config.approval_mode == "Sequential":
		pending_with = approvers[0].user
		create_approval_todo(doc, approvers[0])
	else:  # Parallel
		for row in approvers:
			create_approval_todo(doc, row)
		pending_with = approvers[0].user

	doc.db_set("custom_approval_pending_with", pending_with, update_modified=False)
	doc.db_set("custom_todo_created", 1, update_modified=False)
	doc.db_set("custom_approval_status", "Pending", update_modified=False)


# ---------------------------------------------------------------------------
# Processing an approver's decision
# ---------------------------------------------------------------------------

def validate_approver(doc, row):
	if frappe.session.user != row.user:
		frappe.throw("You are not authorized to take action for approver {0}".format(row.user))


def process_approval_action(doc, row_name, action, comments=None, information_request=None):
	if action not in VALID_ACTIONS:
		frappe.throw("Invalid approval action.")

	if doc.docstatus != 0:
		frappe.throw(
			"This document has already been submitted or cancelled. No further approval actions are allowed."
		)

	config = get_approval_config(doc.doctype)
	if not config:
		frappe.throw("Approval is not configured or enabled for this document type.")

	row = find_child_row(doc, APPROVERS_FIELD, row_name)
	validate_approver(doc, row)

	allowed_actions = get_allowed_actions(config)
	if action not in allowed_actions:
		frappe.throw(
			"Action '{0}' is not permitted by the approval configuration for this document type.".format(action)
		)

	if row.action:
		frappe.throw("You have already submitted a decision for this approval and it cannot be changed.")

	if _has_open_information_request(doc, row.user):
		frappe.throw(
			"You have requested information and are waiting for a response. "
			"Please wait until all requested information has been received before taking further action."
		)

	if config.approval_mode == "Sequential" and doc.custom_approval_pending_with != row.user:
		frappe.throw("It is not currently {0}'s turn to approve this document.".format(row.user))

	if action == NEED_MORE_INFORMATION:
		request_more_information(doc, row, comments, information_request or {})
		return _result(doc)

	frappe.db.set_value(
		APPROVER_DOCTYPE,
		row.name,
		{
			"action": action,
			"comments": comments,
			"approval_datetime": now_datetime(),
		},
	)
	row.action = action
	row.comments = comments
	row.approval_datetime = now_datetime()

	close_approval_todo(row)

	if action == REJECT:
		reject_approval(doc)
	elif action == APPROVE:
		move_to_next_approver(doc, config, row)

	return _result(doc)


# ---------------------------------------------------------------------------
# Reject
# ---------------------------------------------------------------------------

def reject_approval(doc):
	doc.db_set("custom_approval_status", "Rejected", update_modified=False)
	doc.db_set("custom_approval_pending_with", None, update_modified=False)

	for row in doc.get(APPROVERS_FIELD) or []:
		if not row.action:
			close_approval_todo(row, cancel=True)

	for info_row in doc.get(INFO_REQUESTS_FIELD) or []:
		if info_row.status == "Pending":
			frappe.db.set_value(INFO_REQUEST_DOCTYPE, info_row.name, "status", "Cancelled")
			info_row.status = "Cancelled"
			close_information_request_todo(info_row, cancel=True)


# ---------------------------------------------------------------------------
# Approve / advance the chain
# ---------------------------------------------------------------------------

def move_to_next_approver(doc, config, row):
	approvers = doc.get(APPROVERS_FIELD) or []

	if config.approval_mode == "Sequential":
		next_rows = [r for r in approvers if r.idx > row.idx]
		if next_rows:
			next_row = next_rows[0]
			create_approval_todo(doc, next_row)
			doc.db_set("custom_approval_pending_with", next_row.user, update_modified=False)
			doc.db_set("custom_approval_status", "Pending", update_modified=False)
		else:
			complete_approval(doc, config)
	else:  # Parallel
		pending = get_pending_approvers(doc)
		if not pending:
			complete_approval(doc, config)
		else:
			doc.db_set("custom_approval_pending_with", pending[0].user, update_modified=False)
			doc.db_set("custom_approval_status", "Pending", update_modified=False)


def complete_approval(doc, config):
	doc.db_set("custom_approval_pending_with", None, update_modified=False)
	doc.db_set("custom_approval_status", "Approved", update_modified=False)

	if config.auto_submit_on_final_approval and doc.docstatus == 0:
		doc.reload()
		doc.flags.ignore_permissions = True
		doc.submit()


# ---------------------------------------------------------------------------
# Need More Information
# ---------------------------------------------------------------------------

def request_more_information(doc, approval_row, comments, information_request):
	request_text = (information_request or {}).get("request")
	users = (information_request or {}).get("users") or []

	if not request_text:
		frappe.throw("Please describe what information is being requested.")
	if not users:
		frappe.throw("Please select at least one user to request information from.")

	valid_users = {r.user for r in (doc.get(APPROVERS_FIELD) or [])}
	seen = set()
	for user in users:
		if user == approval_row.user:
			frappe.throw("You cannot request information from yourself.")
		if user not in valid_users:
			frappe.throw("{0} is not an approver on this document and cannot be asked for information.".format(user))
		if user in seen:
			frappe.throw("{0} was selected more than once.".format(user))
		seen.add(user)

	if comments:
		frappe.db.set_value(APPROVER_DOCTYPE, approval_row.name, "comments", comments)
		approval_row.comments = comments

	for user in users:
		create_information_request(doc, requested_by=approval_row.user, requested_from=user, request=request_text)

	doc.db_set("custom_approval_status", "Information Requested", update_modified=False)
