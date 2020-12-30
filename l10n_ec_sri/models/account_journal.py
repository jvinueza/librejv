# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountJournal(models.Model):
    _inherit = ['account.journal']

    formapago_id = fields.Many2one(
        'l10n_ec_sri.formapago', string='Forma de pago', )
