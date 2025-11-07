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
    _logger.info('=' * 80)
    _logger.info('PRE-MIGRATION SCRIPT: pre-drop-constraint-product-code.py')
    _logger.info('Starting pre-migration: dropping product_product.default_code unique constraint')
    _logger.info('=' * 80)
    
    # Check if product_code_unique module is installed
    _logger.info('Checking if product_code_unique module is installed...')
    if not util.module_installed(cr, 'product_code_unique'):
        _logger.info('Module product_code_unique is not installed. Skipping constraint drop.')
        return
    
    _logger.info('✓ Module product_code_unique is installed. Checking for products without code...')
    
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
    
    # First, verify the constraint exists and get its details
    try:
        # Try the most reliable method: join with pg_class
        cr.execute("""
            SELECT c.conname, c.contype
            FROM pg_constraint c
            JOIN pg_class t ON c.conrelid = t.oid
            JOIN pg_namespace n ON t.relnamespace = n.oid
            WHERE c.conname = 'product_product_default_code_uniq'
            AND t.relname = 'product_product'
            AND n.nspname = 'public'
        """)
        constraint_info = cr.fetchone()
        
        if constraint_info:
            _logger.info(f'Found constraint: {constraint_info[0]} (type: {constraint_info[1]})')
        else:
            # Try without schema restriction
            cr.execute("""
                SELECT c.conname, c.contype
                FROM pg_constraint c
                JOIN pg_class t ON c.conrelid = t.oid
                WHERE c.conname = 'product_product_default_code_uniq'
                AND t.relname = 'product_product'
            """)
            constraint_info = cr.fetchone()
            if constraint_info:
                _logger.info(f'Found constraint (without schema filter): {constraint_info[0]} (type: {constraint_info[1]})')
            else:
                # Last attempt: simple search by name
                cr.execute("""
                    SELECT conname 
                    FROM pg_constraint 
                    WHERE conname = 'product_product_default_code_uniq'
                """)
                constraint_info = cr.fetchone()
                if constraint_info:
                    _logger.info(f'Found constraint (simple search): {constraint_info[0]}')
                else:
                    _logger.warning('Constraint product_product_default_code_uniq not found in database. It may have been already dropped.')
        
        # Drop the constraint if it exists
        _logger.info('Attempting to drop constraint product_product_default_code_uniq')
        
        # First attempt: DROP CONSTRAINT IF EXISTS
        cr.execute("""
            ALTER TABLE product_product
            DROP CONSTRAINT IF EXISTS product_product_default_code_uniq
        """)
        _logger.info('Executed: DROP CONSTRAINT IF EXISTS product_product_default_code_uniq')
        
        # Verify the constraint was actually dropped
        cr.execute("""
            SELECT 1 
            FROM pg_constraint c
            JOIN pg_class t ON c.conrelid = t.oid
            WHERE c.conname = 'product_product_default_code_uniq'
            AND t.relname = 'product_product'
        """)
        still_exists = cr.fetchone()
        
        if still_exists:
            _logger.warning('Constraint still exists after first DROP attempt. Trying with explicit name (no IF EXISTS)...')
            # Try without IF EXISTS in case there's an issue with the syntax
            try:
                cr.execute("""
                    ALTER TABLE product_product
                    DROP CONSTRAINT product_product_default_code_uniq
                """)
                _logger.info('Executed: DROP CONSTRAINT product_product_default_code_uniq (without IF EXISTS)')
            except Exception as e1:
                _logger.warning(f'First explicit DROP failed: {e1}. Trying with CASCADE...')
                # Try with CASCADE in case there are dependencies
                try:
                    cr.execute("""
                        ALTER TABLE product_product
                        DROP CONSTRAINT product_product_default_code_uniq CASCADE
                    """)
                    _logger.info('Executed: DROP CONSTRAINT product_product_default_code_uniq CASCADE')
                except Exception as e2:
                    _logger.error(f'All DROP attempts failed. Last error: {e2}')
                    raise
        
        # Final verification after all attempts
        cr.execute("""
            SELECT 1 
            FROM pg_constraint c
            JOIN pg_class t ON c.conrelid = t.oid
            WHERE c.conname = 'product_product_default_code_uniq'
            AND t.relname = 'product_product'
        """)
        final_check = cr.fetchone()
        
        if final_check:
            _logger.error('=' * 80)
            _logger.error('CRITICAL: Constraint still exists after all DROP attempts!')
            _logger.error('This may indicate a transaction rollback or permission issue.')
            _logger.error('=' * 80)
            # Don't raise here, just log the error so the migration can continue
        else:
            _logger.info('✓ Successfully verified: constraint product_product_default_code_uniq has been dropped')
        
        # Commit the transaction explicitly
        try:
            cr.commit()
            _logger.info('✓ Transaction committed successfully')
        except Exception as commit_error:
            _logger.error(f'Error committing transaction: {commit_error}')
            # Some Odoo versions handle commits automatically, so this might not be an error
            _logger.info('Note: Some Odoo versions handle commits automatically')
            
    except Exception as e:
        _logger.error(f'Error dropping constraint product_product_default_code_uniq: {e}')
        _logger.error(f'Exception type: {type(e).__name__}')
        import traceback
        _logger.error(traceback.format_exc())
        raise
    
    # Final diagnostic check
    _logger.info('=' * 80)
    _logger.info('FINAL DIAGNOSTIC CHECK:')
    try:
        cr.execute("""
            SELECT c.conname, c.contype
            FROM pg_constraint c
            JOIN pg_class t ON c.conrelid = t.oid
            WHERE c.conname = 'product_product_default_code_uniq'
            AND t.relname = 'product_product'
        """)
        final_constraint = cr.fetchone()
        if final_constraint:
            _logger.warning(f'⚠️  Constraint still exists: {final_constraint[0]} (type: {final_constraint[1]})')
            _logger.warning('This may require manual intervention or the constraint may be recreated by another module.')
        else:
            _logger.info('✓ Constraint successfully removed - verification confirmed')
    except Exception as diag_error:
        _logger.warning(f'Could not perform final diagnostic check: {diag_error}')
    
    _logger.info('=' * 80)
    _logger.info('Finished pre-migration: dropping product_product.default_code unique constraint')

