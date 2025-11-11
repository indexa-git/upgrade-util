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

