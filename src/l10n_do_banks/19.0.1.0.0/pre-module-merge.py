"""
Pre-migration script for l10n_do_banks 19.0.1.0.0

Merges custom modules into their replacements before the upgrade so that Odoo
can locate all related database records (ir_model_data,
ir_module_module_dependency, view keys, etc.) under the new module names
before any model/view loading takes place.

Merges performed:
  - account_auto_transfer_features → account_transfer_features
  - payment_azul                   → payment_azul_webpages
  - stock_analytic (OCA)           → stock_analytic_distribution_features

Affects (for each merge):
  - ir_module_module          — module registry entry
  - ir_module_module_dependency — downstream module dependencies
  - ir_model_data             — XML IDs owned by the module
  - ir_ui_view.key            — view technical keys (module.xmlid prefix)
"""

import logging

from odoo.addons.base.maintenance.migrations import util as mig_util
from odoo.upgrade import util

_logger = logging.getLogger(__name__)

_MERGES = [
    ("account_auto_transfer_features", "account_transfer_features"),
    ("payment_azul", "payment_azul_webpages"),
    ("account_reconcile_payment", "l10n_do_account_withholding_tax"),
    ("stock_analytic", "stock_analytic_distribution_features"),
]


def _known_modules(cr, names):
    """Return the subset of ``names`` present in ``ir_module_module``."""
    cr.execute("SELECT name FROM ir_module_module WHERE name IN %s", [tuple(names)])
    return {name for (name,) in cr.fetchall()}


def migrate(cr, version):

    # Force-install replacement modules BEFORE merging so that
    # account_reconcile_payment is still in 'installed' state for the checks.
    mig_util.force_upgrade_of_fresh_module(
        cr,
        "l10n_do_account_withholding_tax",
        init=True,
    )
    mig_util.force_install_module(
        cr,
        "l10n_do_withholding_certification",
        if_installed=["l10n_do_account_withholding_tax"],
    )

    known = _known_modules(cr, [module for merge in _MERGES for module in merge])

    for old_module, into_module in _MERGES:
        missing = [module for module in (old_module, into_module) if module not in known]
        if missing:
            _logger.warning(
                "Skipping merge %r → %r: module(s) not in this database: %s",
                old_module,
                into_module,
                ", ".join(missing),
            )
            continue
        util.merge_module(cr, old_module, into_module)
        _logger.info("Module merged: %r → %r", old_module, into_module)
