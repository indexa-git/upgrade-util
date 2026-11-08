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
    if (
        not _pos_sale_installs_over(cr, "sale")
        or util.column_exists(cr, "sale_order", "amount_unpaid")
        or util.column_exists(cr, "pos_order_line", "sale_order_line_id")
    ):
        return

    util.create_column(cr, "sale_order", "amount_unpaid", "numeric")
    cr.execute(
        """
        WITH paid_tx AS (
            SELECT rel.sale_order_id AS order_id, tx.id AS tx_id, tx.amount
              FROM sale_order_transaction_rel rel
              JOIN payment_transaction tx ON tx.id = rel.transaction_id
             WHERE tx.state IN ('authorized', 'done')
        ),
        tx_paid AS (
            SELECT order_id, SUM(amount) AS amount
              FROM paid_tx
          GROUP BY order_id
        ),
        invoice_lines AS (
            SELECT DISTINCT sol.order_id, aml.id, aml.price_total, aml.balance
              FROM sale_order_line sol
              JOIN sale_order_line_invoice_rel rel ON rel.order_line_id = sol.id
              JOIN account_move_line aml ON aml.id = rel.invoice_line_id
             WHERE aml.parent_state IN ('draft', 'posted')
               AND NOT EXISTS (
                   SELECT 1
                     FROM paid_tx
                     JOIN account_invoice_transaction_rel itx ON itx.transaction_id = paid_tx.tx_id
                    WHERE paid_tx.order_id = sol.order_id
                      AND itx.invoice_id = aml.move_id
               )
        ),
        invoiced AS (
            SELECT order_id,
                   SUM(CASE WHEN balance >= 0 THEN -ABS(price_total) ELSE ABS(price_total) END) AS amount
              FROM invoice_lines
          GROUP BY order_id
        )
        UPDATE sale_order so
           SET amount_unpaid = GREATEST(
                   CASE
                       WHEN cur.rounding > 0
                       THEN ROUND(
                           (COALESCE(base.amount_total, 0) - COALESCE(invoiced.amount, 0) - COALESCE(tx_paid.amount, 0))
                           / cur.rounding
                       ) * cur.rounding
                       ELSE COALESCE(base.amount_total, 0) - COALESCE(invoiced.amount, 0) - COALESCE(tx_paid.amount, 0)
                   END,
                   0
               )
          FROM sale_order base
     LEFT JOIN res_currency cur ON cur.id = base.currency_id
     LEFT JOIN invoiced ON invoiced.order_id = base.id
     LEFT JOIN tx_paid ON tx_paid.order_id = base.id
         WHERE so.id = base.id
        """
    )
    _logger.info("sale_order.amount_unpaid prefilled in SQL for %s orders", cr.rowcount)
