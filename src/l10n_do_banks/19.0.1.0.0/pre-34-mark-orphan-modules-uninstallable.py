import logging

from odoo.modules.module import get_module_path

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("SELECT name FROM ir_module_module WHERE state = 'uninstalled' ORDER BY name")
    orphans = [name for (name,) in cr.fetchall() if not get_module_path(name, display_warning=False)]
    if not orphans:
        return
    cr.execute(
        "UPDATE ir_module_module SET state = 'uninstallable' WHERE name = ANY(%s)",
        [orphans],
    )
    _logger.info("Marked %d modules without code as uninstallable: %s", len(orphans), ", ".join(orphans))
