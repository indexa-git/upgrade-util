import logging

from odoo.modules.module import get_module_path

from odoo.addons.base.maintenance.migrations import util

_logger = logging.getLogger(__name__)

MODULE_MAP = {
    "operating_unit": "operating_unit_base",
    "stock_operating_unit": "stock_operating_unit_segregation",
    "pos_operating_unit": "pos_operating_unit_visibility",
    "analytic_operating_unit": "analytic_operating_unit_segregation",
}


def migrate(cr, version):
    if not util.module_installed(cr, "operating_unit"):
        return

    installed = [old for old in MODULE_MAP if util.module_installed(cr, old)]
    missing_code = [MODULE_MAP[old] for old in installed if not get_module_path(MODULE_MAP[old], display_warning=False)]
    if missing_code:
        _logger.warning("Operating unit modules not replaced, code not found for: %s", ", ".join(missing_code))
        return

    blockers = _installed_dependers(cr, installed)
    if blockers:
        _logger.warning(
            "Operating unit modules not replaced, other installed modules depend on them: %s", ", ".join(blockers)
        )
        return

    for old in installed:
        new = MODULE_MAP[old]
        cr.execute("DELETE FROM ir_module_module WHERE name = %s AND state = 'uninstalled'", [new])
        cr.execute(
            "DELETE FROM ir_model_data WHERE module = 'base' AND model = 'ir.module.module' AND name = %s",
            ["module_" + new],
        )
        util.rename_module(cr, old, new)
        _logger.info("Module %s replaced by %s", old, new)


def _installed_dependers(cr, modules):
    cr.execute(
        """
        SELECT DISTINCT m.name
          FROM ir_module_module_dependency d
          JOIN ir_module_module m ON m.id = d.module_id
         WHERE d.name IN %s
           AND m.name NOT IN %s
           AND m.state IN ('installed', 'to upgrade', 'to install')
      ORDER BY m.name
        """,
        [tuple(modules), tuple(MODULE_MAP)],
    )
    return [name for (name,) in cr.fetchall()]
