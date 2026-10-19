"""Move the commission history of account_payment_compensation to sale_commission_payout, then uninstall it.

account_payment_compensation (profiles, Python rules and receipts) and its bridges account_payment_compensation_news
(payroll news) and account_payment_compensation_pos (point of sale payments) are not ported to 20.0.
``pre-30-install-sale-commission.py`` installs sale_commission_payout; by the end stage both the old tables and the
new models are there, so the data is copied here. Lines are summed and copied in SQL: a client can have millions.

What moves:

* **Receipts** that are not drafts or rejected become payouts (``sale.commission.payout``), with one line per
  profile and one detail per receipt line (invoice, payment, days and amount). They are *Paid*, except the receipts
  still waiting in the last period of their company, which become *Approved*: those may not be paid yet, and the
  new payouts never pay again a period before the upgrade.
* Payout lines need a plan, so each profile gets a cancelled plan, "Histórico - <profile>", that only holds the
  history: payouts only settle approved plans, so the history never offsets a new payout.
* **Receipt batch reports** become payout batches. **Payroll news** created from a receipt point to its payout: the
  news wizard skips payouts that have news, and paying that news in payroll marks the payout as paid.
* **Contacts without an internal user** get an archived internal user that owns their history: a payout belongs to
  a user, and archived users cannot log in nor count as licensed users.
* **Payroll news types** marked as compensation news, with a salary rule, become commission news types.
* *Cost at posting* (``account_move_line.standard_product_price``) stays: sale_commission_payout declares the same
  column, so uninstalling the old module keeps it.

What does not move:

* Commission plans. Profiles and Python rules are configured again with each client after the upgrade; plans must
  start after the last migrated period, logged here per company.
* Drafts and rejected receipts, receipts without lines (no amount), the chatter and attachments of the receipts,
  the compensation JSON columns of the invoices, the profit percentages and the contact targets.
* Columns that client modules or Studio added to the receipt tables: they go with the tables.

The old modules are kept when another installed module still depends on them; the history is migrated anyway.

Plan, batch and login names are written in Spanish: they are data shown to Dominican users, created once, with no
translation file behind them.
"""

import logging
from collections import defaultdict
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import Command

from odoo.upgrade import util

_logger = logging.getLogger(__name__)

OLD_MODULE = "account_payment_compensation"
OLD_NEWS_MODULE = "account_payment_compensation_news"
OLD_POS_MODULE = "account_payment_compensation_pos"
# Uninstalled in this order: the bridges first.
OLD_MODULES = (OLD_POS_MODULE, OLD_NEWS_MODULE, OLD_MODULE)
LEGACY_PLAN_PREFIX = "Histórico - "
LEGACY_PLAN_NO_PROFILE = "Histórico - Sin perfil"
HISTORY_LOGIN = "historico.comisiones.%d"
CHUNK = 500


def migrate(cr, version):
    if not util.module_installed(cr, OLD_MODULE) or not util.table_exists(cr, "account_compensation_receipt"):
        return
    env = util.env(cr)
    if "sale.commission.payout" not in env:
        _logger.error("sale_commission_payout is not installed: %s is kept with its data.", OLD_MODULE)
        return
    env = env(
        context=dict(
            env.context,
            tracking_disable=True,
            mail_create_nolog=True,
            mail_create_nosubscribe=True,
            mail_notrack=True,
            no_reset_password=True,
        )
    )
    data = _read_compensation_data(cr)
    _migrate_history(env, data)
    _migrate_news_types(env)
    _uninstall_old_modules(cr)


# ---------------------------------------------------------------------------------------------------------------
# Reading the old tables (their models are no longer in the registry)
# ---------------------------------------------------------------------------------------------------------------


def _name_sql(cr, table, alias):
    """Expression for the name of a record, whether the column is translatable (jsonb) or not."""
    if util.column_type(cr, table, "name") == "jsonb":
        return f"COALESCE({alias}.name->>'es_DO', {alias}.name->>'en_US')"
    return f"{alias}.name"


def _pairs(cr, model, field):
    """Rows of the relation table of a many2many field of the old module, as (model id, comodel id)."""
    cr.execute(
        "SELECT relation_table, column1, column2 FROM ir_model_fields WHERE model = %s AND name = %s",
        [model, field],
    )
    row = cr.fetchone()
    if not row or not row[0] or not util.table_exists(cr, row[0]):
        return []
    table, column1, column2 = row
    cr.execute(f'SELECT "{column1}", "{column2}" FROM "{table}"')
    return cr.fetchall()


