"""Rebuild the closed v17 ``sale_pos_backend`` sessions as closed ``pos.session``.

Runs after ``end-35-migrate-sale-cashier-to-pos`` (it needs the cash register
-> ``pos.config`` map) and reads the ``zz_legacy_*`` snapshot taken by
``pre-35-snapshot-sale-cashier``.

Only existing records are linked; nothing else is created:
  * one closed ``pos.session`` per closed v17 session, with no journal entry,
    no cash lines and no orders (v17 accounting already exists);
  * ``account.payment.pos_session_id`` on the payments whose journal entry
    carried the v17 session. Payments without that link stay unlinked.

The v17 cash collections go to ``cash_real_transaction`` so that the native
expected balance and difference of a closed session show the v17 figures, and
the per-currency closing figures are written to ``closing_notes``.

Sessions are inserted in SQL: the ORM opens a session on create and refuses a
start date before the lock date. Re-running is safe: migrated sessions are
skipped.
"""

import logging
from collections import defaultdict

from odoo.upgrade import util

_logger = logging.getLogger(__name__)

_CONFIG_MAP = "zz_legacy_cashier_pos_config_map"
_SESSION_MAP = "zz_legacy_cashier_session_pos_map"
_PAYMENT_SESSION = "zz_legacy_payment_session"


def migrate(cr, version):
    if not (util.table_exists(cr, "zz_legacy_sale_cashier_session") and util.table_exists(cr, _CONFIG_MAP)):
        _logger.info("No sale_cashier_session snapshot or register map (see pre-35); nothing to migrate.")
        return

    cr.execute(
        util.format_query(
            cr, "CREATE TABLE IF NOT EXISTS {} (session_id int PRIMARY KEY, pos_session_id int)", _SESSION_MAP
        )
    )
    _report_skipped(cr)
    created = _insert_sessions(cr)
    if created:
        _write_closing_notes(cr, created)
    _link_payments(cr)


def _report_skipped(cr):
    cr.execute(
        util.format_query(
            cr,
            """
            SELECT count(*) FILTER (WHERE s.state != 'closed'),
                   count(*) FILTER (WHERE s.state = 'closed' AND m.pos_config_id IS NULL)
              FROM zz_legacy_sale_cashier_session s
              LEFT JOIN {} m ON m.cashier_id = s.cashier_id
            """,
            _CONFIG_MAP,
        )
    )
    not_closed, no_config = cr.fetchone()
    if not_closed:
        _logger.warning(
            "%d v17 session(s) not closed were NOT migrated: close them in 17.0 before the upgrade.", not_closed
        )
    if no_config:
        _logger.warning("%d closed v17 session(s) skipped: their cash register has no pos.config.", no_config)


