# -*- coding: utf-8 -*-
import base64
import logging

from collections import OrderedDict
from datetime import datetime 

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from .account_invoice import RET_IR_COMPRAS, RET_IR_VENTAS, RET_IVA_COMPRAS, RET_IVA_VENTAS

_logger = logging.getLogger(__name__)

try:
    import xmltodict
except ImportError:
    _logger.error(
        "The module xmltodict can't be loaded, try: pip install xmltodict")


class SriTaxFormSet(models.Model):
    _name = 'l10n_ec_sri.tax.form.set'
    _inherit = 'bi.abstract.report'      #desmarcado jvinueza
    _order = 'date_from'

    @api.multi
    def prepare_sri_declaration(self):
        for s in self:
            invoices = s.in_invoice_ids + s.in_refund_ids + \
                s.out_invoice_ids + s.out_refund_ids
            for inv in invoices:
                inv.button_prepare_sri_declaration()

    @api.multi
    def get_invoices(self):
        for s in self:
            # Obtenemos todas las facturas abiertas y pagadas del periodo.
            invoices = self.env['account.invoice'].search([
                ('state', 'in', ('open', 'paid')),
                ('date', ">=", self.date_from),
                ('date', '<=', self.date_to),
            ])
            no_declarado = invoices.filtered(
                lambda x: x.comprobante_id.code in ('NA', False))
            invoices -= no_declarado

            out_invoice = invoices.filtered(lambda x: x.type == 'out_invoice')

            # Agregamos las devoluciones en venta sin valor a las ventas
            # puesto que así se ingresan las retenciones de tarjeta de crédito.
            out_invoice += invoices.filtered(lambda x: x.subtotal ==
                                             0 and x.type == 'out_refund')

            # Restamos las facturas ya procesadas para mejorar el rendimiento.
            invoices -= out_invoice

            in_invoice = invoices.filtered(lambda x: x.type == 'in_invoice')
            invoices -= in_invoice

            # No restamos lo procesado porque la lista es pequeña.
            in_refund = invoices.filtered(lambda x: x.type == 'in_refund')
            out_refund = invoices.filtered(lambda x: x.type == 'out_refund')

            # Agregamos las retenciones manuales en ventas a la declaración.
            sri_tax_line_obj = self.env['l10n_ec_sri.tax.line']
            out_r = sri_tax_line_obj.search([
                ('r_invoice_id.type', '=', 'out_invoice'),
                ('r_invoice_id.state', 'in', ('open', 'paid')),
                ('r_invoice_id', 'not in', out_invoice.ids),
                ('fecha_declaracion', '>=', self.date_from),
                ('fecha_declaracion', '<=', self.date_to),
            ])

            ca_obj = self.env['l10n_ec_sri.comprobantesanulados']
            comprobantesanulados = ca_obj.search([
                ('fecha','>=', self.date_from),
                ('fecha','<=', self.date_to)
            ])

            s.update({
                'no_declarado_ids': no_declarado,
                'out_invoice_ids': out_invoice,
                'out_refund_ids': out_refund,
                'in_invoice_ids': in_invoice,
                'in_refund_ids': in_refund,
                'out_r_sri_tax_line_ids': out_r,
                'comprobantesanulados_ids': comprobantesanulados
            })


    date_from = fields.Date('Desde', required=True, )
    date_to = fields.Date('Hasta', required=True, )

    sri_tax_form_ids = fields.One2many(
        'l10n_ec_sri.tax.form', inverse_name='sri_tax_form_set_id',
        string='Tax declarations', )

    no_declarado_ids = fields.Many2many(
        'account.invoice', 'no_declarado_tax_form_set_rel', 'no_declarado_ids',
        'no_declarado_tax_form_set_ids', string="Comprobantes no declarados", )
    in_invoice_ids = fields.Many2many(
        'account.invoice', 'in_inv_tax_form_set_rel', 'in_invoice_ids',
        'in_inv_tax_form_set_ids', string="In invoices", )
    out_invoice_ids = fields.Many2many(
        'account.invoice', 'out_inv_tax_form_set_rel', 'out_invoice_ids',
        'out_inv_tax_form_set_ids', string="Out invoices", )
    in_refund_ids = fields.Many2many(
        'account.invoice', 'in_ref_tax_form_set_rel', 'in_refund_ids',
        'in_ref_tax_form_set_ids', string="In refunds", )
    out_refund_ids = fields.Many2many(
        'account.invoice', 'out_ref_tax_form_set_rel', 'out_refund_ids',
        'out_ref_tax_form_set_ids', string="Out refunds", )
    in_reembolso_ids = fields.One2many(
        'account.invoice', string='Reembolsos en compras',
        compute='_compute_reembolsos', readonly=True, )
    out_r_sri_tax_line_ids = fields.Many2many(
        'l10n_ec_sri.tax.line',
        'out_r_sri_tax_line_tax_form_rel',
        'tax_form_ids',
        'out_r_sri_tax_line_ids',
        string='Reteciones manuales en ventas (de periodos anteriores)',
    )
    comprobantesanulados_ids = fields.One2many(
        'l10n_ec_sri.comprobantesanulados',
        'sri_tax_form_set_id',
        string='Comprobantes anulados',
    )

    @api.multi
    @api.depends('in_invoice_ids', 'out_invoice_ids')
    def _compute_reembolsos(self):
        for f in self:
            f.in_reembolso_ids = f.in_invoice_ids.mapped("reembolso_ids")

    @api.multi
    def get_report_data(self):
        totales = [
            [
                '',
                'TIPO DE EMISIÓN',
                'ESTABLECIMIENTO',
                'NRO COMPROBANTES',
                'SUBTOTAL GRAVADO',
                'SUBTOTAL SIN IVA',
                'IVA',
                'ICE',
                'TOTAL',
                'RETENCIONES'
            ]
        ]
        sheets = []
        out_inv = [
            [
                'CI / RUC',
                'CLIENTE',
                'DIARIO',
                'REFERENCIA',
                'COMPROBANTE',
                'TIPO EMISIÓN',
                'ESTABLECIMIENTO',
                'PUNTO DE EMISIÓN',
                'SECUENCIAL',
                'FECHA DE EMISIÓN',
                'SUBTOTAL GRAVADO',
                'SUBTOTAL SIN IVA',
                'IVA',
                'ICE',
                'TOTAL',
                'RETENCIONES IR',
                'RETENCIONES IVA',
                'TOTAL RETENCIONES',
                'SERIE COMPROBANTE RETENCIÓN',
                'AUTORIZACION RETENCIÓN',
                'FECHA EMISIÓN RETENCIÓN',
            ]
        ]
        # Total ventas establecimiento (tve)
        tve = {}
        for inv in self.out_invoice_ids.sorted(
            key=lambda x: x.get_sri_secuencial_completo_factura()
        ):
            key = inv.establecimiento + inv.tipoem
            total_retenciones_ir = inv._get_impuestos_por_periodo(
                amount=True, groups=RET_IR_VENTAS,
                date_from=self.date_from, date_to=self.date_to
            )
            total_retenciones_iva = inv._get_impuestos_por_periodo(
                amount=True, groups=RET_IVA_VENTAS,
                date_from=self.date_from, date_to=self.date_to
            )
            total_retenciones = total_retenciones_ir + total_retenciones_iva
            if key in tve.keys():
                estab = tve[key]
                estab[1] += 1
                estab[2] += inv.baseimpgrav
                estab[3] += inv.subtotal_sin_iva
                estab[4] += inv.montoiva
                estab[5] += inv.montoice
                estab[6] += inv.total
                estab[7] += total_retenciones_ir
                estab[8] += total_retenciones_iva
                estab[9] += total_retenciones
            else:
                tve.update(
                    {key:
                        [
                            inv.establecimiento,
                            1,
                            inv.baseimpgrav,
                            inv.subtotal_sin_iva,
                            inv.montoiva,
                            inv.montoice,
                            inv.total,
                            total_retenciones_ir,
                            total_retenciones_iva,
                            total_retenciones
                        ]
                    }
                )
            has_ret = 'PENDIENTE' if inv.total_retenciones > 0 else ''
            ret = inv.secretencion1 and True or False
            out_inv.append(
                [
                    inv.partner_id.vat,
                    inv.partner_id.name,
                    inv.journal_id.name,
                    inv.name or '',
                    inv.comprobante_id.name,
                    inv.tipoem,
                    inv.establecimiento,
                    inv.puntoemision,
                    inv.secuencial.zfill(9),
                    inv.date_invoice,
                    inv.baseimpgrav,
                    inv.subtotal_sin_iva,
                    inv.montoiva,
                    inv.montoice,
                    inv.total,
                    total_retenciones_ir,
                    total_retenciones_iva,
                    total_retenciones,
                    ret and inv.get_sri_secuencial_completo_retencion() or has_ret,
                    ret and inv.autretencion1 or has_ret,
                    ret and inv.fechaemiret1 or has_ret,
                ]
            )

        # Agregamos todas las retenciones manuales.
        for inv in self.out_r_sri_tax_line_ids.mapped('r_invoice_id').sorted(
            key=lambda x: x.get_sri_secuencial_completo_factura()
        ):
            # Usamos el total de retenciones de la factura puesto que la
            # necesidad del comprobante depende del total de retenciones y
            # no de las retenciones del periodo.
            has_ret = 'PENDIENTE' if inv.total_retenciones > 0 else ''
            ret = inv.secretencion1 and True or False

            # No filtramos puesto que todas las retenciones pertenecen al mismo periodo.
            total_retenciones_ir = sum(
                inv.r_sri_tax_line_ids.filtered(
                    lambda x: x.group in RET_IR_VENTAS
                ).mapped('amount')
            )
            total_retenciones_iva = sum(
                inv.r_sri_tax_line_ids.filtered(
                    lambda x: x.group in RET_IVA_VENTAS
                ).mapped('amount')
            )
            total_retenciones = total_retenciones_ir + total_retenciones_iva
            out_inv.append(
                [
                    inv.partner_id.vat,
                    inv.partner_id.name,
                    inv.journal_id.name,
                    inv.name or '',
                    inv.comprobante_id.name,
                    inv.tipoem,
                    inv.establecimiento,
                    inv.puntoemision,
                    inv.secuencial.zfill(9),
                    inv.date_invoice,
                    0, # inv.baseimpgrav,
                    0, # inv.subtotal_sin_iva,
                    0, # inv.montoiva,
                    0, # inv.montoice,
                    0, # inv.total,
                    total_retenciones_ir,
                    total_retenciones_iva,
                    total_retenciones,
                    ret and inv.get_sri_secuencial_completo_retencion() or has_ret,
                    ret and inv.autretencion1 or has_ret,
                    ret and inv.fechaemiret1 or has_ret,
                ]
            )

        sheets.append({
            'name': 'VENTAS',
            'rows': out_inv
        })

        out_ref = [
            [
                'CI / RUC',
                'CLIENTE',
                'DIARIO',
                'REFERENCIA',
                'COMPROBANTE',
                'TIPO EMISIÓN',
                'ESTABLECIMIENTO',
                'PUNTO DE EMISIÓN',
                'SECUENCIAL',
                'FECHA DE EMISIÓN',
                'SUBTOTAL GRAVADO',
                'SUBTOTAL SIN IVA',
                'IVA',
                'ICE',
                'TOTAL',
            ]
        ]

        tnce = {}
        for ref in self.out_refund_ids.sorted(
            key=lambda x: x.get_sri_secuencial_completo_factura()
        ):
            key = ref.establecimiento + ref.tipoem
            if key in tnce.keys():
                estab[1] += 1
                estab[2] += ref.baseimpgrav
                estab[3] += ref.subtotal_sin_iva
                estab[4] += ref.montoiva
                estab[5] += ref.montoice
                estab[6] += ref.total
                estab[7] += ref.total_retenciones
            else:
                tnce.update(
                    {key:
                        [
                            ref.establecimiento,
                            1,
                            ref.baseimpgrav,
                            ref.subtotal_sin_iva,
                            ref.montoiva,
                            ref.montoice,
                            ref.total,
                            ref.total_retenciones
                        ]
                    }
                )
            out_ref.append(
                [
                    ref.partner_id.vat,
                    ref.partner_id.name,
                    ref.journal_id.name,
                    ref.name or '',
                    ref.comprobante_id.name,
                    ref.tipoem,
                    ref.establecimiento,
                    ref.puntoemision,
                    ref.secuencial.zfill(9),
                    ref.date_invoice,
                    ref.baseimpgrav,
                    ref.subtotal_sin_iva,
                    ref.montoiva,
                    ref.montoice,
                    ref.total,
                ]
            )

        sheets.append({
            'name': 'NC EN VENTAS',
            'rows': out_ref
        })
        
        for estab in list(set([*tve] + [*tnce])):
            tipoem = "ELECTRÓNICA"
            establecimiento = estab[:-1]
            if 'F' in estab:
                tipoem = "FÍSICA"
            v = tve.get(estab, [establecimiento,tipoem,0,0,0,0,0,0])
            totales.append(
                [
                    'VENTAS',
                    tipoem,
                    v[0],
                    v[1],
                    v[2],
                    v[3],
                    v[4],
                    v[5],
                    v[6],
                    v[7]
                ]
            )
            nc = tnce.get(estab, [establecimiento,0,0,0,0,0,0,0])
            totales.append(
                [
                    'NOTAS DE CRÉDITO',
                    tipoem,
                    nc[0],
                    nc[1],
                    nc[2],
                    nc[3],
                    nc[4],
                    nc[5],
                    nc[6],
                    nc[7]
                ]
            )

        in_inv = [
            [
                'RUC PROVEEDOR',
                'PROVEEDOR',
                'DIARIO',
                'REFERENCIA',
                'COMPROBANTE',
                'TIPO EMISIÓN',
                'TIPO ID PROVEEDOR',
                'SERIE COMPROBANTE',
                'AUTORIZACIÓN COMPROBANTE',
                'BASE IMPONIBLE GRABADA',
                'BASE IMPONIBLE',
                'BASE IMPONIBLE EXENTA',
                'BASE QUE NO GRABA IVA',
                'MONTO IVA',
                'MONTO ICE',
                'ESTAB. RETENCIÓN',
                'PTO EMISIÓN RETENCIÓN',
                'SECUENCIAL RETENCIÓN',
                'AUTORIZACIÓN RETENCIÓN',
                'RETENCIONES IVA',
                'RETENCIONES IR',
                'TOTAL RETENCIONES',
            ]
        ]

        for inv in self.in_invoice_ids:
            total_retenciones_ir = inv._get_impuestos_por_periodo(
                amount=True, groups=RET_IR_COMPRAS,
                date_from=self.date_from, date_to=self.date_to
            )
            total_retenciones_iva = inv._get_impuestos_por_periodo(
                amount=True, groups=RET_IVA_COMPRAS,
                date_from=self.date_from, date_to=self.date_to
            )
            total_retenciones = total_retenciones_ir + total_retenciones_iva
            in_inv.append(
                [
                    inv.partner_id.vat,
                    inv.partner_id.name,
                    inv.journal_id.name,
                    inv.reference or '',
                    inv.comprobante_id.name,
                    inv.tipoem,
                    inv.partner_id.property_account_position_id.identificacion_id.code,
                    inv.get_sri_secuencial_completo_factura(),
                    inv.autorizacion or '',
                    inv.baseimpgrav,
                    inv.baseimponible,
                    inv.baseimpexe,
                    inv.basenograiva,
                    inv.montoiva,
                    inv.montoice,
                    inv.estabretencion1 or '',
                    inv.ptoemiretencion1 or '',
                    inv.secretencion1 or '',
                    inv.autretencion1 or '',
                    total_retenciones_iva,
                    total_retenciones_ir,
                    total_retenciones
                ]
            )
        sheets.append({
            'name': 'COMPRAS',
            'rows': in_inv
        })

        in_ref = [
            [
                'RUC PROVEEDOR',
                'PROVEEDOR',
                'DIARIO',
                'REFERENCIA',
                'COMPROBANTE',
                'TIPO EMISIÓN',
                'TIPO ID PROVEEDOR',
                'SERIE COMPROBANTE',
                'AUTORIZACIÓN COMPROBANTE',
                'BASE IMPONIBLE GRABADA',
                'BASE IMPONIBLE',
                'BASE IMPONIBLE EXENTA',
                'BASE QUE NO GRABA IVA',
                'MONTO IVA',
                'MONTO ICE',
            ]
        ]

        for ref in self.in_refund_ids:
            in_ref.append(
                [
                    ref.partner_id.vat,
                    ref.partner_id.name,
                    ref.journal_id.name,
                    ref.reference or '',
                    ref.comprobante_id.name,
                    ref.tipoem,
                    ref.partner_id.property_account_position_id.identificacion_id.code,
                    ref.get_sri_secuencial_completo_factura(),
                    ref.autorizacion or '',
                    ref.baseimpgrav,
                    ref.baseimponible,
                    ref.baseimpexe,
                    ref.basenograiva,
                    ref.montoiva,
                    ref.montoice,
                ]
            )
        sheets.append({
            'name': 'NC EN COMPRAS',
            'rows': in_ref
        })
        sheets.append({
            'name': 'TOTALES',
            'rows': totales
        })

        return {
            'wizard': False,
            'filename': 'reporte_de_impuestos.xlsx',
            'sheets': sheets,
        }


