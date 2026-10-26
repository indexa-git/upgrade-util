from odoo.upgrade import util


def migrate(cr, version):
    util.rename_xmlid(
        cr,
        "stock_landed_costs_file.stock_landed_costs_file_tree",
        "stock_landed_costs_file.stock_landed_costs_file_list",
    )
