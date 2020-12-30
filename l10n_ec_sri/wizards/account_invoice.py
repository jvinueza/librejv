# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SriMultiDataWizard(models.TransientModel):
    _name = "l10n_ec_sri.multi.data.wizard"
    _description = "Register multiple SRI information on invoices."

    estabretencion1 = fields.Char('Establecimiento de la retención', size=3, )
    ptoemiretencion1 = fields.Char('Punto de emsión de la retención', size=3, )
    autretencion1 = fields.Char('Autorización de la retención', )
    secretencion1 = fields.Char('Secuencial de la retención', )
    fechaemiret1 = fields.Date('Fecha de la retención', )


    def _get_sri_data(self):
        """ Hook for extension """
        return {
            'estabretencion1': self.estabretencion1,
            'ptoemiretencion1': self.ptoemiretencion1,
            'autretencion1': self.autretencion1,
            'secretencion1': self.secretencion1,
            'fechaemiret1': self.fechaemiret1,
        }


    @api.multi
    def register_sri_data(self):
        self.ensure_one()
        context = dict(self._context or {})
        active_model = context.get('active_model')
        active_ids = context.get('active_ids')

        if not active_model or not active_ids:
            raise UserError(_("Programmation error: wizard action executed without active_model or active_ids in context."))
        if active_model != 'account.invoice':
            raise UserError(_("Programmation error: the expected model for this action is 'account.invoice'. The provided one is '%d'.") % active_model)

        # Checks on received invoice records
        invoices = self.env[active_model].browse(active_ids)
        if any(invoice.state not in ('open','paid') for invoice in invoices):
            raise UserError(_("You can only register retention data for open or paid"))

        data = self._get_sri_data()
        invoices.write(data)

        return True
