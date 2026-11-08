import logging

from odoo.upgrade import util

_logger = logging.getLogger(__name__)


def _pos_sale_installs_over(cr, module):
    cr.execute(
        """
        SELECT 1
          FROM ir_module_module pos_sale
          JOIN ir_module_module base_module ON base_module.name = %s
         WHERE pos_sale.name = 'pos_sale'
           AND pos_sale.state = 'to install'
           AND base_module.state IN ('installed', 'to upgrade')
        """,
        [module],
    )
    return bool(cr.rowcount)


def migrate(cr, version):
    if not _pos_sale_installs_over(cr, "point_of_sale") or util.column_exists(cr, "pos_order_line", "qty_delivered"):
        return

    util.create_column(cr, "pos_order_line", "qty_delivered", "float8")
    cr.execute(
        """
        WITH shipped_order AS (
            SELECT DISTINCT picking.pos_order_id AS order_id
              FROM stock_picking picking
              JOIN stock_picking_type picking_type ON picking_type.id = picking.picking_type_id
             WHERE picking.pos_order_id IS NOT NULL
               AND picking.state = 'done'
               AND picking_type.code = 'outgoing'
        )
        UPDATE pos_order_line line
           SET qty_delivered = CASE
                   WHEN pos_order.state IN ('paid', 'done', 'invoiced') AND shipped_order.order_id IS NOT NULL
                   THEN line.qty
                   ELSE 0
               END
          FROM pos_order pos_order
     LEFT JOIN shipped_order ON shipped_order.order_id = pos_order.id
         WHERE line.order_id = pos_order.id
           AND NOT (
               pos_order.state IN ('paid', 'done', 'invoiced')
               AND pos_order.shipping_date IS NOT NULL
               AND shipped_order.order_id IS NOT NULL
           )
        """
    )
    _logger.info("pos_order_line.qty_delivered prefilled in SQL for %s lines", cr.rowcount)
