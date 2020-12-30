# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    formapago_id = fields.Many2one(
        'l10n_ec_sri.formapago', string='Forma de pago')

    tax_form_ids = fields.Many2many(
        'l10n_ec_sri.tax.form', 'payment_tax_form_rel', 'tax_form_ids',
        'payment_ids', string="Tax Form", )

    @api.onchange('journal_id')
    def _onchange_journal_sri(self):
        if self.journal_id:
            if not self.formapago_id:
                self.formapago_id = self.journal_id.formapago_id
