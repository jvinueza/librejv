# -*- coding: utf-8 -*-
import logging
_logger = logging.getLogger(__name__)

from openupgradelib import openupgrade

def compute_sri_invoice_tipoem(env):
    inv = env['account.invoice'].search([])
    for i in inv:
        if i.type == 'in_invoice' and i.retencion_electronica_id:
            i.tipoem = "E"
            _logger.warning("Corrigiendo el tipoem en la factura: %s", i.number)

def set_emitir_retenciones_en_cero(env):
    comp = env['res.company'].search([])
    for c in comp:
        c.emitir_retenciones_en_cero = True
        _logger.warning("Emitir retenciones en cero en: %s", c.name)

@openupgrade.migrate(use_env=True)
def migrate(env, version):
    compute_sri_invoice_tipoem(env)
    set_emitir_retenciones_en_cero(env)

