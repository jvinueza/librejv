# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountFiscalPosition(models.Model):
    _inherit = 'account.fiscal.position'
    _order = 'sequence asc'

    sequence = fields.Integer(string="Secuencia", )
    identificacion_id = fields.Many2one(
        'l10n_ec_sri.identificacion', ondelete='restrict',
        string="Tipo de identificación", )
    persona_id = fields.Many2one(
        'l10n_ec_sri.persona', ondelete='restrict',
        string="Tipo de persona", )
    formapago_id = fields.Many2one(
        'l10n_ec_sri.formapago', ondelete='restrict',
        string="Forma de pago", )
    es_publica = fields.Boolean('¿Es una Institucion publica?', )
    obligada_contabilidad = fields.Boolean(
        '¿Obligada a llevar contabilidad?', )
    contribuyente_especial = fields.Boolean(
        '¿Es contribuyente especial?', )

    tipopago_id = fields.Many2one(
        'l10n_ec_sri.tipopago', string='Tipo de pago', )
    property_account_payable_id = fields.Many2one(
        'account.account', string="Cuenta como proveedor",
        domain="[('internal_type','=','payable'), ('deprecated','=',False)]",
        help="La cuenta para el registro de las cuentas por pagar (en compras).", )
    property_account_receivable_id = fields.Many2one(
        'account.account', string="Cuenta como cliente",
        domain="[('internal_type','=','receivable'),('deprecated','=',False)]",
        help="La cuenta para el registro de las cuentas por cobrar (en ventas).", )

    # Borrar, agregado a res.country para facilitar la configuración por país.
    doble_tributacion = fields.Boolean('No usar, borrar en futura actualizacion')
    aplicconvdobtrib = fields.Boolean(string='¿Aplica convenio de doble tributación?', )
    paraiso_fiscal = fields.Boolean('¿Reside en un paraiso fiscal?')

