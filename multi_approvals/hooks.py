app_name = "multi_approvals"
app_title = "Multi Approvals"
app_publisher = "Multi Approvals"
app_description = "A configurable, generic multi-level approval engine for any Frappe DocType."
app_email = "admin@example.com"
app_license = "MIT"

# Generic client script loaded on every desk page. It attaches itself to
# whichever DocType has an active Multi Approval Settings configuration -
# there is no per-DocType JS anywhere in this app.
app_include_js = "/assets/multi_approvals/js/multi_approval.js"

# ---------------------------------------------------------------------------
# Document events
#
# These are registered against "*" (every DocType) on purpose: the engine
# itself decides, per document, whether Multi Approval Settings has an
# active configuration for doc.doctype. If not, every entry point below is a
# no-op. This is what keeps the app free of DocType-specific logic.
# ---------------------------------------------------------------------------
doc_events = {
    "*": {
        "validate": "multi_approvals.multi_approvals.utils.approval_engine.validate",
        "on_update": "multi_approvals.multi_approvals.utils.approval_engine.on_update",
        "before_submit": "multi_approvals.multi_approvals.utils.approval_engine.validate_before_submit",
    }
}

# ---------------------------------------------------------------------------
# Installation / migration
# ---------------------------------------------------------------------------
after_install = "multi_approvals.install.after_install"
after_migrate = "multi_approvals.install.after_migrate"
