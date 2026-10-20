import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    cr.execute(
        """
        WITH RECURSIVE legacy_views AS (
            SELECT id
              FROM ir_ui_view
             WHERE key = 'website_sale.product'
               AND website_id IS NOT NULL
               AND NOT EXISTS (
                   SELECT 1
                     FROM jsonb_each_text(arch_db) arch
                    WHERE arch.value LIKE '%t-if="is_add_to_cart_possible"%'
               )
            UNION
            SELECT child.id
              FROM ir_ui_view child
              JOIN legacy_views parent ON child.inherit_id = parent.id
        )
        SELECT array_agg(id) FROM legacy_views
        """
    )
    view_ids = cr.fetchone()[0]
    if not view_ids:
        return

    cr.execute("DELETE FROM ir_model_data WHERE model = 'ir.ui.view' AND res_id = ANY(%s)", [view_ids])
    cr.execute("DELETE FROM ir_ui_view WHERE id = ANY(%s)", [view_ids])
    _logger.warning("Deleted 17.0 website copies of website_sale.product and their children: %s", view_ids)
