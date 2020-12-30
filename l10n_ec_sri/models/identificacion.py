# -*- coding: utf-8 -*-
from odoo import models, fields


class Identificacion(models.Model):
    _name = 'l10n_ec_sri.identificacion'
    _description = 'Modelo para el manejo de tipos de identificaciones'

    name = fields.Char(string='Tipo de identificación')
    code = fields.Char(string='Código', size=2)
    active = fields.Boolean('Activo', default=True)
    description = fields.Char(string='Descripción')
    tpidprov = fields.Char(string='Código en compras', size=2)
    tpidcliente = fields.Char(string='Código en ventas', size=2)
