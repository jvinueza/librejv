# -*- coding: utf-8 -*-
####################################################
# Parte del Proyecto LibreGOB: http://libregob.org #
# Licencia AGPL-v3                                 #
####################################################

from odoo import models, fields, api

class ResCountry(models.Model):
    _inherit = 'res.country'

    # TABLA 19
    tiporegi = fields.Selection([
            ('01','Régimen general'),
            ('02','Paraíso fiscal'),
            ('03','Régimen fiscal preferente o jurisdicción de menor imposición'),
        ], default="01",
        string='Tipo de régimen',
    )
    aplicconvdobtrib = fields.Boolean(string='¿Aplica convenio de doble tributación?', )

    # TABLA 16
    codigo = fields.Char(string='Código (SRI)', )
    denopago = fields.Char(string='Denominación (SRI)', )

    pagextsujretnorleg = fields.Boolean(string='¿Pago al exterior sujeto a retención?', )

