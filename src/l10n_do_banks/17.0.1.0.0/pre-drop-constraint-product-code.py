# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migration script to drop the unique constraint on product_product.default_code.

    This script removes the constraint 'product_product_default_code_uniq' from the
    product_product table, but only when the module 'product_code_unique' has been
    uninstalled and there is no data in `product_product.default_code`.
    
    Args:
        cr (cursor): Database cursor
        version (str): Module version
    """
    _logger.info('Starting pre-migration: dropping product_product.default_code unique constraint')
    
    try:
        cr.execute(
            """
            SELECT state
            FROM ir_module_module
            WHERE name = 'product_code_unique'
            ORDER BY id DESC
            LIMIT 1
            """
        )
        module_row = cr.fetchone()

        if module_row and module_row[0] not in ('uninstalled', 'uninstallable'):
            _logger.info(
                "Skipping constraint drop because module product_code_unique is not uninstalled"
            )
            return

        cr.execute(
            """
            SELECT COUNT(*)
            FROM product_product
            WHERE COALESCE(default_code, '') != ''
            """
        )
        default_code_count = cr.fetchone()[0]

        if default_code_count > 0:
            _logger.info(
                "Skipping constraint drop because %s products have default_code set",
                default_code_count,
            )
            return

        # Check if constraint exists before attempting to drop it
        cr.execute("""
            SELECT 1 
            FROM pg_constraint 
            WHERE conname = 'product_product_default_code_uniq'
        """)
        
        if cr.rowcount > 0:
            _logger.info('Dropping constraint product_product_default_code_uniq')
            cr.execute("""
                ALTER TABLE product_product
                DROP CONSTRAINT product_product_default_code_uniq
            """)
            _logger.info('Successfully dropped constraint product_product_default_code_uniq')
        else:
            _logger.info('Constraint product_product_default_code_uniq does not exist, skipping')
            
    except Exception as e:
        _logger.error(f'Error dropping constraint product_product_default_code_uniq: {e}')
        raise
    
    _logger.info('Finished pre-migration: dropping product_product.default_code unique constraint')

