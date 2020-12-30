# -*- coding: utf-8 -*-
from odoo import fields, models, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    enviar_facturas_electronicas = fields.Boolean(
        string='Enviar facturas electrónicas',
        default=True,
    )
    enviar_notas_de_credito_electronicas = fields.Boolean(
        string='Enviar notas de credito electrónicas',
        default=True,
    )
    enviar_retenciones_electronicas = fields.Boolean(
        string='Enviar retenciones electrónicas',
        default=True,
    )

