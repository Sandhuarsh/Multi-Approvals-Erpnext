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

This is deliberately NOT gated on "does the old Section Break field still
exist" - if a previous run of this patch was interrupted partway (e.g. the
process was killed mid-migration), it may have already deleted the old
field without finishing the rebuild, which would make that check silently
skip the repair forever on every retry. Instead, this always normalizes
every doctype that is either currently registered in Multi Approval
Settings or still carries any trace of our fields, regardless of what
partial state a previous failed run left behind.
"""

import frappe

FIELDNAMES_TO_RELOCATE = [
	"custom_approval_section",  # old Section Break (pre-tab layout)
	"custom_approval_tab",  # new Tab Break - recreated too, in case a prior run left it half-wired
	"custom_add_approvers",
	"custom_approval_information_requests",
	"custom_approval_column_break",
	"custom_approval_pending_with",
	"custom_approval_status",
	"custom_todo_created",
]


def execute():
	if not frappe.db.exists("DocType", "Multi Approval Settings"):
		return

	settings = frappe.get_cached_doc("Multi Approval Settings")
	doctypes = {row.document_type for row in settings.approval_configuration if row.document_type}

	# Also catch any doctype left over from a previous interrupted run,
	# even if it's since been removed from the settings.
	doctypes |= set(
		frappe.get_all(
			"Custom Field",
			filters={"fieldname": ["in", FIELDNAMES_TO_RELOCATE]},
			pluck="dt",
		)
	)

	for doctype in doctypes:
		for fieldname in FIELDNAMES_TO_RELOCATE:
			name = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname})
			if name:
				frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)

	from multi_approvals.multi_approvals.utils.custom_fields import sync_custom_fields

	sync_custom_fields()
