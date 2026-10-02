import logging

from odoo.addons.base.maintenance.migrations import util

_logger = logging.getLogger(__name__)

_DISCOUNT_FIELDS = ["discount_total", "price_total_no_discount"]


def retire_oca_invoice_discount(cr):
    if not util.module_installed(cr, "account_invoice_discount_display_amount"):
        return
    util.remove_view(
        cr, xml_id="account_invoice_discount_display_amount.invoice_discount_display_amount_document", silent=True
    )
    for field in _DISCOUNT_FIELDS:
        util.remove_field(cr, "account.move.line", field)
        util.remove_column(cr, "account_move", field)
    util.force_install_module(
        cr, "l10n_do_accounting_invoice_discount_display_amount", if_installed=["l10n_do_accounting"]
    )
    _logger.info("account_invoice_discount_display_amount: retired the OCA 17.0 leftovers")


def migrate(cr, version):
    if not version:
        return

    retire_oca_invoice_discount(cr)

    # The v17 template payment.token_form used <div t-call="payment.form_logo">
    # directly; v19 changed it to <div><t t-call="payment.form_logo"/></div>.
    # The DB has a stale azul_token_form_logo record with noupdate=True that
    # still targets the old xpath //div[@t-call='payment.form_logo']. Remove it
    # so Odoo recreates it from XML with the correct v19 xpath on next update.
    util.remove_view(cr, xml_id="payment_azul_webservices.azul_token_form_logo")
    _logger.info("payment_azul_webservices: removed stale azul_token_form_logo view")
