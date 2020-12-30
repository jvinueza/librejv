# -*- coding: utf-8 -*-
####################################################
# Parte del Proyecto LibreGOB: http://libregob.org #
# Licencia AGPL-v3                                 #
####################################################
import json

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from ..models.account_invoice import RET_VENTAS, RET_COMPRAS, RET_IR_COMPRAS
from odoo.tools import float_is_zero, float_compare


class SaleRetentionWizard(models.TransientModel):
    _name = 'l10n_ec_sri.sale.retention.wizard'
    _description = 'Sale Retention Wiz'

    r_comprobante_id = fields.Many2one(
        "l10n_ec_sri.comprobante",
        string="Comprobante retención",
        domain="[('es_retencion','=', True)]",
        default=lambda self: self.env.ref('l10n_ec_sri.comprobante_07'),
    )
    estabretencion1 = fields.Char(
        "Establecimiento de la retención",
        size=3,
        required=True,
    )
    ptoemiretencion1 = fields.Char(
        "Punto de emsión de la retención",
        size=3,
        required=True,
    )
    autretencion1 = fields.Char(
        "Autorización de la retención",
        required=True,
    )
    secretencion1 = fields.Char(
        "Secuencial de la retención",
        required=True,
    )
    fechaemiret1 = fields.Date(
        "Fecha de la retención",
        required=True,
    )
    date = fields.Date(
        "Fecha de contabilización",
    )
    invoice_id = fields.Many2one(
        'account.invoice',
        string='Invoice',
        required=True,
    )
    type = fields.Selection(
        related="invoice_id.type",
        string='Type',
    )

    wizard_line_ids = fields.One2many(
        'l10n_ec_sri.sale.retention.wizard.line',
        'wizard_id',
        string='Wizard lines',
        required=True,
    )

    @api.multi
    @api.onchange('estabretencion1', 'ptoemiretencion1', 'secretencion1')
    def _onchange_sri_secuencial_completo_retencion(self):
        for r in self:
            if r. estabretencion1 and r.estabretencion1.isdigit():
                r.estabretencion1 = r.estabretencion1.zfill(3)
            if r.ptoemiretencion1 and r.ptoemiretencion1.isdigit():
                r.ptoemiretencion1 = r.ptoemiretencion1.zfill(3)
            if r.secretencion1 and r.secretencion1.isdigit():
                r.secretencion1 = r.secretencion1.zfill(9)

    @api.multi
    @api.onchange('fechaemiret1')
    def _onchange_fechaemiret1(self):
        for r in self:
            # Por defecto, lo declaramos en la misma fecha contable.
            r.date = r.invoice_id.date

    @api.multi
    def button_registrar_retencion(self):
        inv = self.invoice_id
        taxes = inv.sri_tax_line_ids + inv.r_sri_tax_line_ids
        groups = taxes.mapped('group')

        if 'RetIva' in groups:
            ret_iva = taxes.filtered(lambda x: x.group == 'RetIva')
            ret_iva_amount = sum(ret_iva.mapped('amount'))
            if ret_iva_amount == 0:
                ret_iva.unlink()
                groups.remove('RetIva')

        if any(r in RET_COMPRAS or r in RET_VENTAS for r in groups):
            raise UserError(_("Ya existen retenciones ingresadas para esta factura."))

        line_ids = []
        tax_line_ids = []
        amount = sum(self.wizard_line_ids.mapped('amount'))

        type = 'out' if inv.type == 'out_invoice' else 'in'
        # Restamos de la cuenta por cobrar todo el valor de la retención.
        line_ids.append((0, 0, {
            'name': 'Retención de factura: %s' % inv.get_sri_secuencial_completo_factura(),
            'debit': 0.0 if type == 'out' else amount ,
            'credit': amount if type == 'out' else 0.0,
            'account_id': inv.account_id.id,
            'partner_id': inv.partner_id.id,
        }))

        # Solo agregamos en compras porque en ventas obtenemos los valores de la
        # retención directamente de los impuestos debido a que en ventas solo se declaran
        # las retenciones físicas que nos han realizado y se pueden declarar en meses posteriores.

        if type == 'in':
            for l in self.wizard_line_ids:
                if not l.sustento_id:
                    raise UserError(_("Debe registar un sustento tributario para la retención."))
                ats_line = self.invoice_id.sri_ats_line_ids.filtered(
                    lambda x: x.codsustento == l.sustento_id.code
                )
                name = l.tax_id.tax_group_id.name
                if len(ats_line) == 1:
                    # Asignamos directamente puesto que no deben existir
                    # retenciones manuales y automáticas en la misma factura.
                    if name == "RetBien10":
                        ats_line.valretbien10 = l.amount
                    elif name == "RetServ20":
                        ats_line.valretserv20 = l.amount
                    elif name == "RetServ50":
                        ats_line.valretserv50 = l.amount
                    elif name == "RetBienes":
                        ats_line.valorretbienes = l.amount
                    elif name == "RetServicios":
                        ats_line.valorretservicios = l.amount
                    elif name == "RetServ100":
                        ats_line.valretserv100 = l.amount
                    elif name in RET_IR_COMPRAS:
                        ats_line.detalleair_ids.create(
                            {
                                "valretair": abs(l.amount),
                                "baseimpair": l.base,
                                "codretair": l.tax_id.impuesto,
                                "porcentajeair": abs(l.tax_id.amount),
                                "sri_ats_line_id": ats_line.id
                            }
                        )
                    else:
                        raise UserError(
                            _(
                                "No se ha encontrado una línea de declaración del ATS"
                                " para el sustento tributario {}".format(l.sustento_id.code)
                            )
                        )

        for l in self.wizard_line_ids:
            line_ids.append(
                (0, 0, {
                    'name': l.tax_id.name,
                    'debit': l.amount if type == 'out' else 0.0,
                    'credit': 0.0 if type == 'out' else l.amount,
                    'account_id': l.account_id.id,
                    'tax_line_id': l.tax_id.id,
                    }
                )
            )

            tax = l.tax_id
            formulario, campo = tax.get_data_from_tag(tax.tag_ids)
            tax_line_ids.append((0,0,
                {
                    "r_invoice_id": inv.id,
                    "fecha_declaracion": self.date,
                    "formulario": formulario,
                    "campo": campo,
                    "group": tax.tax_group_id.name,
                    "amount": l.amount,
                    "base": l.base,
                    "porcentaje": str(abs(int(tax.amount))),
                    "impuesto": tax.impuesto,
                    "codigo": tax.codigo,
                    "codigoporcentaje": tax.codigoporcentaje,
                }
            ))

        inv.r_sri_tax_line_ids = tax_line_ids

        vals = {
            'journal_id': inv.journal_id.id,
            'date': self.date or self.fechaemiret1,
            'state': 'draft',
            'line_ids': line_ids,
            'partner_id': inv.partner_id.id,
        }
        r_move = self.env['account.move'].create(vals)
        r_move.post()
        inv.write(
            {
                'r_comprobante_id': self.r_comprobante_id.id,
                'estabretencion1': self.estabretencion1,
                'ptoemiretencion1': self.ptoemiretencion1,
                'autretencion1': self.autretencion1,
                'secretencion1': self.secretencion1,
                'fechaemiret1': self.fechaemiret1,
                'r_move_id': r_move.id,
            }
        )
        if inv.state == 'paid':
            return True
        if inv.type == 'out_invoice':
            credit_aml = r_move.line_ids.filtered(lambda x: x.credit > 0)
        elif inv.type == 'in_invoice':
            credit_aml = r_move.line_ids.filtered(lambda x: x.debit > 0)
        if inv.state == 'open' and credit_aml:
            inv.register_payment(credit_aml)
            return True


