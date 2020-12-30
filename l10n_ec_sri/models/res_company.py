# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    vat = fields.Char(
        'Identificacion fiscal', related='partner_id.vat', )

    contribuyenteespecial = fields.Integer(
        'Nro. de resolución como contribuyente especial', )

    property_account_position_id = fields.Many2one(
        'account.fiscal.position', 'Posición fiscal',
        related='partner_id.property_account_position_id', )

    # Autorizaciones por defecto, se usan si el usuario no tiene configurada una autorización.
    autorizacion_facturas_id = fields.Many2one(
        'l10n_ec_sri.autorizacion', string='Autorizacion en facturas', )
    autorizacion_notas_credito_id = fields.Many2one(
        'l10n_ec_sri.autorizacion', string='Autorizacion en notas de crédito', )
    autorizacion_retenciones_id = fields.Many2one(
        'l10n_ec_sri.autorizacion', string='Autorizacion en retenciones', )
    autorizacion_liquidaciones_id = fields.Many2one(
        'l10n_ec_sri.autorizacion', string='Autorizacion en liquidaciones', )
    emitir_retenciones_en_cero = fields.Boolean(
        string='Emitir retenciones en cero',
    )

