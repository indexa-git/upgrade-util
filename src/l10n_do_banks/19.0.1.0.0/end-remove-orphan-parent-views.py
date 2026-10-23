import logging

from odoo.upgrade import util

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    registry = util.env(cr).registry
    modules = tuple(registry.updated_modules)
    if not modules:
        return

    cr.execute(
        """
        SELECT d.module || '.' || d.name
          FROM ir_model_data d
         WHERE d.model = 'ir.ui.view'
           AND d.module IN %s
           AND NOT COALESCE(d.noupdate, false)
           AND EXISTS (SELECT 1 FROM ir_ui_view c WHERE c.inherit_id = d.res_id)
           AND NOT EXISTS (
                   SELECT 1
                     FROM ir_model_data o
                    WHERE o.model = 'ir.ui.view'
                      AND o.res_id = d.res_id
                      AND o.id != d.id
               )
         ORDER BY d.id DESC
        """,
        [modules],
    )
    orphan_xmlids = [xmlid for (xmlid,) in cr.fetchall() if xmlid not in registry.loaded_xmlids]
    for xmlid in orphan_xmlids:
        _logger.info("removing view %s and its descendants before _process_end", xmlid)
        util.remove_view(cr, xmlid)
