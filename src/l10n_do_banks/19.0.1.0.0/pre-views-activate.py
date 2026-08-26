import logging

_logger = logging.getLogger(__name__)


def activate_views(cr, xml_ids):
    """Reactivate views the upgrade platform switched off.

    Runs in `pre` and not in end-views-management.py: a module whose XML
    xpaths into content injected by one of these views fails to install while
    the view is inactive, and that install happens during the module loading
    phase, long before the `end` scripts run.

    Raw SQL on purpose — writing `active` through the ORM revalidates the view
    arch, and at this point the registry is only partially loaded.
    """
    for xml_id in xml_ids:
        module, _, name = xml_id.partition('.')
        cr.execute("""
            UPDATE ir_ui_view v
               SET active = true
              FROM ir_model_data d
             WHERE d.res_id = v.id
               AND d.model = 'ir.ui.view'
               AND d.module = %s
               AND d.name = %s
               AND v.active = false
         RETURNING v.id
        """, (module, name))
        row = cr.fetchone()
        if row:
            _logger.info("Reactivated view %s (ID %s)", xml_id, row[0])


def migrate(cr, version):
    # Deactivated while their modules were missing from the addons path.
    # Without them the partner form loses the whole financial risk page, and
    # installing account_financial_risk_features raises a ParseError.
    inactive_views_list = [
        'account_financial_risk.res_partner_view_risk',
        'purchase_financial_risk.res_partner_view_purchase_risk',
    ]

    activate_views(cr, inactive_views_list)
