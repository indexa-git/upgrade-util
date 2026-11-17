import logging

from odoo.modules.module import get_module_path

from odoo.upgrade import util

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
        cr.execute("UPDATE ir_module_module SET state = 'to upgrade' WHERE name = %s", [new])
        _logger.info("Module %s replaced by %s", old, new)

    if _registry_reload_is_scheduled(cr):
        logging.getLogger("odoo.modules.loading").addFilter(
            _PendingUpgradeIsExpected(MODULE_MAP[old] for old in installed)
        )


def _registry_reload_is_scheduled(cr):
    cr.execute("SELECT 1 FROM ir_module_module WHERE state = 'to remove' LIMIT 1")
    return bool(cr.rowcount)


class _PendingUpgradeIsExpected(logging.Filter):
    def __init__(self, modules):
        super().__init__()
        self.modules = set(modules)

    def filter(self, record):
        pending = record.args[0] if isinstance(record.args, tuple) and record.args else None
        if (
            record.levelno == logging.ERROR
            and "inconsistent states" in str(record.msg)
            and isinstance(pending, list)
            and set(pending) <= self.modules
        ):
            record.levelno = logging.WARNING
            record.levelname = logging.getLevelName(logging.WARNING)
        return True


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
