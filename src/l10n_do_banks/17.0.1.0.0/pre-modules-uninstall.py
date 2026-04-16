from odoo.addons.base.maintenance.migrations import util
import logging

_logger = logging.getLogger(__name__)


def _cleanup_qztray_data(cr):
    """Remove qztray printer records that block keypair deletion.

    Some databases have a NOT NULL constraint on ``qztray_printer.keypair_id``
    while the foreign key uses ``ON DELETE SET NULL``. When uninstalling the
    qztray modules, the upgrade utility tries to delete records from
    ``qztray_keypair``, which triggers ``SET NULL`` on ``qztray_printer`` and
    crashes on the NOT NULL constraint.

    We proactively delete the printer records that reference any keypair so the
    module uninstall can proceed.
    """
    # Solo ejecutamos esta limpieza si el módulo qztray_printer (o qztray)
    # está instalado en la base de datos.
    if not (
        util.module_installed(cr, "qztray_printer")
        or util.module_installed(cr, "qztray")
    ):
        _logger.debug(
            "qztray_printer/qztray no instalados; se omite la limpieza previa."
        )
        return

    try:
        cr.execute(
            """
                DELETE FROM qztray_printer
                WHERE keypair_id IN (SELECT id FROM qztray_keypair)
            """
        )
        _logger.info("Deleted qztray_printer records referencing qztray_keypair.")
    except Exception:
        # If tables don't exist or deletion fails, ignore and let normal
        # uninstall logic handle it.
        _logger.debug(
            "qztray_printer/qztray_keypair tables not found or deletion failed, "
            "continuing with module uninstall.",
            exc_info=True,
        )


def uninstall_modules(cr):
    """
    Script to uninstall modules that are no longer needed or compatible with version 17.0.

    Args:
        cr (cursor): Database cursor.
    """
    modules_to_uninstall = [
        'whatsapp_connector_send_stock',
        'whatsapp_connector_send_purchase',
        'whatsapp_connector_send_account',
        'whatsapp_connector_send_crm',
        'whatsapp_connector_template_base',
        'whatsapp_connector_admin',
        'whatsapp_connector_facebook',
        'whatsapp_connector_menu_analysis',
        'whatsapp_connector_menu_analysis_sale',
        'qztray',
        'qztray_base',
        'qztray_location_labels',
        'qztray_partner_labels',
        'qztray_product_inventory',
        'qztray_product_labels',
        'qztray_product_purchase',
        'base_rest',
        'base_rest_auth_api_key',
        'base_rest_datamodel',
        'restapi',
        'account_rest_api',
        'partner_rest_api',
        'payment_rest_api',
        'product_rest_api',
        'purchase_rest_api',
        'product_pricelist_direct_print',
        'sh_product_multi_barcode_mod',
        'sh_product_multi_barcode',
        'product_analytic',
        'incocegla_product_label_zebra_printer',
        'product_quantity_update_force_inventory',
        'product_code_unique',
        'product_warehouse_quantity',
        'product_hide_sale_cost_price',
        'sales_product_warehouse_quantity',
        'non_moving_product_ept',
        'account_multi_contact_followup',
        'account_payment_reconcile_features',
        'account_reconcile_exchange_difference',
        'account_followup_features',
        'account_move_line_auto_reconcile_hook',
        'account_state_report_kl',
        'account_invoice_migration_scripts',
        'account_ecf_auto_post',
        'account_discount',
        'account_multicurrency_reconcile_patch',
        'account_purchase_discount',
        'l10n_do_electronic_stamp_amount',
        'l10n_do_duplicate_fiscal_number',
        'l10n_do_account_followup',
        'l10n_do_check_print',
        'l10n_do_hr_expense_invoice',
        'l10n_do_hr_payroll_holidays',
        'l10n_do_ecf_consult',
        'l10n_do_ecf_xsd_bypass',
        'l10n_do_ecf_document_type_enable',
        'l10n_do_ecf_certificate',
        'l10n_do_ecf_cashier',
        'l10n_do_partner',
        'l10n_do_purchase',
        'l10n_do_debit_note',
        'l10n_do_document_pools_pre_migration_scripts',
        'ncf_invoice_template',
        'ncf_purchase',
        'ncf_sale',
        'partner_phone_extension',
        'res_partner_phone_search',
        'datamodel',
        'website_sale_require_login',
        'web_m2x_options_manager',
        'neutralized_automated_action',
        'import_lot_serial_no',
        'unique_fields_support',
        'repair_financial_risk_features',
        'repair_financial_risk',
        'eq_send_payslip_email',
        'odoo_cheque_bank_no_image',
        'setu_advance_inventory_reports',
        'sale_mrp_link',
        'bim',
        'bim_code_product',
        'base_bim_2',
        'component',
        'dgii_ir3',
        'dgii_reports_enterprise',
        'hr_payroll_inputs_dynamic_tree',
        'sale_pos_backend_invoice_template',
        'web_gantt_view',
        'stock_account_product_cost_security',
        'stock_available_unreserved',
        'sale_discount_limit',
        'professional_templates',
        'alan_customize',
        'config_interface',
        'database_cleanup',
        'dev_sale_product_stock_restrict',
        'interface_invoicing',
        'negative_stock_sale',
        'payment_backend_refund',
        'protocol_message',
        'required_requested_date',
        'stock_inventory_chatter',
        'cecomsa_account_followup',
        'odoo_document_invoice_report',
        'base_partner_fields',
        'folder_view',
        'bi_all_in_one_hide',
        'web_digital_sign',
        'hierarchy_view',
        'generic_read_only_user_app',
        'sh_payslip_send_email',
        'base_patch',
    ]

    _logger.info(f'Starting uninstall process for {len(modules_to_uninstall)} modules.')
    
    uninstalled_count = 0
    not_installed_count = 0
    failed_count = 0

    for module_name in modules_to_uninstall:
        try:
            if util.module_installed(cr, module_name):
                _logger.info(f'Attempting to uninstall module: {module_name}')
                util.uninstall_module(cr, module_name)
                uninstalled_count += 1
                _logger.info(f'Successfully uninstalled module: {module_name}.')
            else:
                not_installed_count += 1
                _logger.debug(f'Module {module_name} is not installed, skipping.')
        except Exception as e:
            failed_count += 1
            _logger.error(
                f'Failed to uninstall module {module_name}: {str(e)}',
                exc_info=True
            )
    
    _logger.info(
        f'Uninstall process completed. '
        f'Uninstalled: {uninstalled_count}, '
        f'Not installed: {not_installed_count}, '
        f'Failed: {failed_count}'
    )


def migrate(cr, version):
    _cleanup_qztray_data(cr)
    uninstall_modules(cr)
