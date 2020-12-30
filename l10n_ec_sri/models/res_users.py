# -*- coding: utf-8 -*-
####################################################
# Parte del Proyecto LibreGOB: http://libregob.org #
# Licencia AGPL-v3                                 #
####################################################

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    # Autorizaciones por usuario.
    autorizacion_facturas_id = fields.Many2one(
        'l10n_ec_sri.autorizacion', string='Autorizacion facturas', )
    autorizacion_notas_credito_id = fields.Many2one(
        'l10n_ec_sri.autorizacion', string='Autorizacion en notas de crédito', )
    autorizacion_retenciones_id = fields.Many2one(
        'l10n_ec_sri.autorizacion', string='Autorizacion en retenciones', )
    autorizacion_liquidaciones_id = fields.Many2one(
        'l10n_ec_sri.autorizacion', string='Autorizacion en liquidaciones', )