class SaleRetentionWizardLine(models.TransientModel):
    _name = 'l10n_ec_sri.sale.retention.wizard.line'
    _description = 'Sale Retention Wiz Line'

    wizard_id = fields.Many2one('l10n_ec_sri.sale.retention.wizard', string='Wizard', )
    tax_id = fields.Many2one(
        'account.tax',
        string='Impuesto',
        required=True,
    )
    base = fields.Float(
        "Base imponible",
        digits=(9, 2),
        required=True,
    )
    amount = fields.Float(
        "Valor del impuesto",
        digits=(9, 2),
        required=True,
    )
    account_id = fields.Many2one(
        'account.account',
        string='Cuenta',
        required=True,
    )
    sustento_id = fields.Many2one(
        'l10n_ec_sri.sustento', ondelete='restrict',
        string="Sustento tributario", )

    @api.multi
    @api.onchange('tax_id')
    def _onchange_tax_id(self):
        for r in self:
            if r.tax_id:
                r.account_id = r.tax_id.account_id.id
            else:
                inv = r.wizard_id.invoice_id
                if inv.type == "in_invoice":
                    RET = RET_COMPRAS
                elif inv.type == "out_invoice":
                    RET = RET_VENTAS
                else:
                    raise UserError(_("Solo puede registrar retenciones en facturas."))
                group = self.env['account.tax.group'].search([('name','in', RET)])
                codsustento = r.wizard_id.invoice_id.sri_ats_line_ids.mapped('codsustento')
                domain = {'domain':{
                    'tax_id':[('tax_group_id','in', group.ids)],
                    'sustento_id': [('code', 'in', codsustento)]
                }}
                return domain

    @api.multi
    @api.onchange('base', 'tax_id')
    def _onchange_base(self):
        """
        Calculamos el valor del impuesto en base al porcentaje directamente
        puesto que en retenciones en ventas no hay casos especiales.
        """
        for r in self:
            if not r.base or not r.tax_id:
                return
            self.amount = abs(self.base * self.tax_id.amount / 100)

