// Generic Multi Approvals client script.
//
// This is the ONLY client script in the app. It attaches to every form via
// frappe.ui.form.on("*", ...) and asks the server whether the current
// doctype has an active Multi Approval Settings configuration. If not, it
// renders nothing. There is no per-DocType JavaScript anywhere in this app.

frappe.provide("multi_approvals");

multi_approvals.config_cache = {};

frappe.ui.form.on("*", {
	refresh: function (frm) {
		multi_approvals.setup(frm);
	},
});

multi_approvals.setup = function (frm) {
	if (!frm.doc || frm.is_new() || !frm.doc.name) {
		return;
	}

	multi_approvals.get_config(frm.doc.doctype, function (config) {
		if (!config) {
			return;
		}

		multi_approvals.render_information_request_actions(frm);

		if (frm.doc.docstatus === 0) {
			multi_approvals.render_approval_actions(frm, config);
		}
	});
};

multi_approvals.get_config = function (doctype, callback) {
	if (Object.prototype.hasOwnProperty.call(multi_approvals.config_cache, doctype)) {
		callback(multi_approvals.config_cache[doctype]);
		return;
	}
	frappe.call({
		method: "multi_approvals.api.get_client_approval_config",
		args: { doctype: doctype },
		callback: function (r) {
			multi_approvals.config_cache[doctype] = r.message || null;
			callback(multi_approvals.config_cache[doctype]);
		},
	});
};

multi_approvals.get_my_pending_row = function (frm) {
	var rows = frm.doc.custom_add_approvers || [];
	for (var i = 0; i < rows.length; i++) {
		if (rows[i].user === frappe.session.user && !rows[i].action) {
			return rows[i];
		}
	}
	return null;
};

multi_approvals.render_approval_actions = function (frm, config) {
	var my_row = multi_approvals.get_my_pending_row(frm);
	if (!my_row) {
		return;
	}

	if (config.approval_mode === "Sequential" && frm.doc.custom_approval_pending_with !== frappe.session.user) {
		return;
	}

	var has_open_request = (frm.doc.custom_approval_information_requests || []).some(function (r) {
		return r.requested_by === frappe.session.user && r.status === "Pending";
	});
	if (has_open_request) {
		frm.dashboard.set_headline_alert(
			__("You have requested information and are waiting on a response before you can take action."),
			"orange"
		);
		return;
	}

	var allowed = config.allowed_actions || [];

	if (allowed.includes("Approve")) {
		frm.add_custom_button(
			__("Approve"),
			function () {
				multi_approvals.approve(frm, my_row);
			},
			__("Approval")
		);
	}

	if (allowed.includes("Reject")) {
		frm.add_custom_button(
			__("Reject"),
			function () {
				multi_approvals.reject(frm, my_row);
			},
			__("Approval")
		);
	}

	if (allowed.includes("Need More Information")) {
		frm.add_custom_button(
			__("Need More Information"),
			function () {
				multi_approvals.show_information_request_dialog(frm, my_row);
			},
			__("Approval")
		);
	}

	frm.page.set_indicator(__("Approval Pending With You"), "orange");
};

multi_approvals.approve = function (frm, row) {
	// Approve is the happy path - a quick yes/no confirm, no comment box.
	frappe.confirm(__("Approve this document?"), function () {
		frappe.call({
			method: "multi_approvals.api.take_approval_action",
			args: {
				doctype: frm.doc.doctype,
				docname: frm.doc.name,
				row_name: row.name,
				action: "Approve",
			},
			freeze: true,
			callback: function () {
				frm.reload_doc();
			},
		});
	});
};

multi_approvals.reject = function (frm, row) {
	// Reject always needs a reason on record.
	var d = new frappe.ui.Dialog({
		title: __("Reject"),
		fields: [
			{
				fieldname: "comments",
				fieldtype: "Small Text",
				label: __("Comments"),
				reqd: 1,
			},
		],
		primary_action_label: __("Reject"),
		primary_action: function (values) {
			frappe.call({
				method: "multi_approvals.api.take_approval_action",
				args: {
					doctype: frm.doc.doctype,
					docname: frm.doc.name,
					row_name: row.name,
					action: "Reject",
					comments: values.comments,
				},
				freeze: true,
				callback: function () {
					d.hide();
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
};

multi_approvals.show_information_request_dialog = function (frm, row) {
	var options = (frm.doc.custom_add_approvers || [])
		.filter(function (r) {
			return r.user !== row.user;
		})
		.map(function (r) {
			return { label: r.user, value: r.user };
		});

	var d = new frappe.ui.Dialog({
		title: __("Need More Information"),
		fields: [
			{
				fieldname: "request",
				fieldtype: "Small Text",
				label: __("What information is needed?"),
				reqd: 1,
			},
			{
				fieldname: "users",
				fieldtype: "MultiCheck",
				label: __("Request Information From"),
				options: options,
				columns: 2,
			},
		],
		primary_action_label: __("Send Request"),
		primary_action: function (values) {
			if (!values.users || !values.users.length) {
				frappe.msgprint(__("Please select at least one user to request information from."));
				return;
			}
			frappe.call({
				method: "multi_approvals.api.take_approval_action",
				args: {
					doctype: frm.doc.doctype,
					docname: frm.doc.name,
					row_name: row.name,
					action: "Need More Information",
					request: values.request,
					request_users: values.users,
				},
				freeze: true,
				callback: function () {
					d.hide();
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
};

multi_approvals.render_information_request_actions = function (frm) {
	var rows = (frm.doc.custom_approval_information_requests || []).filter(function (r) {
		return r.requested_from === frappe.session.user && r.status === "Pending";
	});

	if (!rows.length) {
		return;
	}

	frm.add_custom_button(
		__("Respond to Information Request"),
		function () {
			multi_approvals.show_respond_dialog(frm, rows[0]);
		},
		__("Approval")
	);
};

multi_approvals.show_respond_dialog = function (frm, row) {
	var d = new frappe.ui.Dialog({
		title: __("Respond to Information Request"),
		fields: [
			{
				fieldname: "request_display",
				fieldtype: "HTML",
				options:
					"<p><strong>" +
					__("Request from") +
					" " +
					frappe.utils.escape_html(row.requested_by) +
					":</strong><br>" +
					frappe.utils.escape_html(row.request || "") +
					"</p>",
			},
			{
				fieldname: "response",
				fieldtype: "Small Text",
				label: __("Your Response"),
				reqd: 1,
			},
		],
		primary_action_label: __("Submit Response"),
		primary_action: function (values) {
			frappe.call({
				method: "multi_approvals.api.submit_information_response",
				args: {
					doctype: frm.doc.doctype,
					docname: frm.doc.name,
					row_name: row.name,
					response: values.response,
				},
				freeze: true,
				callback: function () {
					d.hide();
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
};
