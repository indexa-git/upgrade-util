"""Freeze the v17 ``sale_pos_backend`` configuration before its tables disappear.

``sale_pos_backend`` (cash registers built on ``sale.order``) is replaced in 19.0
by the native Point of Sale. Its configuration is rebuilt as ``pos.config`` /
``pos.payment.method`` / ``pos.bill`` by ``end-35-migrate-sale-cashier-to-pos``,
but that script needs the ORM of ``point_of_sale`` while the legacy tables are
gone by then. This script bridges both moments:

  1. Copies the legacy tables to ``zz_legacy_*`` (Odoo ignores unknown tables,
     so they survive the upgrade). They are dropped by hand once the migration
     is validated.
  2. Keeps cash register / session traceability on invoices and payments as a
     read-only manual text field ``x_legacy_cashier``.
  3. Forces the install of ``point_of_sale``.

Session history (sessions, cash counts, journal controls) is not migrated.

Pending decision: keeping ``x_legacy_cashier`` is provisional; whether to keep
it, extend it or drop it must be discussed with the client.
"""

import logging

from odoo.upgrade import util

_logger = logging.getLogger(__name__)

_MODULE = "sale_pos_backend"

# Legacy tables read by end-35. The m2m names were checked against a real
# 17.0 database (``payment_id`` / ``refund_id`` are explicit relations).
_TABLES = [
    "sale_cashier",
    "cashbox_template",
    "payment_id",
    "refund_id",
    "product_pricelist_sale_cashier_rel",
    "sale_cashier_stock_warehouse_rel",
    "cashbox_template_sale_cashier_rel",
    "sale_cashier_sale_return_reason_rel",
    "sale_return_reason",
]

_FIELD = "x_legacy_cashier"
_FIELD_LABEL = "Caja / sesión (v17)"
_TRACEABILITY_TABLES = {"account_move": "account.move", "account_payment": "account.payment"}


def migrate(cr, version):
    if not util.module_installed(cr, _MODULE):
        _logger.info("%s is not installed; nothing to snapshot.", _MODULE)
        return

    _snapshot_tables(cr)
    for table, model in _TRACEABILITY_TABLES.items():
        _keep_traceability(cr, table, model)

    util.force_install_module(cr, "point_of_sale")
    _logger.info("point_of_sale forced to install to rebuild the cash registers.")


def _snapshot_tables(cr):
    for table in _TABLES:
        target = f"zz_legacy_{table}"
        if not util.table_exists(cr, table):
            _logger.warning("Legacy table %s not found; skipped.", table)
            continue
        if util.table_exists(cr, target):
            _logger.info("%s already exists; keeping the first snapshot.", target)
            continue
        # Plain copy: the ORM cannot read tables of a module that is going away.
        cr.execute(util.format_query(cr, "CREATE TABLE {} AS SELECT * FROM {}", target, table))
        _logger.info("Snapshot %s -> %s (%d rows).", table, target, cr.rowcount)


def _keep_traceability(cr, table, model):
    if not (util.column_exists(cr, table, "cashier_id") and util.column_exists(cr, table, "session_id")):
        _logger.info("%s has no cashier/session columns; traceability skipped.", table)
        return

    util.create_column(cr, table, _FIELD, "varchar")
    _register_manual_field(cr, model)

    # Bulk UPDATE: ~400k invoices in the biggest client, too many for the ORM.
    cr.execute(
        util.format_query(
            cr,
            """
            UPDATE {table} t
               SET {field} = concat_ws(
                       ' / ',
                       (SELECT c.name FROM sale_cashier c WHERE c.id = t.cashier_id),
                       (SELECT s.name FROM sale_cashier_session s WHERE s.id = t.session_id)
                   )
             WHERE t.cashier_id IS NOT NULL
               AND t.{field} IS NULL
            """,
            table=table,
            field=_FIELD,
        )
    )
    _logger.info("Backfilled %s.%s for %d row(s).", table, _FIELD, cr.rowcount)


def _register_manual_field(cr, model):
    """Expose the column as a manual char field so it can be filtered from the UI."""
    # Same pattern as pre-20: manual fields need the `x_` prefix and a jsonb label.
    cr.execute(
        """
        INSERT INTO ir_model_fields
            (model_id, model, name, field_description, ttype,
             state, store, copied, readonly, required, "index", selectable)
        SELECT m.id, %(model)s, %(name)s,
               jsonb_build_object('en_US', %(label)s, 'es_DO', %(label)s),
               'char', 'manual', TRUE, FALSE, TRUE, FALSE, FALSE, TRUE
          FROM ir_model m
         WHERE m.model = %(model)s
           AND NOT EXISTS (
               SELECT 1 FROM ir_model_fields
                WHERE model = %(model)s AND name = %(name)s
           )
        """,
        {"model": model, "name": _FIELD, "label": _FIELD_LABEL},
    )
