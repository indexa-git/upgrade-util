"""
Merge modules whose code is still in the addons path, before Odoo loads anything.

Pass it to `--pre-upgrade-scripts` in the 19.0 upgrade command, and nowhere else:

    odoo -d <db> -u l10n_do_banks \
         --upgrade-path=<...>/upgrade-util/src \
         --pre-upgrade-scripts=<...>/19.0.1.0.0/merge_modules_before_load.py

`util.merge_module` deletes the `ir_module_module` row of the merged module, and that
row has to be gone before Odoo builds the list of modules to load. A module still in
the addons path — such as OCA `stock_analytic`, ported to 19.0 — is already a node of
the graph by the time a regular pre-script runs, so Odoo loads it anyway, reflects its
constraints with no module and dies on `ir_model_constraint.module` being NULL. Merged
from here (`odoo/modules/loading.py`, before any module is loaded) it never enters the
graph: `update_list()` re-creates its row as `uninstalled` without Odoo running its
uninstall, so the columns and their data survive under the destination module.

Modules whose code is gone from the addons path do not need this; they are merged in
`pre-module-merge.py`.

The file name must not start with `pre-`, or Odoo would also run it as a regular
migration script (`odoo/modules/migration.py`), which is the case that fails.
Re-running it is harmless: once merged, the module is gone and the entry is skipped.
"""

import logging

from odoo.modules import get_manifest

from odoo.upgrade import util

_logger = logging.getLogger(__name__)

_MERGES = [
    ("stock_analytic", "stock_analytic_distribution_features"),
]


def _known_modules(cr, names):
    """Return the subset of ``names`` present in ``ir_module_module``."""
    cr.execute("SELECT name FROM ir_module_module WHERE name IN %s", [tuple(names)])
    return {name for (name,) in cr.fetchall()}


def migrate(cr, version):
    known = _known_modules(cr, [module for merge in _MERGES for module in merge])

    for old_module, into_module in _MERGES:
        if old_module not in known:
            _logger.info("%r is not in this database; nothing to merge.", old_module)
            continue

        if into_module not in known:
            manifest = get_manifest(into_module)
            if not manifest:
                _logger.error(
                    "Skipping merge %r → %r: %r is not in the addons path.", old_module, into_module, into_module
                )
                continue
            util.new_module(cr, into_module, deps=manifest["depends"])
            _logger.info("Declared %r ahead of the module list update.", into_module)

        util.merge_module(cr, old_module, into_module)
        _logger.info("Module merged: %r -> %r; %r is left uninstalled.", old_module, into_module, old_module)
