# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.osv import expression


class Autorizacion(models.Model):
    _name = 'l10n_ec_sri.autorizacion'
    _description = "Autorizaciones"

    name = fields.Char(string="Autorizacion",)
    autorizacion = fields.Char('Nro. de autorizacion', related="name", )
    establecimiento = fields.Char(
        'Establecimiento',
        size=3,
        required=True,
    )
    puntoemision = fields.Char(
        'Punto de impresion',
        size=3,
        required=True,
    )
    fechaemision = fields.Date('Fecha de emision', )
    fechavencimiento = fields.Date('Fecha de vencimiento', )
    secuencia_inicial = fields.Integer('Secuencia inicial', )
    secuencia_final = fields.Integer('Secuencia final', )
    secuencia_actual = fields.Integer(
        string='Último secuencial utilizado',
    )
    comprobante_id = fields.Many2one(
        'l10n_ec_sri.comprobante',
        string="Comprobante",
        required=True,
        domain=[('requiere_autorizacion', '=', True)],)
    c_invoice_ids = fields.One2many(
        'account.invoice', inverse_name='autorizacion_id', ondelete='restrict',
        string="Facturas", )
    r_invoice_ids = fields.One2many(
        'account.invoice', inverse_name='r_autorizacion_id', ondelete='restrict',
        string="Retenciones", )
    comprobantesanulados_ids = fields.One2many('l10n_ec_sri.comprobantesanulados', inverse_name='autorizacion_id',
                                               ondelete='restrict', string="Comprobantes anulados", )
    revisar = fields.Char(string="Comprobantes no registrados",
                          compute="_compute_c_ids", )

    @api.multi
    @api.onchange('establecimiento')
    def _onchange_establecimiento(self):
        for r in self:
            if not r.establecimiento:
                return
            if r.establecimiento.isdigit():
                r.establecimiento = r.establecimiento.zfill(3)
            else:
                r.establecimiento = ''

    @api.multi
    @api.onchange('puntoemision')
    def _onchange_puntoemision(self):
        for r in self:
            if not r.puntoemision:
                return
            if r.puntoemision.isdigit():
                r.puntoemision = r.puntoemision.zfill(3)
            else:
                r.puntoemision = ''

    # tipoEm se usa en el ATS.
    tipoem = fields.Selection(
        [
            ('F', 'Facturación física'),
            ('E', 'Facturación electrónica'),
        ],
        required=True,
        string='Tipo de emisión',
        defaut='F', )  # Default F es importante para que las facturas actuales sean todas físicas.

    # Facturación electrónica.
    direstablecimiento = fields.Char('Dirección del establecimiento', )

    @api.multi
    def name_get(self):
        res = []
        for r in self:
            name = '-'.join([
                r.comprobante_id.name or '',
                r.establecimiento or '',
                r.puntoemision or '',
                r.autorizacion or '',
            ])
            res.append((r.id, name))
        return res

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        args = args or []
        domain = []
        if name:
            domain = ['|', ('establecimiento', '=ilike', name + '%'),
                      '|', ('puntoemision', '=ilike', name + '%'),
                      ('autorizacion', operator, name)]
            if operator in expression.NEGATIVE_TERM_OPERATORS:
                domain = ['&'] + domain
        autorizaciones = self.search(domain + args, limit=limit)
        return autorizaciones.name_get()

    @api.multi
    @api.depends('secuencia_inicial', 'secuencia_actual', 'c_invoice_ids', 'comprobantesanulados_ids')
    def _compute_c_ids(self):
        for r in self:
            if r.tipoem == 'E' or r.secuencia_inicial == 0:
                return

            anulados = list()
            revisar = ''
            for a in r.comprobantesanulados_ids:
                for i in range(a.secuencialinicio, (a.secuencialfin + 1), 1):
                    anulados.append(i)
            for n in range(r.secuencia_inicial, (r.secuencia_actual + 1), 1):
                if any(inv.secuencial == n for inv in r.c_invoice_ids) \
                    or any(inv.secuencial == n for inv in r.r_invoice_ids):
                    continue
                else:
                    if n not in anulados:
                        revisar += str(n) + ', '
                        r.revisar = revisar

    @api.onchange('autorizacion')
    def _onchange_autorizacion(self):
        self.name = self.autorizacion

