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

import odoo

from odoo.addons.base.maintenance.migrations import util as mig_util
from odoo.upgrade import util

_logger = logging.getLogger(__name__)

_MERGES = [
    ("account_auto_transfer_features", "account_transfer_features"),
    ("payment_azul", "payment_azul_webpages"),
    ("account_reconcile_payment", "l10n_do_account_withholding_tax"),
    ("stock_analytic", "stock_analytic_distribution_features"),
]


_LEFTOVER_CODE_ERROR = (
    "Cannot merge module %(old)r into %(into)r: the code of %(old)r is still in the "
    "addons path of this upgrade.\n"
    "`util.merge_module` deletes the `ir_module_module` row of %(old)r, but Odoo built "
    "the module graph before this script ran, so it still loads %(old)r afterwards. Its "
    "constraint reflection then resolves `module` to NULL and the upgrade dies with:\n"
    '  null value in column "module" of relation "ir_model_constraint" '
    "violates not-null constraint\n"
    "Keep the retired module out of the addons path of the upgrade branch and run "
    "the upgrade again. For `stock_analytic`, that means pinning the "
    "OCA/account-analytic submodule to a commit without it: OCA migrated that "
    "module to 19.0, and it is the very module "
    "`stock_analytic_distribution_features` replaces."
)


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
    on_disk = set(odoo.modules.get_modules())

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
        if old_module in on_disk:
            # The graph of this upgrade already holds `old_module` as a node, so deleting
            # its module row here makes the later `init_models` reflect constraints with
            # a NULL module. Fail loud and early instead.
            raise util.MigrationError(_LEFTOVER_CODE_ERROR % {"old": old_module, "into": into_module})
        util.merge_module(cr, old_module, into_module)
        _logger.info("Module merged: %r → %r", old_module, into_module)

    if util.force_noupdate(cr, "payment_azul_webpages.payment_method_azul"):
        _logger.info("Kept legacy Azul payment method: xmlid flagged noupdate")
