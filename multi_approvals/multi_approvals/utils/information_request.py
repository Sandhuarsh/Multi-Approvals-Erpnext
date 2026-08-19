"""Information-request workflow: create requests, validate the responder,
record responses, and notify the requester once everything is answered.

This module never touches the requesting approver's own action/pending
state - that stays under the exclusive control of approval_engine.py so
the two concerns (approval decisions vs. information requests) never get
conflated, per the distinction the spec calls out explicitly.
"""

import frappe
from frappe.utils import now_datetime

from multi_approvals.multi_approvals.utils.approval_config import (
	INFO_REQUEST_DOCTYPE,
	INFO_REQUESTS_FIELD,
	find_child_row,
)
from multi_approvals.multi_approvals.utils.approval_todo import (
	close_information_request_todo,
	create_information_request_todo,
)


def create_information_request(doc, requested_by, requested_from, request):
	"""Insert one Approval Information Request row + its ToDo.

	Called once per selected user, so "Mike requests info from Sarah and
	David" always produces two independent rows/ToDos, never one merged
	request.
	"""
	existing = doc.get(INFO_REQUESTS_FIELD) or []
	next_idx = max([row.idx for row in existing], default=0) + 1

	child = frappe.get_doc(
		{
			"doctype": INFO_REQUEST_DOCTYPE,
			"parent": doc.name,
			"parenttype": doc.doctype,
			"parentfield": INFO_REQUESTS_FIELD,
			"idx": next_idx,
			"requested_by": requested_by,
			"requested_from": requested_from,
			"request": request,
			"status": "Pending",
			"requested_datetime": now_datetime(),
		}
	)
	child.insert(ignore_permissions=True)

	create_information_request_todo(doc, child)
	doc.append(INFO_REQUESTS_FIELD, child)
	return child


def validate_information_request_user(request_row):
	if frappe.session.user != request_row.requested_from:
		frappe.throw(
			"You are not authorized to respond to this information request. "
			"It was addressed to {0}.".format(request_row.requested_from)
		)


def respond_to_information_request(doc, row_name, response):
	if doc.docstatus != 0:
		frappe.throw("This document has already been submitted or cancelled. No further responses are allowed.")

	request_row = find_child_row(doc, INFO_REQUESTS_FIELD, row_name)

	if request_row.status != "Pending":
		frappe.throw("This information request has already been resolved.")

	validate_information_request_user(request_row)

	if not response:
		frappe.throw("Please provide a response before submitting.")

	responded_at = now_datetime()
	frappe.db.set_value(
		INFO_REQUEST_DOCTYPE,
		request_row.name,
		{
			"response": response,
			"status": "Responded",
			"responded_datetime": responded_at,
		},
	)
	request_row.response = response
	request_row.status = "Responded"
	request_row.responded_datetime = responded_at

	close_information_request_todo(request_row)
	complete_information_request(doc, request_row)

	return request_row


def complete_information_request(doc, request_row):
	_notify(
		request_row.requested_by,
		"{0} responded to your information request on {1} {2}.".format(
			request_row.requested_from, doc.doctype, doc.name
		),
	)

	still_pending = any(row.status == "Pending" for row in (doc.get(INFO_REQUESTS_FIELD) or []))

	if not still_pending and doc.custom_approval_status == "Information Requested":
		doc.db_set("custom_approval_status", "Pending", update_modified=False)
		_notify(
			request_row.requested_by,
			"All requested information for {0} {1} has been received. You may now review and take action.".format(
				doc.doctype, doc.name
			),
		)


def _notify(user, message):
	if not user:
		return
	try:
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"from_user": frappe.session.user,
				"subject": message,
				"type": "Alert",
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="Multi Approvals: Notification Failed")
