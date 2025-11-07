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
    
    # Also check if there are potential conflicts (products with NULL that would conflict 
    # when modules try to assign default codes like '/')
    cr.execute("""
        SELECT COUNT(*) 
        FROM product_product 
        WHERE default_code IS NULL 
        AND EXISTS (
            SELECT 1 
            FROM product_product pp2 
            WHERE pp2.default_code = '/'
        )
    """)
    
    potential_conflicts = cr.fetchone()[0]
    
    if potential_conflicts > 0:
        _logger.info(f'Found {potential_conflicts} products with NULL default_code that would conflict with existing "/" codes. This confirms constraint drop is needed.')
    
    try:
        # Drop the constraint if it exists
        # Using IF EXISTS to avoid errors if constraint doesn't exist
        _logger.info('Dropping constraint product_product_default_code_uniq')
        cr.execute("""
            ALTER TABLE product_product
            DROP CONSTRAINT IF EXISTS product_product_default_code_uniq
        """)
        _logger.info('Successfully dropped constraint product_product_default_code_uniq (or it did not exist)')
            
    except Exception as e:
        _logger.error(f'Error dropping constraint product_product_default_code_uniq: {e}')
        raise
    
    _logger.info('Finished pre-migration: dropping product_product.default_code unique constraint')