def _insert_sessions(cr):
    """Insert the closed sessions not migrated yet; return {pos.session id: v17 session id}."""
    # The cash journal is the one of the register's cash payment method, as
    # pos.session._compute_cash_journal would set it.
    cr.execute(
        util.format_query(
            cr,
            """
            WITH cash_journal AS (
                SELECT DISTINCT ON (r.pos_config_id) r.pos_config_id, pm.journal_id
                  FROM pos_config_pos_payment_method_rel r
                  JOIN pos_payment_method pm ON pm.id = r.pos_payment_method_id
                  JOIN account_journal j ON j.id = pm.journal_id
                 WHERE j.type = 'cash'
                 ORDER BY r.pos_config_id, pm.id
            ), legacy AS MATERIALIZED (
                -- The new id is reserved here so the v17 -> v19 map needs no join back.
                SELECT s.*, cm.pos_config_id, nextval('pos_session_id_seq') AS new_id
                  FROM zz_legacy_sale_cashier_session s
                  JOIN {config_map} cm ON cm.cashier_id = s.cashier_id
                 WHERE s.state = 'closed'
                   AND NOT EXISTS (SELECT 1 FROM {session_map} sm WHERE sm.session_id = s.id)
            ), inserted AS (
                INSERT INTO pos_session (
                    id, config_id, user_id, name, state, start_at, stop_at,
                    cash_journal_id, cash_register_balance_start, cash_real_transaction,
                    cash_register_balance_end_real, rescue, update_stock_at_closing,
                    create_uid, create_date, write_uid, write_date
                )
                -- A closed session needs both dates: pos.config sorts by stop_at desc
                -- (NULLs first) and crashes on a missing one. Some v17 sessions lack them.
                SELECT l.new_id, l.pos_config_id, l.user_id, l.name, 'closed',
                       coalesce(l.opening_date, l.create_date),
                       coalesce(l.closing_date, l.write_date, l.opening_date, l.create_date),
                       cj.journal_id, coalesce(l.cash_register_opening_balance, 0),
                       coalesce(l.cash_register_balance_current, 0),
                       b.cash_register_balance_end, false, false,
                       l.create_uid, l.create_date, l.write_uid, l.write_date
                  FROM legacy l
                  LEFT JOIN cash_journal cj ON cj.pos_config_id = l.pos_config_id
                  -- Counted cash in the company currency; other currencies go to the notes.
                  LEFT JOIN res_company c ON c.id = l.company_id
                  LEFT JOIN LATERAL (
                      SELECT bl.cash_register_balance_end
                        FROM zz_legacy_sale_cashier_session_balance bl
                       WHERE bl.sale_session_id = l.id AND bl.currency_id = c.currency_id
                       ORDER BY bl.id
                       LIMIT 1
                  ) b ON true
                RETURNING id
            )
            INSERT INTO {session_map} (session_id, pos_session_id)
            SELECT l.id, l.new_id
              FROM legacy l
              JOIN inserted i ON i.id = l.new_id
            RETURNING pos_session_id, session_id
            """,
            config_map=_CONFIG_MAP,
            session_map=_SESSION_MAP,
        )
    )
    created = dict(cr.fetchall())
    _logger.info("Migrated %d closed v17 session(s) to pos.session.", len(created))
    return created


def _write_closing_notes(cr, created):
    """Write the per-currency v17 closing figures, which 19.0 has no field for."""
    if not util.table_exists(cr, "zz_legacy_sale_cashier_session_balance"):
        return
    cr.execute(
        """
        SELECT b.sale_session_id, cur.name, coalesce(b.cash_register_opening_balance, 0),
               coalesce(b.cash_register_balance_current, 0), coalesce(b.cash_register_balance_end, 0),
               coalesce(b.cash_register_difference, 0)
          FROM zz_legacy_sale_cashier_session_balance b
          JOIN res_currency cur ON cur.id = b.currency_id
         WHERE b.sale_session_id = ANY(%s)
         ORDER BY b.sale_session_id, cur.name
        """,
        [list(created.values())],
    )
    notes = defaultdict(list)
    for session_id, currency, opening, cash, counted, difference in cr.fetchall():
        notes[session_id].append(
            f"{currency}: apertura {opening:,.2f} · efectivo cobrado {cash:,.2f} · "
            f"contado {counted:,.2f} · diferencia {difference:,.2f}"
        )
    pos_by_legacy = {legacy: pos for pos, legacy in created.items()}
    rows = [(pos_by_legacy[sid], "Cierre v17\n" + "\n".join(lines)) for sid, lines in notes.items()]
    if rows:
        cr.execute(
            """
            UPDATE pos_session s SET closing_notes = v.note
              FROM unnest(%s::int[], %s::text[]) AS v(id, note)
             WHERE s.id = v.id
            """,
            [[r[0] for r in rows], [r[1] for r in rows]],
        )
    _logger.info("Wrote v17 closing figures on %d session(s).", len(rows))


def _link_payments(cr):
    if not util.table_exists(cr, _PAYMENT_SESSION):
        _logger.warning("No payment -> session snapshot; payments are not linked to the sessions.")
        return
    cr.execute(
        util.format_query(
            cr,
            """
            UPDATE account_payment p
               SET pos_session_id = sm.pos_session_id
              FROM {payment_session} ps
              JOIN {session_map} sm ON sm.session_id = ps.session_id
             WHERE p.id = ps.payment_id
               AND p.pos_session_id IS NULL
            """,
            payment_session=_PAYMENT_SESSION,
            session_map=_SESSION_MAP,
        )
    )
    _logger.info("Linked %d payment(s) to their migrated session.", cr.rowcount)