def _read_compensation_data(cr):
    data = {}
    cr.execute(f"SELECT p.id, {_name_sql(cr, 'account_compensation_profile', 'p')} FROM account_compensation_profile p")
    data["profile_names"] = dict(cr.fetchall())
    data["profile_rules"] = defaultdict(set)
    for profile_id, rule_id in _pairs(cr, "account.compensation.profile", "rule_ids"):
        data["profile_rules"][profile_id].add(rule_id)
    data["receipt_profiles"] = defaultdict(list)
    for receipt_id, profile_id in _pairs(cr, "account.compensation.receipt", "profile_ids"):
        data["receipt_profiles"][receipt_id].append(profile_id)
    # Internal user of each contact; an archived one still owns the history of its contact.
    cr.execute(
        """
        SELECT DISTINCT ON (u.partner_id) u.partner_id, u.id
          FROM res_users u
         WHERE NOT u.share
      ORDER BY u.partner_id, u.active DESC, u.id
        """
    )
    data["users"] = dict(cr.fetchall())
    return data


# ---------------------------------------------------------------------------------------------------------------
# History: receipts -> payouts
# ---------------------------------------------------------------------------------------------------------------


def _migrate_history(env, data):
    cr = env.cr
    news_column = "r.news_id" if util.column_exists(cr, "account_compensation_receipt", "news_id") else "NULL"
    cr.execute(
        f"""
        SELECT r.id, r.partner_id, r.company_id, COALESCE(NULLIF(r.number, ''), r.name), r.state, r.date_from,
               r.date_to, r.compensation_batch_report_id, {news_column}
          FROM account_compensation_receipt r
         WHERE (r.state IS NULL OR r.state NOT IN ('draft', 'cancel'))
           AND EXISTS (SELECT 1 FROM account_compensation_receipt_line l WHERE l.receipt_id = r.id)
         ORDER BY r.company_id, r.date_to, r.id
        """
    )
    receipts = {}
    for receipt_id, partner_id, company_id, name, state, date_from, date_to, batch_report_id, news_id in cr.fetchall():
        receipts[receipt_id] = {
            "partner_id": partner_id,
            "company_id": company_id,
            "name": name,
            "old_state": state,
            "date_from": date_from,
            "date_to": date_to,
            "batch_report_id": batch_report_id,
            "news_ids": {news_id} if news_id else set(),
        }
    if not receipts:
        return

    _create_history_users(env, data, receipts)
    _set_payout_states(receipts)
    if util.column_exists(cr, "l10n_do_hr_news", "compensation_receipt_id"):
        cr.execute(
            "SELECT compensation_receipt_id, id FROM l10n_do_hr_news WHERE compensation_receipt_id = ANY(%s)",
            [list(receipts)],
        )
        for receipt_id, news_id in cr.fetchall():
            receipts[receipt_id]["news_ids"].add(news_id)

    # Amount of each receipt per profile: a line belongs to the receipt profile that holds its rule. Summed in SQL
    # per (receipt, rule): a big client has millions of lines, and only these pairs need to be held in memory.
    cr.execute(
        """
        SELECT l.receipt_id, l.rule_id, SUM(COALESCE(l.compensation_amount, 0))
          FROM account_compensation_receipt_line l
         WHERE l.receipt_id = ANY(%s)
      GROUP BY l.receipt_id, l.rule_id
        """,
        [list(receipts)],
    )
    rule_profile = {}
    amounts = defaultdict(float)
    for receipt_id, rule_id, amount in cr.fetchall():
        candidates = data["receipt_profiles"].get(receipt_id, [])
        profile_id = next(
            (p for p in candidates if rule_id in data["profile_rules"][p]),
            candidates[0] if candidates else None,
        )
        rule_profile[receipt_id, rule_id] = profile_id
        amounts[receipt_id, profile_id] += amount

    plans = _create_legacy_plans(env, data, receipts, amounts)
    batches = _create_legacy_batches(env, receipts, amounts)
    payout_lines = _create_legacy_payouts(env, receipts, amounts, plans, batches)
    _create_legacy_details(cr, rule_profile, receipts, plans, payout_lines)
    _link_payroll_news(env, receipts)
    _log_cutoffs(env, receipts, amounts)


