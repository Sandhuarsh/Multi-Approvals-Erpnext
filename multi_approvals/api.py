"""Whitelisted endpoints for the generic Multi Approvals client script.

Every method here re-loads the document fresh via frappe.get_doc() before
doing anything, so each call always acts on the latest saved state. All
authorization (row ownership, information-request ownership, action
validity, current approval state) is enforced inside the engine/
information_request modules - this file is a thin, permission-checked
transport layer, not where security decisions are made.
"""

import json

import frappe
from frappe import _

from multi_approvals.multi_approvals.utils.approval_config import get_allowed_actions, get_approval_config
from multi_approvals.multi_approvals.utils.approval_engine import get_pending_approvers, process_approval_action
from multi_approvals.multi_approvals.utils.custom_fields import sync_custom_fields
from multi_approvals.multi_approvals.utils.information_request import respond_to_information_request


def _check_read_permission(doc):
	if not doc.has_permission("read"):
		frappe.throw(_("You do not have permission to access this document."), frappe.PermissionError)


@frappe.whitelist()
def get_client_approval_config(doctype):
	"""Used by the generic form script to decide whether to render any
	approval UI at all for the DocType currently open in the desk."""
	config = get_approval_config(doctype)
	if not config:
		return None
	return {
		"approval_mode": config.approval_mode,
		"auto_submit_on_final_approval": config.auto_submit_on_final_approval,
		"approver_source": config.approver_source,
		"allowed_actions": get_allowed_actions(config),
	}


@frappe.whitelist()
def take_approval_action(doctype, docname, row_name, action, comments=None, request=None, request_users=None):
	if isinstance(request_users, str):
		request_users = json.loads(request_users) if request_users else []

	doc = frappe.get_doc(doctype, docname)
	_check_read_permission(doc)

	information_request = None
	if action == "Need More Information":
		information_request = {"request": request, "users": request_users or []}

	return process_approval_action(doc, row_name, action, comments=comments, information_request=information_request)


@frappe.whitelist()
def submit_information_response(doctype, docname, row_name, response):
	doc = frappe.get_doc(doctype, docname)
	_check_read_permission(doc)

	respond_to_information_request(doc, row_name, response)
	return {"status": "Responded"}


@frappe.whitelist()
def get_pending_approvers_for_document(doctype, docname):
	doc = frappe.get_doc(doctype, docname)
	_check_read_permission(doc)
	return [row.user for row in get_pending_approvers(doc)]


@frappe.whitelist()
def sync_custom_fields_api():
	frappe.only_for("System Manager")
	sync_custom_fields()
	return {"status": "ok"}
