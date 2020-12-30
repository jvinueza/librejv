# -*- coding: utf-8 -*-
from odoo import models, fields


class Persona(models.Model):
    _name = 'l10n_ec_sri.persona'

    name = fields.Char('Tipo de proveedor')
    code = fields.Char('Codigo', size=1)
    tpidprov = fields.Char(
        'Tipo de identificacion del Proveedor', size=2, )
