# -*- coding: utf-8 -*-
from odoo import models, fields, api


class Comprobante(models.Model):
    _name = 'l10n_ec_sri.comprobante'
    _order = 'sequence asc'

    name = fields.Char('Comprobante', )
    sequence = fields.Integer(string="Secuencia", )
    code = fields.Char('Codigo', size=2, readonly=True, )
    requiere_autorizacion = fields.Boolean(
        '¿Requiere autorizacion del S.R.I.?', )
    en_compras = fields.Boolean(string="¿Es comprobante de adquisiciones?", )
    en_ventas = fields.Boolean(string="¿Es comprobante de ventas?", )
    es_retencion = fields.Boolean(string="¿Es comprobante de retencion?", )


class ComprobantesAnulados(models.Model):
    _name = 'l10n_ec_sri.comprobantesanulados'

    fecha = fields.Date(
        'Fecha de anulación',
        required=True, )
    secuencialinicio = fields.Integer(
        'Secuencial inicial',
        required=True, )
    secuencialfin = fields.Integer(
        'Secuencial final',
        required=True, )
    autorizacion_id = fields.Many2one(
        'l10n_ec_sri.autorizacion', ondelete='restrict',
        string="Autorizacion",
        required=True, )
    comprobante_id = fields.Many2one(
        'l10n_ec_sri.comprobante', ondelete='restrict',
        string="Comprobante",
        required=True,
        domain=[('requiere_autorizacion', '=', True)])
    sri_tax_form_set_id = fields.Many2one(
        'l10n_ec_sri.tax.form.set',
        string='Declaración',
    )
    autorizacion = fields.Char(string='Autorizacion', )

    @api.multi
    @api.onchange('secuencialinicio')
    def _onchange_secuencialinicio(self):
        for r in self:
            if r.secuencialinicio:
                r.secuencialfin = r.secuencialinicio

