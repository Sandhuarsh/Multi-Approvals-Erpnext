"""One-time migration for sites that installed Multi Approvals before the
Approval fields moved from a "custom_approval_section" Section Break into
their own "custom_approval_tab" Tab Break ("User Approvals" tab).

Deleting a Custom Field only removes its field definition:
  - Table fields (Approvers / Information Requests) have no data of their
    own on the parent doctype - the child rows live independently in
    their own tables and are untouched.
  - Link/Select/Check fields keep their underlying DB column and values;
    Frappe reuses the existing column when the field is redefined.

So recreating everything under the new layout is safe and non-destructive.
"""

import frappe

OLD_SECTION_FIELD = "custom_approval_section"

FIELDNAMES_TO_RELOCATE = [
	"custom_approval_section",
	"custom_add_approvers",
	"custom_approval_information_requests",
	"custom_approval_column_break",
	"custom_approval_pending_with",
	"custom_approval_status",
	"custom_todo_created",
]


def execute():
	affected_doctypes = frappe.get_all(
		"Custom Field", filters={"fieldname": OLD_SECTION_FIELD}, pluck="dt"
	)
	if not affected_doctypes:
		return

	for doctype in affected_doctypes:
		for fieldname in FIELDNAMES_TO_RELOCATE:
			name = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname})
			if name:
				frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)

	from multi_approvals.multi_approvals.utils.custom_fields import sync_custom_fields

	sync_custom_fields()
