"""
Pre-migration: Fix constraint violations that would block schema updates.

1. ir_cron_check_strictly_positive_interval
   Rows with interval_number <= 0 violate the check added in v19.

2. hr_resume_line_date_check
   Resume lines where date_start > date_end violate the date ordering check.

3. helpdesk_ticket.x_partner_company NOT NULL
   Custom studio field has null values; set to empty string before constraint
   is enforced.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _fix_cron_interval(cr)
    _fix_resume_line_dates(cr)
    _fix_helpdesk_x_partner_company(cr)


def _fix_cron_interval(cr):
    cr.execute("""
        SELECT COUNT(*) FROM ir_cron WHERE interval_number <= 0
    """)
    count = cr.fetchone()[0]
    if not count:
        return
    cr.execute("""
        UPDATE ir_cron SET interval_number = 1 WHERE interval_number <= 0
    """)
    _logger.info(
        "pre-fix-constraints: set interval_number=1 on %d cron(s) with non-positive interval",
        cr.rowcount,
    )


def _fix_resume_line_dates(cr):
    cr.execute("""
        SELECT COUNT(*) FROM hr_resume_line
        WHERE date_start IS NOT NULL
          AND date_end IS NOT NULL
          AND date_start > date_end
    """)
    count = cr.fetchone()[0]
    if not count:
        return
    # Swap dates so date_start <= date_end
    cr.execute("""
        UPDATE hr_resume_line
        SET date_start = date_end,
            date_end   = date_start
        WHERE date_start IS NOT NULL
          AND date_end IS NOT NULL
          AND date_start > date_end
    """)
    _logger.info(
        "pre-fix-constraints: swapped date_start/date_end on %d hr.resume.line record(s)",
        cr.rowcount,
    )


def _fix_helpdesk_x_partner_company(cr):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'helpdesk_ticket'
          AND column_name = 'x_partner_company'
    """)
    if not cr.fetchone():
        return

    cr.execute("""
        SELECT COUNT(*) FROM helpdesk_ticket WHERE x_partner_company IS NULL
    """)
    count = cr.fetchone()[0]
    if not count:
        return

    cr.execute("""
        UPDATE helpdesk_ticket SET x_partner_company = '' WHERE x_partner_company IS NULL
    """)
    _logger.info(
        "pre-fix-constraints: set x_partner_company='' on %d helpdesk_ticket row(s)",
        cr.rowcount,
    )
