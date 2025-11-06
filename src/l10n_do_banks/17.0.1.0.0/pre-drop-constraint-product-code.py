# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migration script to drop the unique constraint on product_product.default_code.
    
    This script removes the constraint 'product_product_default_code_uniq' from the
    product_product table to allow duplicate default codes.
    
    Args:
        cr (cursor): Database cursor
        version (str): Module version
    """
    _logger.info('Starting pre-migration: dropping product_product.default_code unique constraint')
    
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