def _create_history_users(env, data, receipts):
    """Give an archived internal user to every contact with receipts and no internal user."""
    partner_ids = sorted({r["partner_id"] for r in receipts.values() if r["partner_id"] not in data["users"]})
    if not partner_ids:
        for receipt in receipts.values():
            receipt["user_id"] = data["users"][receipt["partner_id"]]
        return
    company_of = {}
    for receipt in receipts.values():
        company_of.setdefault(receipt["partner_id"], receipt["company_id"])
    env.cr.execute("SELECT login FROM res_users WHERE login = ANY(%s)", [[HISTORY_LOGIN % p for p in partner_ids]])
    taken = {login for (login,) in env.cr.fetchall()}
    internal = env.ref("base.group_user")
    partners = env["res.partner"].with_context(active_test=False).browse(partner_ids)
    active_partners = partners.filtered("active")
    vals_list = []
    for partner in partners:
        login = HISTORY_LOGIN % partner.id
        if login in taken:
            login = f"{login}.{len(taken)}"
        company_id = company_of[partner.id]
        vals_list.append(
            {
                "name": partner.name,
                "login": login,
                "partner_id": partner.id,
                "company_id": company_id,
                "company_ids": [Command.set([company_id])],
                "group_ids": [Command.set([internal.id])],
                "active": False,
            }
        )
    users = env["res.users"].with_context(active_test=False).create(vals_list)
    # An archived user archives its contact; the contact may still be a customer, vendor or employee.
    active_partners.active = True
    for user in users:
        data["users"][user.partner_id.id] = user.id
        _logger.warning(
            "Created archived user %r for %r: its compensation history needs a user, it had none.",
            user.login,
            user.partner_id.name,
        )
    for receipt in receipts.values():
        receipt["user_id"] = data["users"][receipt["partner_id"]]


def _set_payout_states(receipts):
    """Paid, except the receipts still waiting in the last period of their company: approved, they may be unpaid."""
    last_period = {}
    for receipt in receipts.values():
        start = receipt["date_to"].replace(day=1)
        last_period[receipt["company_id"]] = max(last_period.get(receipt["company_id"], start), start)
    for receipt in receipts.values():
        waiting = receipt["old_state"] == "verify" and receipt["date_to"] >= last_period[receipt["company_id"]]
        receipt["state"] = "approved" if waiting else "paid"


def _create_legacy_plans(env, data, receipts, amounts):
    """One cancelled plan per (company, profile) holding the history. Return {(company, profile): plan id}."""
    periods = {}
    for receipt_id, profile_id in amounts:
        receipt = receipts[receipt_id]
        key = (receipt["company_id"], profile_id)
        date_from, date_to = periods.get(key, (receipt["date_from"], receipt["date_to"]))
        periods[key] = (min(date_from, receipt["date_from"]), max(date_to, receipt["date_to"]))

    keys = sorted(periods, key=lambda key: (key[0], key[1] or 0))
    vals_list = []
    for company_id, profile_id in keys:
        date_from, date_to = periods[company_id, profile_id]
        name = data["profile_names"].get(profile_id)
        vals_list.append(
            {
                "name": LEGACY_PLAN_PREFIX + name if name else LEGACY_PLAN_NO_PROFILE,
                "company_id": company_id,
                "date_from": date_from.replace(day=1),
                "date_to": date_to,
                "periodicity": "month",
                "type": "achieve",
                "user_type": "person",
                "achievement_ids": [],
                "state": "cancel",
            }
        )
    plans = env["sale.commission.plan"].create(vals_list)
    return dict(zip(keys, plans.ids))


def _create_legacy_batches(env, receipts, amounts):
    """One payout batch per receipt batch report, or per company and end date without one."""
    cr = env.cr
    cr.execute("SELECT id, name FROM account_compensation_batch_report")
    report_names = dict(cr.fetchall())
    groups = {}
    for receipt_id in {receipt_id for receipt_id, _profile_id in amounts}:
        receipt = receipts[receipt_id]
        key = (receipt["company_id"], receipt["batch_report_id"] or receipt["date_to"])
        groups[key] = max(groups.get(key, receipt["date_to"]), receipt["date_to"])

    keys = sorted(groups, key=lambda key: (key[0], groups[key]))
    vals_list = [
        {
            "name": report_names.get(group) if not isinstance(group, date) else f"Histórico {group.isoformat()}",
            "company_id": company_id,
            "date": groups[company_id, group],
        }
        for company_id, group in keys
    ]
    batches = env["sale.commission.payout.batch"].create(vals_list)
    return dict(zip(keys, batches.ids))


