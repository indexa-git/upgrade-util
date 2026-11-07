import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

BATCH_SIZE = 500


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    if "qty_delivered" not in env["pos.order.line"]._fields:
        return

    cr.execute(
        """
        SELECT pos_order.id
          FROM pos_order
         WHERE pos_order.state IN ('paid', 'done')
           AND pos_order.shipping_date IS NOT NULL
           AND EXISTS (
               SELECT 1
                 FROM pos_order_line line
                WHERE line.order_id = pos_order.id
                  AND line.qty_delivered IS NULL
           )
           AND EXISTS (
               SELECT 1
                 FROM stock_picking picking
                 JOIN stock_picking_type picking_type ON picking_type.id = picking.picking_type_id
                WHERE picking.pos_order_id = pos_order.id
                  AND picking.state = 'done'
                  AND picking_type.code = 'outgoing'
           )
      ORDER BY pos_order.id
        """
    )
    order_ids = [order_id for (order_id,) in cr.fetchall()]
    field = env["pos.order.line"]._fields["qty_delivered"]
    total = len(order_ids)
    for offset in range(0, total, BATCH_SIZE):
        lines = env["pos.order.line"].search([("order_id", "in", order_ids[offset : offset + BATCH_SIZE])])
        env.add_to_compute(field, lines)
        lines.flush_recordset(["qty_delivered"])
        env.invalidate_all()
        _logger.info(
            "pos_order_line.qty_delivered recomputed for ship-later orders: %s/%s",
            min(offset + BATCH_SIZE, total),
            total,
        )
