from multi_approvals.multi_approvals.utils.custom_fields import sync_custom_fields


def after_install():
	sync_custom_fields()


def after_migrate():
	sync_custom_fields()
