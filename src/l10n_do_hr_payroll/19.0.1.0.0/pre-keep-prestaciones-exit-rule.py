import logging

from odoo.addons.base.maintenance.migrations import util

_logger = logging.getLogger(__name__)

# v19 removed the "Prestaciones" exit rule and its structure from the data XML.
# At the end of the upgrade Odoo deletes module records that are no longer
# defined in XML (unless noupdate=True). On databases where payslips were
# computed with this rule, hr_payslip_line rows still reference it and the
# deletion aborts the upgrade. The structure must be kept too: hr.salary.rule
# cascades on struct_id, so deleting the structure would drag the rule with it.
_KEEP_XML_IDS = (
    "l10n_do_hr_payroll.hr_rule_employee_exit",
    "l10n_do_hr_payroll.hr_payroll_structure_exit",
)


def migrate(cr, version):
    if not version:
        return

    for xml_id in _KEEP_XML_IDS:
        util.force_noupdate(cr, xml_id, noupdate=True)
        _logger.info("Marked %s as noupdate to survive the v19 data cleanup", xml_id)
