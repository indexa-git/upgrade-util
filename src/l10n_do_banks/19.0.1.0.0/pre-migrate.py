import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # Reset noupdate on payment.token_form so Odoo reloads its arch from the
    # Odoo 19 source file. In v17 the template used <div t-call="payment.form_logo">
    # directly; in v19 it changed to <div><t t-call="payment.form_logo"/></div>.
    # Without this reset the stale arch stays in the DB and the xpath
    # //div[t[@t-call='payment.form_logo']] in our inherited view fails.
    cr.execute("""
        UPDATE ir_model_data
        SET noupdate = FALSE
        WHERE module = 'payment'
          AND name = 'token_form'
          AND model = 'ir.ui.view'
    """)
    _logger.info(
        "payment_azul_webservices: reset noupdate on payment.token_form (%d row)",
        cr.rowcount,
    )
