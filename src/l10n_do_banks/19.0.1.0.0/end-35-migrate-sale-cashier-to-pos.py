"""Rebuild the v17 ``sale_pos_backend`` cash registers as native Point of Sale.

Reads the ``zz_legacy_*`` snapshot taken by ``pre-35-snapshot-sale-cashier`` and
creates, in this order (each step references the previous ones):

    cashbox.template  -> pos.bill            (company-currency values only)
    payment journals  -> pos.payment.method  (one per journal)
    sale.cashier      -> pos.config

Everything that has no native destination is logged as a warning per cash
register, so the report of what the client loses comes from its own data.
Re-running is safe: registers already migrated are skipped.

Pending decisions (the script only reports them; a viable solution must be
found before go-live):
  * Foreign-currency journals and pricelists (USD) are skipped. Native POS
    requires a single currency per register and ``pos_multi_currency`` needs a
    company-currency journal with ``foreign_currency_id``.
  * A cash journal shared by several registers is assigned to the first one
    only (active first, then lowest id): native POS forbids one cash method in
    several registers. Some of these journals are not real cash (withholdings,
    exchange difference) and must be reviewed one by one.

TODO: analyse the employee unarchiving done by ``_ensure_pos_manager_employees``.
It changes client HR data only so ``pos_hr`` does not hit ``hr_employee_user_uniq``
(it would otherwise create a duplicate employee for that user); decide with the
client whether to keep it, or to fix the employees by hand before the upgrade.
"""

import logging

from odoo import Command

from odoo.upgrade import util

_logger = logging.getLogger(__name__)

# Denominations outside this range are opening balances typed as "coins" in v17.
_BILL_MIN = 0.01
_BILL_MAX = 2000.0

# sale.cashier fields with no pos.config equivalent, reported when set.
_LOST_FIELDS = [
    "session_user_id",
    "default_partner_id",
    "account_analytic_id",
    "team_id",
    "operating_unit_id",
    "auto_confirm_picking",
    "delivered_quantities",
    "auto_confirm_return_picking",
    "multi_journal_payment",
    "cash_back",
    "auto_cash_back_modal",
    "can_edit_price_list",
    "can_edit_payment_date",
    "can_edit_memo",
    "payment_authorization_code",
    "account_show_rate",
    "cashier_lots_serials",
    "reason_return_required",
    "journal_control",
    "journal_amount_authorized_diff",
    "specific_credit_note",
    "partial_payments_with_card_bin",
    "l10n_do_receipt_show_lot",
    "cash_control_multi_currency",
    "payment_journal_id",
    "can_use_external_order",
    "can_use_external_moves",
    "cashier_user_id",
    "is_sale_pos_backend_sales_person",
    "link_sales_person",
    "can_return_external_orders",
]

_MAP_TABLE = "zz_legacy_cashier_pos_config_map"


def migrate(cr, version):
    if not util.table_exists(cr, "zz_legacy_sale_cashier"):
        _logger.info("No sale_cashier snapshot; nothing to migrate.")
        return
    env = util.env(cr)
    if "pos.config" not in env:
        _logger.error("point_of_sale is not installed; cash registers cannot be migrated.")
        return

    cr.execute(
        util.format_query(
            cr, "CREATE TABLE IF NOT EXISTS {} (cashier_id int PRIMARY KEY, pos_config_id int)", _MAP_TABLE
        )
    )
    env["stock.warehouse"]._create_missing_pos_picking_types()

    cashiers = _fetch(cr, "SELECT * FROM zz_legacy_sale_cashier ORDER BY active DESC, id")
    cr.execute(util.format_query(cr, "SELECT cashier_id FROM {}", _MAP_TABLE))
    done = {row[0] for row in cr.fetchall()}
    pending = [c for c in cashiers if c["id"] not in done]
    if not pending:
        _logger.info("All %d cash registers already migrated.", len(cashiers))
        return

    if not done:
        _keep_loyalty_out_of_pos(cr, env)
    bills = _migrate_bills(cr, env)
    methods = _PaymentMethods(env)
    _ensure_pos_manager_employees(env, {c["company_id"] for c in pending})
    failed = []
    for cashier in pending:
        # One broken register must not abort the whole upgrade.
        try:
            with util.savepoint(cr):
                _migrate_cashier(cr, env, cashier, bills, methods)
        except Exception:
            _logger.exception("Cash register '%s' (sale.cashier %d) NOT migrated.", cashier["name"], cashier["id"])
            env.invalidate_all(flush=False)
            methods.release(cashier)
            failed.append(cashier["name"])

    _report_refund_reasons(cr)
    _logger.info("Migrated %d cash register(s) to pos.config.", len(pending) - len(failed))
    if failed:
        _logger.error("%d cash register(s) failed and must be created by hand: %s", len(failed), ", ".join(failed))


