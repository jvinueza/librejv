# -*- coding: utf-8 -*-
from odoo import models, fields


class FormaPago(models.Model):
    _name = 'l10n_ec_sri.formapago'

    name = fields.Char('Forma de pago')
    code = fields.Char('Codigo', size=2)
    sequence = fields.Integer(string="Secuencia", )
    active = fields.Boolean("Activo")

