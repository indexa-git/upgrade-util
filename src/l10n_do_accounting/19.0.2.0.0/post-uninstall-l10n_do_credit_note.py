import logging

from odoo.addons.base.maintenance.migrations import util

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Uninstall l10n_do_credit_note, merged into l10n_do_accounting.

    Runs as a post-script: by then l10n_do_accounting 19.0.2.0.0 already owns
    the company fields absorbed from the module (l10n_do_fiscal_position_id,
    l10n_do_day_months, credit_note_company_currency), so the uninstall keeps
    their columns and values.
    """
    module_name = "l10n_do_credit_note"
    if util.module_installed(cr, module_name):
        _logger.info("Uninstalling module: %s", module_name)
        util.uninstall_module(cr, module_name)
        _logger.info("Successfully uninstalled module: %s", module_name)
    else:
        _logger.info("Module %s is not installed, skipping.", module_name)