def _keep_loyalty_out_of_pos(cr, env):
    """Keep the existing loyalty programs out of the new registers, as in v17.

    ``pos_loyalty`` is auto-installed with ``point_of_sale`` and its ``pos_ok``
    column defaults to True, so every sales/website program would apply to all
    registers and block session opening when its reward products are not
    available in PoS.
    """
    if not util.column_exists(cr, "loyalty_program", "pos_ok"):
        return
    # Plain SQL: a flag reset on every program, nothing to recompute.
    cr.execute("UPDATE loyalty_program SET pos_ok = false WHERE pos_ok")
    count = cr.rowcount
    if util.table_exists(cr, "loyalty_program_pos_config_rel"):
        cr.execute("DELETE FROM loyalty_program_pos_config_rel")
    env.invalidate_all(flush=False)
    if count:
        _logger.warning(
            "%d loyalty program(s) taken out of Point of Sale (they never ran in v17 registers);"
            " enable them per register if needed.",
            count,
        )


def _fetch(cr, query, params=None):
    cr.execute(query, params)
    return cr.dictfetchall()


def _rel(cr, table, src, dst, src_id):
    """Ids linked to ``src_id`` in a snapshot m2m table (empty if not snapshotted)."""
    table = f"zz_legacy_{table}"
    if not util.table_exists(cr, table):
        return []
    cr.execute(util.format_query(cr, "SELECT {} FROM {} WHERE {} = %s ORDER BY 1", dst, table, src), [src_id])
    return [row[0] for row in cr.fetchall()]


def _migrate_bills(cr, env):
    """Return ``{cashbox_template_id: pos.bill id}`` for company-currency values in range."""
    if not util.table_exists(cr, "zz_legacy_cashbox_template"):
        return {}
    rows = _fetch(
        cr,
        """
        SELECT t.id, t.value, t.currency_id = c.currency_id AS company_currency
          FROM zz_legacy_cashbox_template t
          JOIN res_company c ON c.id = t.company_id
         WHERE t.sale_session_id IS NULL
        """,
    )
    Bill = env["pos.bill"]
    by_value = {b.value: b.id for b in Bill.search([])}
    mapping, foreign, out_of_range = {}, [], []
    for row in rows:
        value = row["value"]
        if not row["company_currency"]:
            foreign.append(value)
            continue
        if not (_BILL_MIN <= value <= _BILL_MAX):
            out_of_range.append(value)
            continue
        if value not in by_value:
            by_value[value] = Bill.create({"name": f"{value:.2f}", "value": value}).id
        mapping[row["id"]] = by_value[value]
    if foreign:
        _logger.warning(
            "%d foreign-currency denomination(s) not migrated (pos.bill has no currency): %s",
            len(foreign),
            sorted(set(foreign)),
        )
    if out_of_range:
        _logger.warning(
            "%d denomination(s) out of %s-%s not migrated (opening balances, not coins): %s",
            len(out_of_range),
            _BILL_MIN,
            _BILL_MAX,
            sorted(set(out_of_range)),
        )
    return mapping


