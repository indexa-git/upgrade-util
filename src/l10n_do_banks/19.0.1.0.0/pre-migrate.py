import logging

from odoo.addons.base.maintenance.migrations import util

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # The v17 template payment.token_form used <div t-call="payment.form_logo">
    # directly; v19 changed it to <div><t t-call="payment.form_logo"/></div>.
    # The DB has a stale azul_token_form_logo record with noupdate=True that
    # still targets the old xpath //div[@t-call='payment.form_logo']. Remove it
    # so Odoo recreates it from XML with the correct v19 xpath on next update.
    util.remove_view(cr, xml_id="payment_azul_webservices.azul_token_form_logo")
    _logger.info("payment_azul_webservices: removed stale azul_token_form_logo view")
