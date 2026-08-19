import frappe
from frappe.model.document import Document


class MultiApprovalSettings(Document):
	def validate(self):
		self.validate_unique_document_types()

	def validate_unique_document_types(self):
		seen = set()
		for row in self.approval_configuration:
			if not row.document_type:
				frappe.throw("Row #{0}: Document Type is required.".format(row.idx))
			if row.document_type in seen:
				frappe.throw(
					"Document Type '{0}' is configured more than once. "
					"Each DocType can only have one approval configuration.".format(row.document_type)
				)
			seen.add(row.document_type)

	def on_update(self):
		# Registering (or editing) a DocType here is the only trigger the
		# admin needs - the required custom fields are synced automatically.
		from multi_approvals.multi_approvals.utils.custom_fields import sync_custom_fields

		sync_custom_fields()