def _create_legacy_payouts(env, receipts, amounts, plans, batches):
    """Create the payouts. Return {(receipt, plan): payout line id}."""
    profiles_by_receipt = defaultdict(list)
    for receipt_id, profile_id in amounts:
        profiles_by_receipt[receipt_id].append(profile_id)

    # Period of each line: the monthly target of the legacy plan holding the receipt start, as new payouts do.
    targets = defaultdict(list)
    for target in env["sale.commission.plan"].browse(list(plans.values())).target_ids:
        targets[target.plan_id.id].append((target.date_from, target.date_to, target.id))

    def target_of(plan_id, day):
        return next((target_id for start, end, target_id in targets[plan_id] if start <= day <= end), False)

    receipt_ids = sorted(profiles_by_receipt)
    payout_lines = {}
    for start in range(0, len(receipt_ids), CHUNK):
        chunk = receipt_ids[start : start + CHUNK]
        vals_list = []
        for receipt_id in chunk:
            receipt = receipts[receipt_id]
            lines = []
            for profile_id in sorted(profiles_by_receipt[receipt_id], key=lambda p: p or 0):
                amount = amounts[receipt_id, profile_id]
                plan_id = plans[receipt["company_id"], profile_id]
                lines.append(
                    Command.create(
                        {
                            "line_type": "commission",
                            "plan_id": plan_id,
                            "target_id": target_of(plan_id, receipt["date_from"]),
                            "date_from": receipt["date_from"],
                            "date_to": receipt["date_to"],
                            "computed_amount": amount,
                            "settled_amount": 0.0,
                            "delta": amount,
                            "amount": amount,
                        }
                    )
                )
            vals_list.append(
                {
                    "name": receipt["name"] or "/",
                    "batch_id": batches[receipt["company_id"], receipt["batch_report_id"] or receipt["date_to"]],
                    "user_id": receipt["user_id"],
                    "payment_channel": "payroll" if receipt["news_ids"] else "manual",
                    "state": receipt["state"],
                    "line_ids": lines,
                }
            )
        payouts = env["sale.commission.payout"].create(vals_list)
        for receipt_id, payout in zip(chunk, payouts):
            receipts[receipt_id]["payout_id"] = payout.id
            for line in payout.line_ids:
                payout_lines[receipt_id, line.plan_id.id] = line.id
        env.invalidate_all()
    states = defaultdict(int)
    for receipt_id in receipt_ids:
        states[receipts[receipt_id]["state"]] += 1
    _logger.info(
        "Migrated %d compensation receipts to commission payouts (%s) in %d legacy plans.",
        len(receipt_ids),
        ", ".join(f"{count} {state}" for state, count in sorted(states.items())),
        len(plans),
    )
    return payout_lines


def _create_legacy_details(cr, rule_profile, receipts, plans, payout_lines):
    """One detail per receipt line, in one SQL statement: a big client has millions of them."""
    receipt_ids, rule_ids, target_ids = [], [], []
    for (receipt_id, rule_id), profile_id in rule_profile.items():
        receipt_ids.append(receipt_id)
        rule_ids.append(rule_id or 0)
        target_ids.append(payout_lines[receipt_id, plans[receipts[receipt_id]["company_id"], profile_id]])

    payment_name = "pay.name" if util.column_exists(cr, "account_payment", "name") else "NULL"
    # account_payment_compensation_pos: lines collected at the point of sale point to a POS payment instead.
    pos = util.column_exists(cr, "account_compensation_receipt_line", "pos_payment_id") and util.table_exists(
        cr, "pos_payment"
    )
    pos_name = "pos_order.name" if pos else "NULL"
    pos_join = (
        "LEFT JOIN pos_payment pos_pay ON pos_pay.id = l.pos_payment_id "
        "LEFT JOIN pos_order ON pos_order.id = pos_pay.pos_order_id"
        if pos
        else ""
    )
    collected = "l.payment_id IS NOT NULL OR l.pos_payment_id IS NOT NULL" if pos else "l.payment_id IS NOT NULL"
    # cr.execute: bulk copy of the receipt lines; payout_id and plan_id are the stored related fields of line_id.
    cr.execute(
        f"""
        INSERT INTO sale_commission_payout_detail (
            line_id, payout_id, plan_id, date, related_res_model, related_res_id, related_res_name, partner_id,
            achieved, create_uid, create_date, write_uid, write_date
        )
        SELECT pl.id, pl.payout_id, pl.plan_id,
               COALESCE(l.payment_date, l.invoice_date, r.date_to),
               CASE WHEN l.invoice_id IS NOT NULL THEN 'account.move'
                    WHEN l.payment_id IS NOT NULL THEN 'account.payment' END,
               COALESCE(l.invoice_id, l.payment_id),
               CONCAT_WS(' - ', inv.name, COALESCE({payment_name}, pay_move.name, {pos_name}))
                   || CASE WHEN {collected} THEN ' (' || COALESCE(l.days, 0) || ' d)' ELSE '' END,
               COALESCE(l.invoice_partner_id, inv.partner_id),
               COALESCE(l.compensation_amount, 0),
               1, NOW() AT TIME ZONE 'UTC', 1, NOW() AT TIME ZONE 'UTC'
          FROM unnest(%s::int[], %s::int[], %s::int[]) AS m(receipt_id, rule_id, payout_line_id)
          JOIN account_compensation_receipt_line l ON l.receipt_id = m.receipt_id AND COALESCE(l.rule_id, 0) = m.rule_id
          JOIN account_compensation_receipt r ON r.id = l.receipt_id
          JOIN sale_commission_payout_line pl ON pl.id = m.payout_line_id
     LEFT JOIN account_move inv ON inv.id = l.invoice_id
     LEFT JOIN account_payment pay ON pay.id = l.payment_id
     LEFT JOIN account_move pay_move ON pay_move.id = pay.move_id
               {pos_join}
        """,
        [receipt_ids, rule_ids, target_ids],
    )
    _logger.info("Migrated %d compensation receipt lines to payout details.", cr.rowcount)


