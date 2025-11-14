from odoo import api, SUPERUSER_ID
import logging

_logger = logging.getLogger(__name__)

def migrate(cr, version):
    """
    Deactivates specific Odoo views.
    
    Args:
        cr (cursor): Database cursor
        version (str): Module version
    """
    _logger.info('Deactivating specific views')
    env = api.Environment(cr, SUPERUSER_ID, {})

    views_to_deactivate = [
        'portal.frontend_layout',
        'purchase_request.view_purchase_request_tree',
        'crm_claim_customizations.crm_case_claims_tree_view_customization_inherit',
        'crm_claim_service.crm_claim_telco_form_view_inherit',
        'crm_claim_service.crm_case_claims_form_view_inherit',
        'sh_barcode_scanner_no_mrp.sh_purchase_barcode_scanner_purchase_order_form',
        'sh_barcode_scanner_no_mrp.sh_sale_barcode_scanner_sale_view_order_form',
        'sh_barcode_scanner_no_mrp.sh_inventory_barcode_scanner_stock_move_operations',
        'sh_barcode_scanner_no_mrp.sh_scrap_barcode_scanner_stock_scrap_form2',
        'sh_barcode_scanner_no_mrp.sh_scrap_barcode_scanner_stock_scrap_form',
        'sh_barcode_scanner_no_mrp.sh_invoice_barcode_scanner_invoice_form',
        'sh_barcode_scanner_no_mrp.sh_product_barcode_scanner_product_variant_form_view',
        'sh_barcode_scanner_no_mrp.sh_product_barcode_scanner_product_template_form_view',
        'product_multiple_barcodes.product_variant_barcode_multi_view_form',
        'b.product_variant_barcode_multi_easy_view_form',
        'product_multiple_barcodes.product_barcode_multi_view_search',
        'product_multiple_barcodes.product_variant_barcode_multi_view_search',
        'product_multiple_barcodes.product_template_view_form_multiply_barcode',
        'cm_base_reports.external_layout_boxed'
    ]

    for xml_id in views_to_deactivate:
        try:
            view = env.ref(xml_id)
            if view:
                view.write({'active': False})
                _logger.info(f'View deactivated: {xml_id}')
            else:
                _logger.warning(f'View not found: {xml_id}')
        except Exception as e:
            _logger.warning(f'Error deactivating view {xml_id}: {e}')

    _logger.info('Finished deactivating views')

