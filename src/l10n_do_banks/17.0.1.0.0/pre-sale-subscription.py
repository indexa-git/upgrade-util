import logging

_logger = logging.getLogger(__name__)


def fix_sale_orders(cr):
    """
    Find and fix sale_order records with invalid next_invoice_date.

    This function searches for all sale_order records where:
      - start_date IS NOT NULL
      - next_invoice_date IS NOT NULL
      - next_invoice_date < start_date
      - subscription_state = '6_churn'
    For each such record, it sets next_invoice_date to NULL (or could be set to start_date if required).

    Parameters:
        cr: Odoo database cursor

    Side effects:
        Updates the next_invoice_date field in the sale_order table for affected records.
        Logs actions and findings for traceability.
    """
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
    sale_order_ids = [sale_order_id for sale_order_id, _, _ in rows]
    _logger.info(
        "Fixing %d sale orders: Setting next_invoice_date to NULL for ids %s.",
        len(sale_order_ids), sale_order_ids
    )
    cr.execute(
        """
        UPDATE sale_order
           SET next_invoice_date = NULL
         WHERE id IN %s
        """,
        (tuple(sale_order_ids),)
    )


def migrate(cr, version):
    """
    Migration entrypoint for fixing invalid next_invoice_date in sale_order records.

    Parameters:
        cr: Odoo database cursor
        version: Target version for the migration (unused)

    Side effects:
        Calls fix_sale_orders to perform the corrective update.
    """
    fix_sale_orders(cr)
