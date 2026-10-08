import logging

from odoo.addons.base.maintenance.migrations import util

_logger = logging.getLogger(__name__)

MODULES_TO_UNINSTALL = [
    "account_date_filters",
]


def migrate(cr, version):
    for module_name in MODULES_TO_UNINSTALL:
        if not util.module_installed(cr, module_name):
            _logger.debug("Module %s is not installed, skipping.", module_name)
            continue
        util.uninstall_module(cr, module_name)
        _logger.info("Uninstalled module %s.", module_name)