class SriTaxForm(models.Model):
    _name = 'l10n_ec_sri.tax.form'
    _order = 'formulario'

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Presentado'),
        ('replaced', 'Sustituido'),
    ],
        string='Estado',
        default='draft', )

    formulario = fields.Selection([
        ('101', '101'),
        ('103', '103'),
        ('104', '104'),
        ('ats', 'Anexo Transaccional'),
    ])
    
    sri_tax_form_set_id = fields.Many2one(
        'l10n_ec_sri.tax.form.set', ondelete='cascade',
        string="Tax Form Set", )
    date_from = fields.Date(
        'Desde', related='sri_tax_form_set_id.date_from', )
    date_to = fields.Date(
        'Hasta', related='sri_tax_form_set_id.date_to', )
    
    sri_tax_form_line_ids = fields.One2many(
        'l10n_ec_sri.tax.form.line',
        inverse_name='sri_tax_form_id',
        string='Tax declarations', )

    payment_ids = fields.Many2many(
        'account.payment', 'payment_tax_form_rel', 'payment_ids',
        'tax_form_ids', string="Payments", )

    move_ids = fields.Many2many(
        'account.move', 'move_tax_form_rel', 'move_ids',
        'tax_form_ids', string="Move", )

    xml_file = fields.Binary('Archivo XML', attachment=True, readonly=True, )
    xml_filename = fields.Char(string="Archivo XML")

    declarar_facturas_electronicas = fields.Boolean(
        string='Declarar facturas electronicas', default=False, )

    @api.multi
    def prepare_ats(self):
        """
        :return: dict con valores del ATS
        """
        
        for f in self:
            inv = self.env['account.invoice']
            form_set = f.sri_tax_form_set_id

            # Para generar los datos de ventas
            ventas_totales = form_set.out_invoice_ids.filtered(
                lambda x: x.comprobante_id.code != '41'
            )
            ventas = self.env['account.invoice']
            tipoem_ventas = 'F'
            if ventas_totales and f.declarar_facturas_electronicas:
                tipoem_ventas = list(set(ventas_totales.mapped('tipoem')))
                if 'F' in tipoem_ventas:
                    raise UserError(_(
                        "No puede declarar las facturas electrónicas si" \
                        "tiene comprobantes de venta físicos emitidos."
                    ))
                retenciones_fisicas = any(len(x.autretencion1 or "NA") == 10 for x in ventas_totales)
                if retenciones_fisicas:
                    raise UserError(_(
                        "No puede declarar las facturas electrónicas si" \
                        "tiene retenciones físicas recibidas."
                    ))
                ventas = ventas_totales
                tipoem_ventas = "E"
            elif ventas_totales:
                ventas = ventas_totales.filtered(lambda x: x.tipoem == 'F')
                tipoem_ventas = "F"

            # Las ventas con comprobante emitido por reembolso.
            reembolsos_totales = form_set.out_invoice_ids.filtered(
                lambda x: x.comprobante_id.code == '41'
            )
            reembolsos = self.env['account.invoice']
            tipoem_reembolsos = 'F'
            if reembolsos_totales and f.declarar_facturas_electronicas:
                tipoem_reembolsos = list(set(reembolsos_totales.mapped('tipoem')))
                if 'F' in tipoem_reembolsos:
                    raise UserError(_(
                        "No puede declarar las reembolsos electrónicos si" \
                        "tiene comprobantes de reembolso físicos emitidos."
                    ))
                retenciones_fisicas = any(len(x.autretencion1 or "NA") == 10 for x in reembolsos_totales)
                if retenciones_fisicas:
                    raise UserError(_(
                        "No puede declarar las reembolsos electrónicos si" \
                        "tiene retenciones físicas recibidas."
                    ))
                reembolsos = reembolsos_totales
                tipoem_ventas = "E"
            elif reembolsos_totales:
                reembolsos = reembolsos_totales.filtered(lambda x: x.tipoem == 'F')
                tipoem_reembolsos = "F"

            devoluciones_totales = form_set.out_refund_ids
            devoluciones = self.env['account.invoice']
            tipoem_devoluciones = "E"
            if devoluciones_totales and f.declarar_facturas_electronicas:
                tipoem_devoluciones = list(set(devoluciones_totales.mapped('tipoem')))
                if 'F' in tipoem:
                    raise UserError(_(
                        "No puede declarar las notas de crédito electrónicas" \
                        "si tiene notas de crédito físicas emitidas."
                    ))
                    devoluciones = devoluciones_totales
                    tipoem_devoluciones = "E"
            elif devoluciones_totales:
                devoluciones = devoluciones_totales.filtered(lambda x: x.tipoem == 'F')
                tipoem_devoluciones = "F"

            detalleVentas = []

            # Agregamos los partners de las retenciones manuales.
            p_retenciones_manuales = form_set.out_r_sri_tax_line_ids.mapped('r_invoice_id.partner_id')

            partners = (ventas_totales + devoluciones_totales + reembolsos_totales).mapped('partner_id')
            partners |= p_retenciones_manuales

            # Necesitamos una segunda lista de partners para comparar los ya procesados.
            pending_partners = self.env['res.partner']
            pending_partners += partners

            for p in partners:
                # Continuamos si el partner ya ha sido procesado.
                if p not in pending_partners:
                    continue

                # Filtramos los partners por cédula y RUC
                vat = p.vat
                if vat and len(vat) == 13:
                    id_fiscal = [vat, vat[:9]]
                elif vat and len(vat) == 10:
                    id_fiscal = [vat, vat + '001']
                else:
                    id_fiscal = [vat]

                contribuyentes = self.env['res.partner']
                contribuyentes = partners.filtered(lambda r: r.vat in id_fiscal)
                # Restamos los partners para evitar duplicar el cálculo.
                pending_partners -= contribuyentes

                fiscal = p.property_account_position_id
                identificacion = fiscal.identificacion_id

                tpidcliente = identificacion.tpidcliente
                vals = OrderedDict([
                    ('tpIdCliente', tpidcliente),
                    ('idCliente', p.vat),
                    ('parteRelVtas', p.parterel and 'SI' or 'NO')
                ])

                if tpidcliente == '06':
                    vals.update(OrderedDict([
                        ('tipoCliente', fiscal.persona_id.tpidprov),
                        # Al declarar el ATS sale un error que indica que se debe
                        # declarar DenoCli cuando el tipo es 06.
                        # ('DenoCli', inv.normalize_text(p.name))
                    ]))

                # Ventas a declarar, filtradas por el tipo de emisión a declarar
                p_ventas = ventas.filtered(
                    lambda r: r.partner_id in contribuyentes
                )
                # Los reembolsos, código 41
                p_reembolsos = reembolsos.filtered(
                    lambda r: r.partner_id in contribuyentes
                )

                # Todas las facturas del partner, independiente al tipo de emisión.
                p_ventas_totales = ventas_totales.filtered(lambda r: r.partner_id in contribuyentes)
                # Filtramos todas las retenciones manuales pertenecientes al partner.
                p_retenciones = form_set.out_r_sri_tax_line_ids.filtered(
                    lambda r: r.r_invoice_id.partner_id in contribuyentes
                )
                # Filtramos las retenciones automaticas a declarar.
                p_retenciones_automaticas = self.env['account.invoice']
                if not self.declarar_facturas_electronicas:
                    p_retenciones_automaticas = p_ventas_totales.filtered(
                        lambda x: len(x.autretencion1 or "NA") == 10
                    )
                else:
                    p_retenciones_automaticas = p_ventas_totales
                # Filtramos las retenciones manuales a declarar.
                p_retenciones_manuales = self.env['l10n_ec_sri.tax.line']
                if not self.declarar_facturas_electronicas:
                    p_retenciones_manuales = p_retenciones.filtered(
                        lambda x: len(x.r_invoice_id.autretencion1 or "NA") == 10
                    )
                else:
                    p_retenciones_manuales = p_retenciones

                if p_ventas or p_retenciones_automaticas or p_retenciones_manuales:
                    # Declaramos las variables en cero porque en caso de
                    # declarar solo retenciones, necesitamos que el valor \
                    # sea cero.
                    basenograiva = 0
                    baseimponible = 0
                    baseimpgrav = 0
                    montoiva = 0
                    montoice = 0
                    formaPago = []

                    # Declaramos las variables de retenciones en cero
                    retenciones_ir = 0
                    retenciones_ir_manuales = 0
                    retenciones_iva = 0
                    retenciones_iva_manuales = 0
                    if p_ventas:
                        t_ventas = p_ventas.mapped('sri_ats_line_ids')
                        ventas -= p_ventas
                        basenograiva = sum(t_ventas.mapped('basenograiva'))
                        baseimponible = sum(t_ventas.mapped('baseimponible'))
                        baseimpgrav = sum(t_ventas.mapped('baseimpgrav'))
                        montoiva = sum(t_ventas.mapped('montoiva'))
                        montoice = sum(t_ventas.mapped('montoice'))
                    retenciones_ir = sum(inv._get_impuestos_por_periodo(
                        amount=True, groups=RET_IR_VENTAS,
                        date_from=form_set.date_from, date_to=form_set.date_to
                    ) for inv in p_retenciones_automaticas)
                    retenciones_iva = sum(inv._get_impuestos_por_periodo(
                        amount=True, groups=RET_IVA_VENTAS,
                        date_from=form_set.date_from, date_to=form_set.date_to
                    ) for inv in p_retenciones_automaticas)

                    retenciones_ir_manuales = sum(p_retenciones_manuales.filtered(
                        lambda r: r.group in RET_IR_VENTAS
                    ).mapped('amount'))
                    retenciones_iva_manuales = sum(p_retenciones_manuales.filtered(
                        lambda r: r.group in RET_IVA_VENTAS
                    ).mapped('amount'))
                    valorretiva = retenciones_iva + retenciones_iva_manuales
                    valorretrenta = retenciones_ir + retenciones_ir_manuales

                    numeroComprobantes = len(
                        p_ventas |
                        p_retenciones_automaticas |
                        p_retenciones_manuales.mapped('r_invoice_id')
                    )

                    # Debido a que no declaramos documentos electrónicos, podemos tener
                    # casos en los que todos los valores sean cero, por eso, hacemos
                    # una verificación antes de agregarlo a la declaración.

                    if basenograiva > 0 or baseimponible > 0 or baseimpgrav > 0 \
                            or montoiva > 0 or montoice > 0 or valorretiva > 0  \
                            or valorretrenta > 0:

                        ventas_dict = OrderedDict()
                        ventas_dict.update(vals)
                        ventas_dict.update(OrderedDict([
                            ('tipoComprobante', '18'),
                            ('tipoEmision', tipoem_ventas),
                            ('numeroComprobantes', numeroComprobantes),
                            ('baseNoGraIva', '{:.2f}'.format(abs(basenograiva))),
                            ('baseImponible', '{:.2f}'.format(abs(baseimponible))),
                            ('baseImpGrav', '{:.2f}'.format(abs(baseimpgrav))),
                            ('montoIva', '{:.2f}'.format(abs(montoiva))),
                            # TODO: Tipo y monto de compensaciones, por desarrollar.
                            # ('tipoCompe', ''),
                            # ('monto', '{:.2f}'.format(0)),
                            ('montoIce', '{:.2f}'.format(abs(montoice))),
                            ('valorRetIva', '{:.2f}'.format(abs(valorretiva))),
                            ('valorRetRenta', '{:.2f}'.format(abs(valorretrenta))),
                        ]))

                        # Forma de pago de las facturas del partner.
                        fp_inv = p_ventas_totales
                        if fp_inv:
                            formaPago = list(
                                set(fp_inv.mapped('payment_ids').mapped('formapago_id.code')))
                        if not formaPago:
                            formaPago.append(
                                p.formapago_id.code
                                or fiscal.formapago_id.code
                                or '20'
                            )
                        # Solo se declaran formasDePago en comprobantes de venta 18 y 41
                        if formaPago:
                            ventas_dict.update([
                                ('formasDePago', {'formaPago': formaPago})
                            ])

                        detalleVentas.append(ventas_dict)


                # REEMBOLSOS
                if p_reembolsos:
                    # Enceramos todas las variables para evitar agregar valores de procesos anteriores.
                    basenograiva = 0
                    baseimponible = 0
                    baseimpgrav = 0
                    montoiva = 0
                    montoice = 0
                    formaPago = []
                    retenciones_ir = 0
                    retenciones_ir_manuales = 0
                    retenciones_iva = 0
                    retenciones_iva_manuales = 0
                    if p_reembolsos:
                        t_reembolsos = p_reembolsos.mapped('sri_ats_line_ids')
                        reembolsos -= p_reembolsos
                        basenograiva = sum(t_reembolsos.mapped('basenograiva'))
                        baseimponible = sum(t_reembolsos.mapped('baseimponible'))
                        baseimpgrav = sum(t_reembolsos.mapped('baseimpgrav'))
                        montoiva = sum(t_reembolsos.mapped('montoiva'))
                        montoice = sum(t_reembolsos.mapped('montoice'))

                    numeroComprobantes = len(p_reembolsos)

                    reembolsos_dict = OrderedDict()
                    reembolsos_dict.update(vals)
                    reembolsos_dict.update(OrderedDict([
                        ('tipoComprobante', '41'),
                        ('tipoEmision', tipoem_reembolsos),
                        ('numeroComprobantes', numeroComprobantes),
                        ('baseNoGraIva', '{:.2f}'.format(abs(basenograiva))),
                        ('baseImponible', '{:.2f}'.format(abs(baseimponible))),
                        ('baseImpGrav', '{:.2f}'.format(abs(baseimpgrav))),
                        ('montoIva', '{:.2f}'.format(abs(montoiva))),
                        # TODO: Tipo y monto de compensaciones, por desarrollar.
                        # ('tipoCompe', ''),
                        # ('monto', '{:.2f}'.format(0)),
                        ('montoIce', '{:.2f}'.format(abs(montoice))),
                        ('valorRetIva', '{:.2f}'.format(abs(valorretiva))),
                        ('valorRetRenta', '{:.2f}'.format(abs(valorretrenta))),
                    ]))

                    # Forma de pago de los reembolsos del partner.
                    formaPago = list(
                        set(p_reembolsos.mapped('payment_ids').mapped('formapago_id.code'))
                    )
                    if not formaPago:
                        formaPago.append(
                            p.formapago_id.code
                            or fiscal.formapago_id.code
                            or '20'
                        )
                    reembolsos_dict.update([
                        ('formasDePago', {'formaPago': formaPago})
                    ])

                    detalleVentas.append(reembolsos_dict)

                # DEVOLUCIONES
                p_devoluciones = devoluciones.filtered(
                    lambda r: r.partner_id in contribuyentes)

                if not p_devoluciones:
                    continue

                t_devoluciones = p_devoluciones.mapped('sri_ats_line_ids')
                devoluciones -= p_devoluciones
                basenograiva = sum(t_devoluciones.mapped('basenograiva'))
                baseimponible = sum(t_devoluciones.mapped('baseimponible'))
                baseimpgrav = sum(t_devoluciones.mapped('baseimpgrav'))
                montoiva = sum(t_devoluciones.mapped('montoiva'))
                montoice = sum(t_devoluciones.mapped('montoice'))
                # Mantenemos el cálculo normal porque en devoluciones no
                # puede haber retenciones mananuales.
                valorretiva = sum(t_devoluciones.mapped('valorretiva'))
                valorretrenta = sum(t_devoluciones.mapped('valorretrenta'))

                devoluciones_dict = OrderedDict()
                devoluciones_dict.update(vals)

                devoluciones_dict.update(OrderedDict([
                    ('tipoComprobante', '04'),
                    ('tipoEmision', tipoem_devoluciones),
                    ('numeroComprobantes', len(p_devoluciones)),
                    ('baseNoGraIva', '{:.2f}'.format(abs(basenograiva))),
                    ('baseImponible', '{:.2f}'.format(abs(baseimponible))),
                    ('baseImpGrav', '{:.2f}'.format(abs(baseimpgrav))),
                    ('montoIva', '{:.2f}'.format(abs(montoiva))),
                    ('montoIce', '{:.2f}'.format(abs(montoice))),
                    ('valorRetIva', '{:.2f}'.format(abs(valorretiva))),
                    ('valorRetRenta', '{:.2f}'.format(abs(valorretrenta))),
                ]))

                detalleVentas.append(devoluciones_dict)

            ventas = OrderedDict([
                ('detalleVentas', detalleVentas),
            ])

            establecimientos = set(
                (ventas_totales).mapped('establecimiento'))
            establecimientos = establecimientos - set(['999', False])
            ventaEst = []
            for e in establecimientos:
                if tipoem_ventas == 'E':
                    e_ventas = 0.00
                else:
                    e_ventas = sum(ventas_totales.filtered(
                        lambda r: r.establecimiento == e
                            and r.tipoem == tipoem_ventas
                    ).mapped('subtotal'))

                ventaEst.append(OrderedDict([
                    ('codEstab', e),
                    ('ventasEstab', '{:.2f}'.format(e_ventas)),
                    ('ivaComp', '{:.2f}'.format(0)),
                ]))

            totalVentas = sum(float(v['ventasEstab']) for v in ventaEst)
            numEstabRuc = str(len(ventaEst)).zfill(3)
            ventasEstablecimiento = OrderedDict([
                ('ventaEst', ventaEst),
            ])
            
            # Para la información general del informante
            date = f.sri_tax_form_set_id.date_to
            company = self.env.user.company_id
            informante = company.partner_id
            fiscal = informante.property_account_position_id
            
            iva = OrderedDict([
                ('TipoIDInformante', fiscal.identificacion_id.code),
                ('IdInformante', informante.vat),
                ('razonSocial', inv.normalize_text(informante.name)),        
                ('Anio', str(date.year)),
                ('Mes', str(date.month))
                
            ])

            if numEstabRuc != '000':
                iva.update(OrderedDict([
                    ('numEstabRuc', numEstabRuc)
                ]))

            iva.update(OrderedDict([
                ('totalVentas', '{:.2f}'.format(totalVentas))
                ]))

            iva.update(OrderedDict([
                ('codigoOperativo', 'IVA')
            ]))

            # Diccionario de compras
            compras = form_set.in_invoice_ids + form_set.in_refund_ids

            detalleCompras = OrderedDict([('detalleCompras', [])])

            detalleAnulados = []
            for ca in form_set.comprobantesanulados_ids:
                autorizacion = ca.autorizacion or ca.autorizacion_id.autorizacion
                if not autorizacion:
                    continue
                detalleAnulados.append(OrderedDict([
                    ('tipoComprobante', ca.comprobante_id.code),
                    ('establecimiento', ca.autorizacion_id.establecimiento),
                    ('puntoEmision', ca.autorizacion_id.puntoemision),
                    ('secuencialInicio', ca.secuencialinicio),
                    ('secuencialFin', ca.secuencialfin),
                    ('autorizacion', autorizacion),
                ]))
            anulados = OrderedDict([
                ('detalleAnulados', detalleAnulados),
            ])

            for c in compras:
                detalleCompra = c.prepare_detallecompras_dict()
                for dc in detalleCompra:
                    detalleCompras['detalleCompras'].append(dc)

            res = {
                'iva': iva,
                'ventas': ventas,
                'ventasEstablecimiento': ventasEstablecimiento,
                'compras': detalleCompras,
                'anulados': anulados
            }
            return res

    @api.multi
    def get_ats_xml(self):
        decl = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>"""
        for f in self:
            vals = f.prepare_ats()
            data = OrderedDict([
                ('iva', vals['iva']),
            ])

            data['iva'].update([
                ('compras', vals['compras'])
            ])

            if vals['ventas']['detalleVentas']:
                data['iva'].update([
                    ('ventas', vals['ventas'])
                ])

            if vals['ventasEstablecimiento']['ventaEst']:
                data['iva'].update([
                    ('ventasEstablecimiento', vals['ventasEstablecimiento'])
                ])

            if vals['anulados']['detalleAnulados']:
                data['iva'].update([
                    ('anulados', vals['anulados'])
                ])

            xml_data = decl + \
                xmltodict.unparse(data, pretty=True, full_document=False)
            f.write({'xml_filename': 'ATS.xml',
                     'xml_file': base64.encodestring(bytes(xml_data,"utf-8"))})

    @api.multi
    def get_tax_form_lines(self):
        for f in self:
            # Limpiamos las líneas de impuestos previamente creadas.
            f.sri_tax_form_line_ids.unlink()

            form_set = f.sri_tax_form_set_id
            tax_form_lines = []

            # Calculamos los impuestos en ventas.
            in_inv = f.sri_tax_form_set_id.mapped('in_invoice_ids')

            inv_taxes = self.env['l10n_ec_sri.tax.line']
            for inv in in_inv:
                inv_taxes += inv._get_impuestos_por_periodo(
                    amount=False, groups=False,
                    date_from=form_set.date_from, date_to=form_set.date_to
                ).filtered(lambda r: r.formulario == f.formulario)
            # Agregamos todas las retenciones manuales en ventas
            # de periodos distintos que corresponden al formulario.
            inv_taxes += form_set.out_r_sri_tax_line_ids.filtered(
                lambda r: r.formulario == f.formulario
            )

            in_ref = f.sri_tax_form_set_id.mapped('in_refund_ids')
            ref_taxes = self.env['l10n_ec_sri.tax.line']
            for ref in in_ref:
                ref_taxes += ref._get_impuestos_por_periodo(
                    amount=False, groups=False,
                    date_from=form_set.date_from, date_to=form_set.date_to
                ).filtered(lambda r: r.formulario == f.formulario)
            form_fields = set((inv_taxes + ref_taxes).mapped('campo'))

            for t in form_fields:
                facturas = inv_taxes.filtered(lambda r: r.campo == t)
                devoluciones = ref_taxes.filtered(lambda r: r.campo == t)

                bruto = sum(facturas.mapped('base'))
                neto = bruto
                impuesto = sum(facturas.mapped('amount'))
                if f.formulario != "103":
                    neto = neto - sum(devoluciones.mapped('base'))
                    impuesto = impuesto - sum(devoluciones.mapped('amount'))

                tax_form_lines.append({
                    'sri_tax_form_id': f.id,
                    'campo': t,
                    'bruto': bruto,
                    'neto': neto,
                    'impuesto': impuesto,
                })

            # Calculamos los impuestos en compras.
            out_inv = f.sri_tax_form_set_id.mapped('out_invoice_ids')
            out_ref = f.sri_tax_form_set_id.mapped('out_refund_ids')

            inv_taxes = self.env['l10n_ec_sri.tax.line']
            for inv in out_inv:
                inv_taxes += inv._get_impuestos_por_periodo(
                    amount=False, groups=False,
                    date_from=form_set.date_from, date_to=form_set.date_to
                ).filtered(lambda r: r.formulario == f.formulario)

            ref_taxes = self.env['l10n_ec_sri.tax.line']
            for ref in out_ref:
                ref_taxes += ref._get_impuestos_por_periodo(
                    amount=False, groups=False,
                    date_from=form_set.date_from, date_to=form_set.date_to
                ).filtered(lambda r: r.formulario == f.formulario)

            form_fields = set((inv_taxes + ref_taxes).mapped('campo'))

            for t in form_fields:
                facturas = inv_taxes.filtered(lambda r: r.campo == t)
                devoluciones = ref_taxes.filtered(lambda r: r.campo == t)

                bruto = sum(facturas.mapped('base'))
                neto = bruto
                impuesto = sum(facturas.mapped('amount'))
                if f.formulario != "103":
                    neto = neto - sum(devoluciones.mapped('base'))
                    impuesto = impuesto - sum(devoluciones.mapped('amount'))

                tax_form_lines.append({
                    'sri_tax_form_id': f.id,
                    'campo': t,
                    'bruto': bruto,
                    'neto': neto,
                    'impuesto': impuesto,
                })

            for line in tax_form_lines:
                self.env['l10n_ec_sri.tax.form.line'].create(line)


class SriTaxFormLine(models.Model):
    _name = 'l10n_ec_sri.tax.form.line'
    _order = 'campo'

    @api.multi
    def _compute_tax_lines(self):
        for r in self:
            s = r.sri_tax_form_id.sri_tax_form_set_id
            invoices = s.in_invoice_ids + s.in_refund_ids + \
                s.out_invoice_ids + s.out_refund_ids
            taxes = invoices.mapped('sri_tax_line_ids')
            r.sri_tax_line_ids = taxes.filtered(lambda x: x.campo == r.campo)

    sri_tax_line_ids = fields.One2many(
        'l10n_ec_sri.tax.line', compute=_compute_tax_lines,
        string='Tax lines', )

    sri_tax_form_id = fields.Many2one(
        'l10n_ec_sri.tax.form', ondelete='cascade',
        string="Tax form", )
    description = fields.Char('Nombre')
    campo = fields.Char('Campo')
    bruto = fields.Float('Valor bruto', digits=(9, 2), )
    neto = fields.Float('Valor neto', digits=(9, 2), )
    impuesto = fields.Float('Impuesto', digits=(9, 2), )

