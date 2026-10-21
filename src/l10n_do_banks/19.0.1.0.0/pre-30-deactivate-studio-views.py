import logging

_logger = logging.getLogger(__name__)

STUDIO_MODULE = 'studio_customization'


def migrate(cr, version):
    if not version:
        return

    cr.execute(
        """
        UPDATE ir_ui_view v
           SET active = FALSE
          FROM ir_model_data d
         WHERE d.model = 'ir.ui.view'
           AND d.module = %s
           AND d.res_id = v.id
           AND v.active
        RETURNING v.id, v.model, v.name
        """,
        (STUDIO_MODULE,),
    )
    rows = cr.fetchall()

    _logger.info("Deactivated %s Studio views", len(rows))
    for view_id, model, name in sorted(rows, key=lambda row: (row[1] or '', row[0])):
        _logger.info("  [%s] %s: %s", view_id, model, name)