class _PaymentMethods:
    """Find-or-create one pos.payment.method per journal, tracking cash ownership."""

    def __init__(self, env):
        self.env = env
        self.cash_owner = {}

    def get(self, journal, cashier):
        """Return the method id for ``journal``, or a reason why it cannot be used."""
        if journal.type not in ("cash", "bank"):
            return None, f"journal type {journal.type}"
        if journal.currency_id and journal.currency_id != journal.company_id.currency_id:
            return None, f"foreign currency {journal.currency_id.name}"
        if journal.type == "cash":
            owner = self.cash_owner.setdefault(journal.id, cashier)
            if owner["id"] != cashier["id"]:
                return None, f"cash journal already used by '{owner['name']}'"
        Method = self.env["pos.payment.method"].with_company(journal.company_id).with_context(active_test=False)
        method = Method.search([("journal_id", "=", journal.id)], limit=1)
        if not method:
            method = Method.create(
                {"name": journal.name, "journal_id": journal.id, "company_id": journal.company_id.id}
            )
        return method.id, None

    def release(self, cashier):
        """Free the cash journals claimed by a register whose migration failed."""
        for journal_id, owner in list(self.cash_owner.items()):
            if owner["id"] == cashier["id"]:
                del self.cash_owner[journal_id]


def _ensure_pos_manager_employees(env, company_ids):
    """Unarchive a PoS manager's employee where ``pos_hr`` would otherwise duplicate it.

    On every ``pos.config`` write, ``pos_hr`` creates an employee for a PoS manager
    when none has an active one in the company. ``user.employee_id`` ignores
    archived employees but ``hr_employee_user_uniq`` does not, so an archived
    employee makes every register creation fail.
    """
    if "hr.employee" not in env:
        return
    managers = env.ref("point_of_sale.group_pos_manager").sudo().user_ids
    Employee = env["hr.employee"].sudo().with_context(active_test=False)
    for company in env["res.company"].browse(sorted(company_ids)).exists():
        users = managers.filtered(lambda u, c=company: c in u.company_ids)
        employees = Employee.search([("user_id", "in", users.ids), ("company_id", "=", company.id)])
        if not users or employees.filtered("active"):
            continue
        # TODO: analyse with the client (see module docstring).
        # One is enough: pos_hr only needs a single active manager employee.
        for employee in employees[:1]:
            employee.active = True
            _logger.warning(
                "Employee '%s' (id %d) of PoS manager '%s' unarchived in company '%s': pos_hr needs an"
                " active employee per PoS manager and would otherwise violate hr_employee_user_uniq.",
                employee.name,
                employee.id,
                employee.user_id.login,
                company.name,
            )


