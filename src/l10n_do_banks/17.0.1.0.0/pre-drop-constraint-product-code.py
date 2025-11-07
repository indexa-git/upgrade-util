# -*- coding: utf-8 -*-

from odoo.addons.base.maintenance.migrations import util
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migration script to drop the unique constraint on product_product.default_code.
    
    This script removes the constraint 'product_product_default_code_uniq' from the
    product_product table to allow duplicate default codes.
    
    This script only runs when:
    - The module 'product_code_unique' is installed
    - There are products without code in the default_code field
    
    Args:
        cr (cursor): Database cursor
        version (str): Module version
    """
    _logger.info('Starting pre-migration: dropping product_product.default_code unique constraint')
    
    # Check if product_code_unique module is installed
    if not util.module_installed(cr, 'product_code_unique'):
        _logger.info('Module product_code_unique is not installed. Skipping constraint drop.')
        return
    
    _logger.info('Module product_code_unique is installed. Checking for products without code...')
    
    # Check if there are products without code in default_code
    cr.execute("""
        SELECT COUNT(*) 
        FROM product_product 
        WHERE default_code IS NULL OR default_code = ''
    """)
    
    products_without_code = cr.fetchone()[0]
    
    if products_without_code == 0:
        _logger.info('No products without code found. Skipping constraint drop.')
        return
    
    _logger.info(f'Found {products_without_code} products without code. Proceeding with constraint drop.')
    
    try:
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

