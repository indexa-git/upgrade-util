"""Create the UAE work entry types that `hr_work_entry_attendance` references.

That module is `auto_install` and its overtime rules point at those types with plain
`ref` attributes and no `forcecreate="0"`, so a missing one aborts the whole registry.
The types ship in `hr_work_entry`'s data, but that file is only replayed when the
module is updated, which never happens on a database `upgrade.odoo.com` already
brought to 19.0 with an older source.
"""

import logging

from odoo.addons.base.maintenance.migrations import util

_logger = logging.getLogger(__name__)

# Mirrors hr_work_entry/data/hr_work_entry_type_data.xml. `code` is required and unique
# per country, so it has to match the core definitions.
WORK_ENTRY_TYPES = (
    ("uae_work_entry_type_overtime_work_days_daytime", "Overtime Weekdays Daytime", "OVTWD", 1.25),
    ("uae_work_entry_type_overtime_work_days_nighttime", "Overtime Weekdays Nighttime", "OVTWDN", 1.5),
    ("uae_work_entry_type_overtime_off_days", "Overtime Off-days", "OVTOD", 1.5),
)


def migrate(cr, version):
    country_id = util.ref(cr, "base.ae")

    for name, label, code, amount_rate in WORK_ENTRY_TYPES:
        if util.ref(cr, f"hr_work_entry.{name}"):
            continue

        # `name` is translated, hence jsonb. `round_days` / `round_days_type` are NOT NULL
        # with no default and absent from the core XML (the ORM fills them from the field
        # defaults), so they are borrowed from an existing row rather than hardcoded.
        cr.execute(
            """
            WITH defaults AS (
                SELECT round_days, round_days_type FROM hr_work_entry_type ORDER BY id LIMIT 1
            ), new_type AS (
                INSERT INTO hr_work_entry_type
                            (name, code, country_id, amount_rate, is_extra_hours, is_leave,
                             active, sequence, round_days, round_days_type,
                             create_uid, write_uid, create_date, write_date)
                     SELECT jsonb_build_object('en_US', %s), %s, %s, %s, TRUE, FALSE,
                            TRUE, 25, d.round_days, d.round_days_type,
                            1, 1, now(), now()
                       FROM defaults d
                  RETURNING id
            )
            INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
                 SELECT 'hr_work_entry', %s, 'hr.work.entry.type', id, TRUE FROM new_type
            """,
            [label, code, country_id, amount_rate, name],
        )
        if cr.rowcount:
            _logger.info("Created hr_work_entry.%s (%s)", name, code)
        else:
            _logger.warning("Could not create hr_work_entry.%s: hr_work_entry_type is empty.", name)
