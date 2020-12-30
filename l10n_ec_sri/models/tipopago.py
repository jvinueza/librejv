# -*- coding: utf-8 -*-
from odoo import models, fields


class TipoPago(models.Model):
    _name = 'l10n_ec_sri.tipopago'

    name = fields.Char('Tipo de pago')
    code = fields.Char('Codigo', size=2)

