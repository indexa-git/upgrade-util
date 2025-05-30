import logging

_logger = logging.getLogger(__name__)


def fix_sale_orders(cr):
    query = """
        SELECT id, start_date, next_invoice_date
        FROM sale_order
        WHERE start_date IS NOT NULL
          AND next_invoice_date IS NOT NULL
          AND next_invoice_date < start_date
          AND subscription_state = '6_churn'
    """
    cr.execute(query)
    rows = cr.fetchall()
    if not rows:
        _logger.info(
            "No sale orders found with next_invoice_date before start_date and state '6_churn'."
        )
        return
    _logger.info("Found %d sale orders to fix.", len(rows))
    for sale_order_id, start_date, next_invoice_date in rows:
        _logger.info(
            "Fixing sale_order id=%s: next_invoice_date (%s) < start_date (%s). "
            "Setting next_invoice_date to NULL.",
            sale_order_id, next_invoice_date, start_date
        )
        cr.execute(
            """
            UPDATE sale_order
               SET next_invoice_date = NULL
             WHERE id = %s
            """,
            (sale_order_id,)
        )


def migrate(cr, version):
    fix_sale_orders(cr)
