import logging

from odoo.upgrade import util

_logger = logging.getLogger(__name__)

OLD_MODULE = "hr_employee_relative"
NEW_MODULE = "l10n_do_hr"


_MODELS = ["hr.employee.relative", "hr.employee.relative.relation"]
_FIELDS = [("hr.employee", "relative_ids")]


def migrate(cr, version):
    if not util.module_installed(cr, OLD_MODULE):
        _logger.info("%r is not installed; nothing to retire.", OLD_MODULE)
        return

    if not util.module_installed(cr, NEW_MODULE):
        _logger.warning("%r is not installed; leaving %r untouched.", NEW_MODULE, OLD_MODULE)
        return

    for model in _MODELS:
        util.move_model(cr, model, OLD_MODULE, NEW_MODULE)
        _logger.info("Model re-homed: %r from %r to %r", model, OLD_MODULE, NEW_MODULE)

    for model, fieldname in _FIELDS:
        util.move_field_to_module(cr, model, fieldname, OLD_MODULE, NEW_MODULE)
        _logger.info("Field re-homed: %s.%s from %r to %r", model, fieldname, OLD_MODULE, NEW_MODULE)

    util.remove_module_deps(cr, NEW_MODULE, [OLD_MODULE])

    cr.execute("UPDATE ir_module_module SET state = 'to remove' WHERE name = %s", [OLD_MODULE])
    _logger.info("Module %r marked 'to remove'; %r owns the model from now on.", OLD_MODULE, NEW_MODULE)
