# -*- coding: utf-8 -*-
from odoo import models, fields


class Sustento(models.Model):
    _name = 'l10n_ec_sri.sustento'

    name = fields.Char('Sustento Tributario')
    code = fields.Char('Codigo', size=2)
    description = fields.Char('Descripcion')
    sequence = fields.Integer(string="Secuencia", )