def _link_payroll_news(env, receipts):
    if "l10n.do.hr.news" not in env or "commission_payout_id" not in env["l10n.do.hr.news"]._fields:
        return
    news_ids, payout_ids = [], []
    for receipt in receipts.values():
        for news_id in receipt["news_ids"]:
            if receipt.get("payout_id"):
                news_ids.append(news_id)
                payout_ids.append(receipt["payout_id"])
    if not news_ids:
        return
    # cr.execute: plain foreign key backfill; writing news through the ORM would rerun their payroll logic.
    env.cr.execute(
        """
        UPDATE l10n_do_hr_news n
           SET commission_payout_id = m.payout_id
          FROM unnest(%s::int[], %s::int[]) AS m(news_id, payout_id)
         WHERE n.id = m.news_id
        """,
        [news_ids, payout_ids],
    )
    _logger.info("Linked %d payroll news to their migrated payouts.", env.cr.rowcount)


def _log_cutoffs(env, receipts, amounts):
    """The plans configured after the upgrade must start after the last migrated period, or it is paid twice."""
    last_day = {}
    for receipt_id, _profile_id in amounts:
        receipt = receipts[receipt_id]
        last_day[receipt["company_id"]] = max(
            last_day.get(receipt["company_id"], receipt["date_to"]), receipt["date_to"]
        )
    for company in env["res.company"].browse(sorted(last_day)):
        _logger.warning(
            "%s: compensation history migrated up to %s. Its commission plans must start on %s.",
            company.name,
            last_day[company.id],
            last_day[company.id] + relativedelta(days=1),
        )


# ---------------------------------------------------------------------------------------------------------------
# Payroll news types and uninstall
# ---------------------------------------------------------------------------------------------------------------


def _migrate_news_types(env):
    cr = env.cr
    if "l10n.do.hr.news.type" not in env or "is_commission_news" not in env["l10n.do.hr.news.type"]._fields:
        return
    if not util.column_exists(cr, "l10n_do_hr_news_type", "is_compensation_new"):
        return
    cr.execute("SELECT id FROM l10n_do_hr_news_type WHERE is_compensation_new ORDER BY id")
    news_types = env["l10n.do.hr.news.type"].with_context(active_test=False).browse([r[0] for r in cr.fetchall()])
    with_rule = news_types.filtered("salary_rule_id")
    for news_type in news_types - with_rule:
        _logger.warning("Compensation news type %r has no salary rule: not marked as commission news.", news_type.name)
    with_rule.is_commission_news = True
    active_types = with_rule.filtered("active")
    for company in env["res.company"].search([("commission_news_type_id", "=", False)]):
        news_type = active_types.filtered_domain([("company_id", "in", [company.id, False])])[:1]
        if news_type:
            company.commission_news_type_id = news_type


def _uninstall_old_modules(cr):
    cr.execute(
        """
        SELECT m.name
          FROM ir_module_module_dependency d
          JOIN ir_module_module m ON m.id = d.module_id
         WHERE d.name IN %s
           AND m.name NOT IN %s
           AND m.state IN %s
        """,
        [OLD_MODULES, OLD_MODULES, util.INSTALLED_MODULE_STATES],
    )
    dependers = [name for (name,) in cr.fetchall()]
    if dependers:
        _logger.error(
            "%s is kept: installed modules still depend on it (%s). Port them, then uninstall it.",
            OLD_MODULE,
            ", ".join(dependers),
        )
        return
    for module in OLD_MODULES:
        if util.module_installed(cr, module):
            util.uninstall_module(cr, module)
            _logger.info("Uninstalled %s: its history now lives in the commission payouts.", module)
