from odoo.addons.base.maintenance.migrations import util
import logging

_logger = logging.getLogger(__name__)


def reinstall_modules(cr):
    modules_to_install = [
        'web_favicon',
    ]

    for module_name in modules_to_install:
        if util.module_installed(cr, module_name):
            _logger.info("Module already installed: %s", module_name)
            continue
        util.force_install_module(cr, module_name)
        _logger.info("Module reinstalled: %s", module_name)


def migrate(cr, version):
    reinstall_modules(cr)

