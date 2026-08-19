frappe.ui.form.on("Multi Approval Settings", {
	refresh: function (frm) {
		frm.add_custom_button(__("Sync Custom Fields"), function () {
			frappe.call({
				method: "multi_approvals.api.sync_custom_fields_api",
				freeze: true,
				callback: function () {
					frappe.msgprint(__("Custom fields have been synced for all registered Document Types."));
				},
			});
		});
	},
});

frappe.ui.form.on("Approval Configuration", {
	allow_approve: warn_if_no_actions_allowed,
	allow_reject: warn_if_no_actions_allowed,
	allow_need_more_information: warn_if_no_actions_allowed,
});

function warn_if_no_actions_allowed(frm, cdt, cdn) {
	var row = locals[cdt][cdn];
	if (!row.allow_approve && !row.allow_reject && !row.allow_need_more_information) {
		frappe.msgprint(
			__("At least one allowed action should be enabled, otherwise approvers will not be able to take any action.")
		);
	}
}
