import logging

from odoo.addons.base.maintenance.migrations import util

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info("Starting pre-XML-ID-rename migration for banks XML-IDs.")

    if not util.module_installed(cr, "bpd_payroll_txt"):
        _logger.info("Module 'bpd_payroll_txt' not installed; skipping XML ID renames.")
        return
        try:
            util.rename_xmlid(cr, "bpd_payroll_txt.bank_asoc_popular", "l10n_do_banks.bank_asoc_popular", on_collision="merge")
            util.rename_xmlid(cr, "bpd_payroll_txt.bank_bdi",          "l10n_do_banks.bank_bdi",          on_collision="merge")
            util.rename_xmlid(cr, "bpd_payroll_txt.bank_bhd",          "l10n_do_banks.bank_bhd",          on_collision="merge")
            util.rename_xmlid(cr, "bpd_payroll_txt.bank_caribe",       "l10n_do_banks.bank_caribe",       on_collision="merge")
            util.rename_xmlid(cr, "bpd_payroll_txt.bank_citibank",     "l10n_do_banks.bank_citibank",     on_collision="merge")
            util.rename_xmlid(cr, "bpd_payroll_txt.bank_leon",         "l10n_do_banks.bank_leon",         on_collision="merge")
            util.rename_xmlid(cr, "bpd_payroll_txt.bank_lope",         "l10n_do_banks.bank_lope",         on_collision="merge")
            util.rename_xmlid(cr, "bpd_payroll_txt.bank_popular",      "l10n_do_banks.bank_popular",      on_collision="merge")
            util.rename_xmlid(cr, "bpd_payroll_txt.bank_promerica",    "l10n_do_banks.bank_promerica",    on_collision="merge")
            util.rename_xmlid(cr, "bpd_payroll_txt.bank_progreso",     "l10n_do_banks.bank_progreso",     on_collision="merge")
            util.rename_xmlid(cr, "bpd_payroll_txt.bank_reservas",     "l10n_do_banks.bank_reservas",     on_collision="merge")
            util.rename_xmlid(cr, "bpd_payroll_txt.bank_santa_cruz",   "l10n_do_banks.bank_santa_cruz",   on_collision="merge")
            util.rename_xmlid(cr, "bpd_payroll_txt.bank_scotia",       "l10n_do_banks.bank_scotia",       on_collision="merge")
            util.rename_xmlid(cr, "bpd_payroll_txt.bank_vimeca",       "l10n_do_banks.bank_vimeca",       on_collision="merge")
        except Exception as e:
            _logger.error("Error renaming XML-ID: %s", e)
                    
    _logger.info("Pre-XML-ID-rename migration finished.")

