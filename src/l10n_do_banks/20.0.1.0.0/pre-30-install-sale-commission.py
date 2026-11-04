"""Install the 20.0 commission modules that receive the data of account_payment_compensation.

account_payment_compensation and account_payment_compensation_news are not ported to 20.0. Their history moves to
sale_commission_payout in ``end-30-migrate-compensation-data.py``, which needs the new models by the end stage:

    account_payment_compensation       -> sale_commission_payout
    account_payment_compensation_news  -> sale_commission_payout_l10n_do

Commission plans are not migrated, so nothing else is installed: each client configures its plans after the
upgrade. Modules set to install here are loaded in a later pass of the same upgrade, before the end stage.
"""

import logging

from odoo.upgrade import util

# The public util.force_install_module only works from the pre/post scripts of base: called from here during a
# major upgrade it raises MigrationError, because the auto discovery already ran. The strict implementation sets
# the module and its dependencies to install right away.
from odoo.upgrade.util.modules import _force_install_module

_logger = logging.getLogger(__name__)

_REPLACEMENTS = [
    ("account_payment_compensation", "sale_commission_payout"),
    ("account_payment_compensation_news", "sale_commission_payout_l10n_do"),
]


def migrate(cr, version):
    for old_module, new_module in _REPLACEMENTS:
        if not util.module_installed(cr, old_module):
            continue
        cr.execute("SELECT 1 FROM ir_module_module WHERE name = %s", [new_module])
        if not cr.rowcount:
            _logger.error(
                "%r is not in the addons path: the data of %r cannot be migrated and is kept.",
                new_module,
                old_module,
            )
            continue
        _force_install_module(cr, new_module, reason=f"it receives the data of {old_module}")