def _migrate_cashier(cr, env, cashier, bills, methods):
    name = cashier["name"]
    company = env["res.company"].browse(cashier["company_id"])
    issues = []

    method_ids = []
    for journal_id in _rel(cr, "payment_id", "sale_cashier_id", "account_journal_id", cashier["id"]):
        journal = env["account.journal"].browse(journal_id).exists()
        if not journal:
            continue
        if journal.company_id != company:
            issues.append(f"payment journal '{journal.name}' belongs to another company")
            continue
        method_id, reason = methods.get(journal, cashier)
        if method_id:
            method_ids.append(method_id)
        else:
            issues.append(f"payment journal '{journal.name}' skipped: {reason}")
    if not method_ids:
        issues.append("NO payment method migrated: the register cannot take payments until one is set")

    currency = company.currency_id
    pricelist_ids = _rel(
        cr, "product_pricelist_sale_cashier_rel", "sale_cashier_id", "product_pricelist_id", cashier["id"]
    )
    pricelists = env["product.pricelist"].browse(pricelist_ids).exists()
    foreign = pricelists.filtered(lambda p: p.currency_id != currency)
    if foreign:
        issues.append(f"pricelists skipped (foreign currency): {', '.join(foreign.mapped('name'))}")
    pricelists -= foreign
    default_pricelist = env["product.pricelist"].browse(cashier["pricelist_id"]).exists()
    if default_pricelist and default_pricelist.currency_id != currency:
        default_pricelist = env["product.pricelist"]
    if default_pricelist:
        pricelists |= default_pricelist

    templates = _rel(cr, "cashbox_template_sale_cashier_rel", "sale_cashier_id", "cashbox_template_id", cashier["id"])
    vals = {
        "name": name,
        "active": cashier["active"],
        "company_id": company.id,
        "journal_id": env["account.journal"].with_company(company)._ensure_company_account_journal().id,
        "payment_method_ids": [Command.set(method_ids)],
        "use_pricelist": bool(pricelists),
        "pricelist_id": (default_pricelist or pricelists[:1]).id,
        "available_pricelist_ids": [Command.set(pricelists.ids)],
        "set_maximum_difference": bool(cashier["amount_authorized_diff"]),
        "amount_authorized_diff": cashier["amount_authorized_diff"] or 0.0,
        "module_pos_hr": bool(cashier.get("use_generic_users")),
        "default_bill_ids": [Command.set(sorted({bills[t] for t in templates if t in bills}))],
    }

    invoice_journal = env["account.journal"].browse(cashier["journal_id"]).exists()
    if invoice_journal.type == "sale" and invoice_journal.company_id == company:
        vals["invoice_journal_id"] = invoice_journal.id
    else:
        issues.append("invoice journal not migrated (missing, not a sale journal or another company)")

    picking_type = _picking_type(cr, env, cashier, issues)
    if picking_type:
        vals["picking_type_id"] = picking_type.id

    config = env["pos.config"].with_company(company).create(vals)
    cr.execute(util.format_query(cr, "INSERT INTO {} VALUES (%s, %s)", _MAP_TABLE), [cashier["id"], config.id])

    issues += _lost_fields(cr, cashier)
    if issues:
        _logger.warning("Cash register '%s' -> pos.config %d:\n  - %s", name, config.id, "\n  - ".join(issues))
    else:
        _logger.info("Cash register '%s' -> pos.config %d.", name, config.id)


def _picking_type(cr, env, cashier, issues):
    warehouse_ids = _rel(cr, "sale_cashier_stock_warehouse_rel", "sale_cashier_id", "stock_warehouse_id", cashier["id"])
    warehouse_id = cashier.get("warehouse_id") or (warehouse_ids and warehouse_ids[0])
    others = [w for w in warehouse_ids if w != warehouse_id]
    if others:
        names = env["stock.warehouse"].browse(others).exists().mapped("name")
        issues.append(f"extra warehouses not migrated (one per register): {', '.join(names)}")
    warehouse = env["stock.warehouse"].browse(warehouse_id).exists() if warehouse_id else None
    if not warehouse or not warehouse.pos_type_id:
        issues.append("no warehouse with a PoS operation type; the default one was used")
        return None
    return warehouse.pos_type_id


def _lost_fields(cr, cashier):
    lost = []
    for field in _LOST_FIELDS:
        value = cashier.get(field)
        if value not in (None, False, "", 0, 0.0):
            lost.append(field if value is True else f"{field}={value}")
    issues = [f"no native equivalent: {', '.join(lost)}"] if lost else []
    refund_journals = _rel(cr, "refund_id", "sale_cashier_id", "account_journal_id", cashier["id"])
    if refund_journals:
        issues.append(f"refund journals not migrated: {len(refund_journals)}")
    reasons = _rel(cr, "sale_cashier_sale_return_reason_rel", "sale_cashier_id", "sale_return_reason_id", cashier["id"])
    if reasons:
        issues.append(f"return reasons not migrated: {len(reasons)}")
    return issues


def _report_refund_reasons(cr):
    if util.table_exists(cr, "zz_legacy_sale_return_reason"):
        cr.execute("SELECT count(*) FROM zz_legacy_sale_return_reason")
        _logger.warning("%d return reason(s) have no native equivalent and were not migrated.", cr.fetchone()[0])
