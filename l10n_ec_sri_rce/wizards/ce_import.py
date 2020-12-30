# -*- coding: utf-8 -*-

import base64
import zipfile
import xmltodict
import logging
import xml

from collections import OrderedDict
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime
from io import StringIO as s

_logger = logging.getLogger(__name__)

try:
    from zeep import Client
except ImportError:
    _logger.warning("The module zeep can't be loaded, try: pip install zeep")


class ComprobanteElectronicoImportWizardLine(models.TransientModel):
    _name = "l10n_ec_sri.ce.import.wizard.line"
    _description = "Register multiple SRI information on invoices."

    import_file = fields.Binary('File:',)
    wizard_id = fields.Many2one(
        'l10n_ec_sri.ce.import.wizard', string="Wizard",)

class ComprobanteElectronicoImportWizard(models.TransientModel):

    _name = "l10n_ec_sri.ce.import.wizard"
    _description = "Register multiple SRI information on invoices."

    import_file = fields.Binary('File:',)
    wizard_line_ids = fields.One2many(
        'l10n_ec_sri.ce.import.wizard.line', inverse_name='wizard_id',
        string='Wizard lines',)
    data_ids = fields.One2many('l10n_ec_sri.ce.pre.validate','prevalidate_id')
    conciliate_ids = fields.One2many('l10n_ec_sri.doc.import.estado','conciliate_id')
    no_conciliate_ids = fields.One2many('l10n_ec_sri.doc.import.estado','no_conciliate_id')
    state = fields.Selection([
            ('draft','Borrador'),
            ('open','Abierto'),
        ], string='Estado', index=True, readonly=True, default='draft',track_visibility='onchange', copy=False,)

    @api.multi
    def get_de_dict(
            self, estado, xml, infotributaria):
        """
        :param estado:
        :param xml:
        :param infotributaria:
        :return:
        """
        comprobante = self.env['l10n_ec_sri.comprobante'].search(
            [('code', '=', infotributaria['codDoc'])], limit=1)

        context, active_model, active_id = self.params_context()

        if active_id and active_model:
            vals = {
                'xml_file': xml,
                'xml_filename': infotributaria['claveAcceso'] + '.xml',
                'estado': estado,
                'ambiente': infotributaria['ambiente'],
                'tipoemision': infotributaria['tipoEmision'],
                'claveacceso': infotributaria['claveAcceso'],
                'reference': ('{0},{1}'.format(active_model, active_id[0])),
                'comprobante_id': comprobante.id,
            }
        else:
            vals = {
                'xml_file': xml,
                'xml_filename': infotributaria['claveAcceso'] + '.xml',
                'estado': estado,
                'ambiente': infotributaria['ambiente'],
                'tipoemision': infotributaria['tipoEmision'],
                'claveacceso': infotributaria['claveAcceso'],
                'comprobante_id': comprobante.id,
            }
        return vals

    @api.multi
    def normalize_date_to_odoo(self, date):
        if not date:
            return
        res = datetime.strptime(date, '%d/%m/%Y').strftime('%Y-%m-%d')
        return res

    @api.multi
    def get_data_from_xml(self, xml):
        """
        :param xml:
        :return:
        """
        try:
            autorizacion_dict = xmltodict.parse(xml)['autorizacion']
            estado = autorizacion_dict['estado']
            comprobante = autorizacion_dict['comprobante'].encode('utf-8')
            comprobante = xmltodict.parse(comprobante)
        except Exception as e:
            return e

        if 'factura' in comprobante.keys():
            infoTributaria = comprobante['factura']['infoTributaria']
            infoFactura = comprobante['factura']['infoFactura']
            establecimiento = infoTributaria['estab']
            puntoEmision = infoTributaria['ptoEmi']
            secuencial = infoTributaria['secuencial']
            numFactura = establecimiento + "-" + puntoEmision + "-" + secuencial
            key = 'factura'
            fecha = infoFactura['fechaEmision']
            vat = infoTributaria['ruc']
            partner_id = self.env['res.partner'].search([('vat', '=', vat)], limit=1).id
            numDocModificado = False
            motivo = False

        elif 'comprobanteRetencion' in comprobante.keys():
            infoTributaria = comprobante['comprobanteRetencion']['infoTributaria']
            key = 'comprobanteRetencion'
            fecha = comprobante['comprobanteRetencion']['infoCompRetencion']['fechaEmision']
            establecimiento = infoTributaria['estab']
            puntoEmision = infoTributaria['ptoEmi']
            secuencial = infoTributaria['secuencial']
            numFactura = establecimiento + "-" + puntoEmision + "-" + secuencial
            vat = infoTributaria['ruc']
            partner_id = self.env['res.partner'].search([('vat', '=', vat)], limit=1).id
            impuesto_list = []
            docs = []
            impuestos = comprobante['comprobanteRetencion']['impuestos']['impuesto']
            motivo = False
            numDocModificado = ""

            if isinstance(impuestos, dict):
                impuesto_list.append(impuestos)
                impuestos = impuesto_list

            try:
                for impuesto in impuestos:
                    if impuesto['numDocSustento'] not in docs:
                            docs.append(impuesto['numDocSustento'])
                docs = list(set(docs))
                for d in docs:
                    numDocModificado += d[:3] + "-" + d[3:6] + "-" + d[6:] + "\n"

            except:
                numDocModificado = "No contiene"


        elif 'notaCredito' in comprobante.keys():
            infoTributaria = comprobante['notaCredito']['infoTributaria']
            infoNotaCredito = comprobante['notaCredito']['infoNotaCredito']
            key = 'notaCredito'
            establecimiento = infoTributaria['estab']
            puntoEmision = infoTributaria['ptoEmi']
            secuencial = infoTributaria['secuencial']
            numFactura = establecimiento + "-" + puntoEmision + "-" + secuencial
            vat = infoTributaria['ruc']
            partner_id = self.env['res.partner'].search([('vat', '=', vat)], limit=1).id
            fecha = infoNotaCredito['fechaEmision']
            numDocModificado = infoNotaCredito['numDocModificado']
            motivo = infoNotaCredito['motivo']

        comprobante_name = self.env['l10n_ec_sri.comprobante'].search([('code','=',infoTributaria['codDoc'])]).name


        razon_social = infoTributaria['razonSocial']
        clave_acceso = infoTributaria['claveAcceso']
        xml = base64.b64encode(xml)

        vals = {
        'ruc': vat,
        'razon_social_emisor': razon_social,
        'comprobante': comprobante_name,
        'partner_id': partner_id,
        'numero_factura': numFactura,
        'clave_acceso': clave_acceso,
        'fecha': datetime.strptime(fecha,'%d/%m/%Y').strftime('%Y-%m-%d'),
        'doc_modificado': numDocModificado,
        'xml': xml,
        'prevalidate_id': self.id,
        'motivo': motivo
        }

        return vals

    @api.multi
    def _process_file(self, file):
        error = []
        fileio = s(base64.b64decode(file))
        xml = base64.b64decode(file)
        if zipfile.is_zipfile(fileio):
            with zipfile.ZipFile(fileio, 'r') as zip_file:
                members = zipfile.ZipFile.namelist(zip_file)
                xml_members = [m for m in members if ".xml" in m]
                if not xml_members:
                    raise UserError(_("Error: Ingrese un archivo xml o zip valido."))
                for m in xml_members:
                    xml = zip_file.open(m).read()
                    vals =  self.get_data_from_xml(xml)
                    line = self.env['l10n_ec_sri.ce.pre.validate'].create(vals)

        elif '<?xml' in xml[:10]:
            try:
                vals = self.get_data_from_xml(xml)
                doc = self._get_documento_existente(vals)
                if doc and doc.move_id:
                    dict = self._get_dict_doc_estado(vals)
                    dict['invoice_id'] = doc.id
                    dict['conciliate_id'] = self.id,
                    line = self.env['l10n_ec_sri.doc.import.estado'].create(dict)
                elif doc and not doc.move_id:
                    dict = self._get_dict_doc_estado(vals)
                    dict['invoice_id'] = doc.id
                    dict['no_conciliate_id'] = self.id,
                    line = self.env['l10n_ec_sri.doc.import.estado'].create(dict)
                else:
                    line = self.env['l10n_ec_sri.ce.pre.validate'].create(vals)
            except:
                    return vals

        elif 'COMPROBANTE' in xml[:11]:
            doces = self.get_data_from_txt(xml)
            for de in doces:
                try:
                    vals = self._get_prevalidate_dict(vals=de)
                    doc = self._get_documento_existente(vals)
                    if doc and doc.move_id:
                        dict = self._get_dict_doc_estado(vals)
                        dict['invoice_id'] = doc.id
                        dict['conciliate_id'] = self.id,
                        line = self.env['l10n_ec_sri.doc.import.estado'].create(dict)
                    elif doc and not doc.move_id:
                        dict = self._get_dict_doc_estado(vals)
                        dict['invoice_id'] = doc.id
                        dict['no_conciliate_id'] = self.id,
                        line = self.env['l10n_ec_sri.doc.import.estado'].create(dict)
                    else:
                        line = self.env['l10n_ec_sri.ce.pre.validate'].create(vals)
                except:
                    error.append(de['error'])
        else:
            raise UserError(_("Error: Ingrese un archivo xml, txt o zip valido."))

        if error:
            return error

    @api.multi
    def _get_documento_existente(self, vals):
        inv_obj = self.env['account.invoice']

        if vals['comprobante'] == u'Factura' or vals['comprobante'] == u'Nota de Cr\xe9dito' or vals['comprobante'].decode('unicode_escape') == u'Notas de Cr\xe9dito' or vals['comprobante'] == u'Nota de cr\xe9dito':
            inv = inv_obj.search([('secuencial', '=', vals['numero_factura'][8:]),
                              ('establecimiento', '=',  vals['numero_factura'][:3]),
                              ('puntoemision', '=',  vals['numero_factura'][4:7])])

        elif vals['comprobante'].decode('unicode_escape') == u'Comprobante de Retención' or vals['comprobante'] == u'Comprobante de Retenci\xf3n':
            inv = inv_obj.search([('secretencion1', '=', vals['numero_factura'][8:]),
                              ('estabretencion1', '=',  vals['numero_factura'][:3]),
                              ('ptoemiretencion1', '=',  vals['numero_factura'][4:7])])

        return inv
    @api.multi
    def _get_dict_doc_estado(self, vals):
        partner = self.env['res.partner'].search([('vat','=',vals['ruc'])], limit=1)
        try:
            dict = {
            'clave_acceso': vals['clave_acceso'],
            'numero_factura': vals['numero_factura'],
            'partner_id': partner.id,
            'ruc': vals['ruc'],
            'invoice_id': False,
            'conciliate_id': False,
            'no_conciliate_id': False,
            'motivo': vals['motivo'],
            }
        except:
            dict = {
            'clave_acceso': vals['clave_acceso'],
            'numero_factura': vals['numero_factura'],
            'partner_id': partner.id,
            'ruc': vals['ruc'],
            'invoice_id': False,
            'conciliate_id': False,
            'no_conciliate_id': False,
            }
        return dict


    @api.multi
    def get_data_from_txt(self,txt):
        list = txt.replace('\n', '\t').replace('\r', '')
        list = list.split('\t')
        str_keys = list[0:11]
        keys = filter(None, str_keys)
        str_values = list[11:]
        values = filter(None, str_values)
        chunks = [values[x:x+11] for x in xrange(0, len(values), 11)]
        doces = []

        for chunk in chunks:
            if chunk[0] == 'Factura':
                list_doce = {
                keys[0]: chunk[0],
                keys[8]: chunk[8],
                keys[2]: chunk[2],
                keys[3]: chunk[3],
                keys[4]: chunk[4],
                keys[1]: chunk[1],
                }
            elif chunk[0].decode('unicode_escape') == u"Comprobante de Retención":
                list_doce = {
                keys[0]: chunk[0],
                keys[8]: chunk[9],
                keys[2]: chunk[2],
                keys[3]: chunk[3],
                keys[4]: chunk[4],
                keys[1]: chunk[1],
                    }
            elif chunk[0].decode('unicode_escape')  == u"Notas de Crédito": #TODO
                list_doce = {
                keys[0]: chunk[0],
                keys[8]: chunk[9],
                keys[2]: chunk[2],
                keys[3]: chunk[3],
                keys[4]: chunk[4],
                keys[1]: chunk[1],
                keys[7]: chunk[7],
                    }
            else:
                error = 'Error en la estructura del archivo txt, NO SE IMPORTA, verifiquelo y vuelva a intentar\nDETALLE ERROR:\t{0}'.format(chunk)
                list_doce = {'error': error}
            doces.append(list_doce)
        return doces

    @api.multi
    def _get_prevalidate_dict(self,vals={}):
        partner = self.env['res.partner'].search([('vat','=',vals['RUC_EMISOR'])], limit=1)
        try:
            dict = {
            'ruc': vals['RUC_EMISOR'],
            'razon_social_emisor': vals['RAZON_SOCIAL_EMISOR'],
            'comprobante': vals['COMPROBANTE'],
            'partner_id': partner.id,
            'numero_factura': vals['SERIE_COMPROBANTE'],
            'clave_acceso': vals['CLAVE_ACCESO'],
            'doc_modificado': vals['IDENTIFICACION_RECEPTOR'],
            'fecha': datetime.strptime(vals['FECHA_EMISION'],'%d/%m/%Y').strftime('%Y-%m-%d'),
            'prevalidate_id': self.id }
        except:
            dict = {
            'ruc': vals['RUC_EMISOR'],
            'razon_social_emisor': vals['RAZON_SOCIAL_EMISOR'],
            'comprobante': vals['COMPROBANTE'],
            'partner_id': partner.id,
            'numero_factura': vals['SERIE_COMPROBANTE'],
            'clave_acceso': vals['CLAVE_ACCESO'],
            'fecha': datetime.strptime(vals['FECHA_EMISION'],'%d/%m/%Y').strftime('%Y-%m-%d'),
            'prevalidate_id': self.id }

        return dict


    @api.multi
    def receive_de(self, comprobante, clave_acceso):
        ambiente_id = self.env.user.company_id.ambiente_id

        client = Client(ambiente_id.autorizacioncomprobantes)
        with client.options(raw_response=False):
            response = client.service.autorizacionComprobante(clave_acceso)

        try:
            autorizaciones = response['autorizaciones']['autorizacion'][0]

            if autorizaciones['estado'] == 'AUTORIZADO':
                autorizacion = OrderedDict([
                    ('autorizacion', OrderedDict([
                        ('estado', autorizaciones['estado']),
                        ('numeroAutorizacion', autorizaciones['numeroAutorizacion']),
                        ('fechaAutorizacion',
                            {
                                '@class': 'fechaAutorizacion',
                                '#text': str(autorizaciones['fechaAutorizacion'])
                            }
                        ),
                        ('ambiente', autorizaciones['ambiente']),
                        ('comprobante', u'<![CDATA[{}]]>'.format(
                            autorizaciones['comprobante'])),
                    ]))
                ])

            elif autorizaciones['estado'] == 'RECHAZADA':
                respuesta = autorizaciones['estado']
                msg_sri = "\nComprobante:\t{0}\n\tSRI clave de acceso:\t{1}\n\tRespuesta del SRI estado del comprobante:\t{2}".format(comprobante, clave_acceso, respuesta)
                return msg_sri

            comp_e = xml.sax.saxutils.unescape(
                    xmltodict.unparse(autorizacion))
        except:
            msg_sri = "\n{0}:\tSRI clave de acceso: {1}, no se encuentra registrada en el SRI".format(comprobante, clave_acceso)
            return msg_sri

        return comp_e


    @api.multi
    def register_de_data(self, xml, active_model, active_records, resumen_dict, line):
        try:
            de, key, info, autorizacion, xml_data, ces, secuencial = self.get_de_from_xml(xml, line)
            nde = de['reference']

            if key == 'factura' and active_model == 'account.invoice':
                creando = False
                old_des = active_records.mapped('factura_electronica_id')
                xml_data['factura_electronica_id'] = de.id
                try:
                    if ces and active_records:
                        active_records.write(xml_data)
                        agregadas = OrderedDict([
                            ("comprobante", key),
                            ("secuencial", secuencial),
                            ])
                        resumen_dict['agregadas'].append(agregadas)
                        active_records._onchange_invoice_line_ids()
                        if line.validate == True:
                            active_records.signal_workflow('invoice_open')

                    elif active_records and not active_records.invoice_line_ids:
                        active_records.write(xml_data)
                        agregadas = OrderedDict([
                            ("comprobante", key),
                            ("secuencial", secuencial),
                            ])
                        resumen_dict['agregadas'].append(agregadas)
                        active_records._onchange_invoice_line_ids()
                        if line.validate == True:
                            active_records.signal_workflow('invoice_open')

                    elif active_records and active_records.invoice_line_ids:
                        creando = True
                        ni = active_records.create(xml_data)
                        ni.factura_electronica_id.reference = '{0},{1}'.format(active_model, ni.id)
                        ni._onchange_invoice_line_ids()
                        agregadas = OrderedDict([
                            ("comprobante", key),
                            ("secuencial", secuencial),
                            ])
                        resumen_dict['agregadas'].append(agregadas)
                        if line.validate == True:
                            ni.signal_workflow('invoice_open')
                    else:
                        creando = True
                        ni = active_records.create(xml_data)
                        ni.factura_electronica_id.reference = '{0},{1}'.format(active_model, ni.id)
                        ni._onchange_invoice_line_ids()
                        agregadas = OrderedDict([
                            ("comprobante", key),
                            ("secuencial", secuencial),
                            ])
                        resumen_dict['agregadas'].append(agregadas)
                        if line.validate == True:
                            ni.signal_workflow('invoice_open')

                except Exception as e:
                    error = str(e)
                    mensaje = "No se pudo crear la factura con el secuencial {0} por el siguiente error: {1}".format(secuencial,error)
                    error_comprobante = OrderedDict([
                        ("mensaje", mensaje)
                        ])
                    resumen_dict['error_en_comprobante'].append(error_comprobante)

            if key == 'comprobanteRetencion' and active_model == 'account.invoice':
                old_des = active_records.mapped('retencion_electronica_id')
                xml_data['retencion_electronica_id'] = de.id
                creando = False
                if ces:
                    creando = True
                    for ce in ces['exist']:
                        try:
                            if not old_des:
                                old_des = ce.mapped('retencion_electronica_id')
                            ce.write(xml_data)
                            creando = True
                            agregadas = OrderedDict([
                                ("comprobante", key),
                                ("secuencial", secuencial),
                                ])
                            resumen_dict['agregadas'].append(agregadas)
                        except Exception as e:
                            error_comprobante = OrderedDict([
                                    ("mensaje", str(e) + "secuencial: {0}".format(secuencial))
                                    ])
                            resumen_dict['error_en_comprobante'].append(error_comprobante)

                if ces['noexist']:
                    no_encontradas = OrderedDict([
                    ("comprobante", key),
                    ("secuencial", ces['noexist'])
                    ])

                    resumen_dict['no_encontradas'].append(no_encontradas)

            if key == 'notaCredito' and active_model == 'account.invoice':
                creando = False
                old_des = active_records.mapped('nota_credito_electronica_id')
                xml_data['nota_credito_electronica_id'] = de.id
                try:
                    if ces:
                        ces.invoice_line_ids.unlink()
                        ces.write(xml_data)
                        agregadas = OrderedDict([
                            ("comprobante", key),
                            ("secuencial", secuencial),
                            ])
                        resumen_dict['agregadas'].append(agregadas)
                        ces._onchange_invoice_line_ids()
                        if line.validate == True:
                            ces.signal_workflow('invoice_open')

                    elif active_records and not active_records.invoice_line_ids:
                        active_records.invoice_line_ids.unlink()
                        active_records.write(xml_data)
                        agregadas = OrderedDict([
                            ("comprobante", key),
                            ("secuencial", secuencial),
                            ])
                        resumen_dict['agregadas'].append(agregadas)
                        active_records._onchange_invoice_line_ids()
                        if line.validate == True:
                            active_records.signal_workflow('invoice_open')

                    else:
                        creando = True
                        active_records.invoice_line_ids.unlink()
                        ni = active_records.write(xml_data)
                        ni.nota_credito_electronica_id.reference = '{0},{1}'.format(active_model, ni.id)
                        ni._onchange_invoice_line_ids()
                        agregadas = OrderedDict([
                            ("comprobante", key),
                            ("secuencial", secuencial),
                            ])
                        resumen_dict['agregadas'].append(agregadas)
                        if line.validate == True:
                            ni.signal_workflow('invoice_open')

                except Exception as e:
                    error = str(e)
                    mensaje = "No se pudo crear la factura con el secuencial {0} por el siguiente error: {1}".format(secuencial,error)
                    error_comprobante = OrderedDict([
                        ("mensaje", mensaje)
                        ])
                    resumen_dict['error_en_comprobante'].append(error_comprobante)

            if creando == False:
                old_des.unlink()  # Borramos los documentos antiguos pues est├í restringido para borrar.

        except:
            error = self.get_de_from_xml(xml, line)
            error = str(error).decode('unicode_escape')
            return error

    @api.multi
    def button_validate_mass(self):
        context, active_model, active_ids = self.params_context()

        if not active_model or not active_ids:
            active_model = 'account.invoice'
            active_ids = []
        elif len(active_ids) > 1:
            raise UserError(_("Debe seleccionar solo un registro."))

        active_records = self.env[active_model].browse(active_ids)

        resumen_dict = OrderedDict([
            ('agregadas', []),
            ('no_encontradas', []),
            ('error_en_comprobante',[]),
            ('total', 0),
        ])

        for line in self.data_ids:
            if line.xml:
                xml = base64.b64decode(line.xml)
                self.register_de_data(xml, active_model, active_records, resumen_dict, line)
            else:
                xml = self.receive_de(line.comprobante, line.clave_acceso.replace(' ', ''))
                if type(xml) == str:
                    resumen_dict['error_en_comprobante'].append(xml)
                else:
                    self.register_de_data(xml, active_model, active_records, resumen_dict, line)

        resumen_dict['total'] = len(resumen_dict['agregadas']) + len(resumen_dict['no_encontradas']) + len(resumen_dict['error_en_comprobante'])

        msg_obj = self.env['custom.pop.message']
        advices = ""

        for msg, num in resumen_dict.items():
            try:
                advices += msg + ": " + str(len(num)) + "\n"
            except:
                advices += msg + ": " + str(num) + "\n"

        txtfile = self.generate_file(resumen_dict)

        return msg_obj.messagebox(advices, txtfile)

    @api.multi
    def validate_one(self,context, active_model, active_ids, prevalidate_line):
        if not active_model or not active_ids:
            active_model = 'account.invoice'
            active_ids = []
        elif len(active_ids) > 1:
            raise UserError(_("Debe seleccionar solo un registro."))

        active_records = self.env[active_model].browse(active_ids)

        resumen_dict = OrderedDict([
            ('agregadas', []),
            ('no_encontradas', []),
            ('error_en_comprobante',[]),
            ('total', 0),
        ])

        for line in prevalidate_line:
            if line.xml:
                xml = base64.b64decode(line.xml)
                res = self.register_de_data(xml, active_model, active_records, resumen_dict, line)
                try:
                    res = resumen_dict['no_encontradas']['secuencial']
                    msg_obj = self.env['custom.pop.message']
                    return msg_obj.messagebox(res, None)
                except:
                    if res:
                        msg_obj = self.env['custom.pop.message']
                        return msg_obj.messagebox(res, None)
            else:
                xml = self.receive_de(line.comprobante, line.clave_acceso.replace(' ', ''))
                if type(xml) == str:
                    msg_obj = self.env['custom.pop.message']
                    return msg_obj.messagebox(xml, None)
                error = self.register_de_data(xml, active_model, active_records, resumen_dict, line)
                if error:
                    msg_obj = self.env['custom.pop.message']
                    return msg_obj.messagebox(error, None)

            line.nivel = 'validate'

    @api.multi
    def get_de_from_xml(self, xml, line):
        """
        :param xml:
        :return:
        """
        try:
            autorizacion_dict = xmltodict.parse(xml)['autorizacion']
            estado = autorizacion_dict['estado']
            comprobante = autorizacion_dict['comprobante'].encode('utf-8')
            comprobante = xmltodict.parse(comprobante)
        except Exception as e:
            return e

        if 'factura' in comprobante.keys():
            inv_obj = self.env['account.invoice']
            infoTributaria = comprobante['factura']['infoTributaria']
            infoFactura = comprobante['factura']['infoFactura']
            secuencial = infoTributaria['secuencial']
            key = 'factura'

            inv = inv_obj.search([('secuencial', '=', infoTributaria['secuencial']),
                                      ('autorizacion', '=', autorizacion_dict['numeroAutorizacion']),
                                       ('establecimiento', '=', infoTributaria['estab']),
                                       ('puntoemision', '=', infoTributaria['ptoEmi'])])

            fecha = infoFactura['fechaEmision']
            partner = self.env['res.partner'].search([('vat', '=', line.ruc)], limit=1)

            if not partner:
                return "\nCree el proveedor {0} para la factura".format(line.razon_social_emisor)

            detalle = comprobante['factura']['detalles']['detalle']
            detalle_list = []

            if isinstance(detalle, dict):
                detalle_list.append(detalle)
                detalle = detalle_list

            supplier = self.env['product.supplierinfo']
            supplier = supplier.search([('name', '=', partner.id)])
            precio_total = 0

            lines = []
            if supplier:
                for d in detalle:

                    d_supplier = supplier.filtered(
                        lambda x: x.product_code == d['codigoPrincipal'] or
                        x.product_name == d['descripcion'] or
                        x.product_name in d['descripcion'] or
                        d['descripcion'] in x.product_name)

                    product = d_supplier.product_tmpl_id

                    if partner.property_account_position_id and product.supplier_taxes_id:
                        tax_ids = partner.property_account_position_id.map_tax(product.supplier_taxes_id).ids
                    else:
                        tax_ids = product.supplier_taxes_id.ids

                    account = product.property_account_expense_id or product.categ_id.property_account_expense_categ_id

                    if not tax_ids and account:
                        return "No se encuentra ingresado una cuenta y un impuesto\n"

                    lines.append((0, 0, {
                                    'product_id': d_supplier.product_tmpl_id.id,
                                    'quantity': d['cantidad'],
                                    'price_unit': d['precioUnitario'],
                                    'name':  d['descripcion'],
                                    'account_id': account.id,
                                    'invoice_line_tax_ids': [(6, 0, tax_ids)],
                                    }))

            elif line.product_id and line.agrupate_product_lines:
                for d in detalle:
                    precio_producto = float(d['cantidad']) * float(d['precioUnitario'])
                    precio_total += precio_producto

                lines.append((0, 0, {
                                    'product_id': line.product_id.id,
                                    'quantity': 1,
                                    'price_unit': precio_total,
                                    'name':  line.product_id.name,
                                    'account_id': int(line.product_id.property_account_expense_id.id),
                                    'invoice_line_tax_ids': [(6, 0, line.product_id.supplier_taxes_id.ids)],
                                    }))

            elif line.product_id:
                for d in detalle:
                    lines.append((0, 0, {
                                    'product_id': line.product_id.id,
                                    'quantity': d['cantidad'],
                                    'price_unit': d['precioUnitario'],
                                    'name':  d['descripcion'],
                                    'account_id': int(line.product_id.property_account_expense_id.id),
                                    'invoice_line_tax_ids': [(6, 0, line.product_id.supplier_taxes_id.ids)],
                                    }))

            elif not line.product_id:
                products = self.env['product.product']
                for d in detalle:
                    product = products.filtered(
                                    lambda x : x.default_code == d['codigoPrincipal'] or
                                    x.name == d['description'] or
                                    d['descripcion'] in x.name)

                    product = products.search(
                                    ['|', ('default_code', '=', d['codigoPrincipal']),
                                         ('name', '=', d['descripcion'])])

                    if not product:
                        product = product.create({
                                            'name': d['descripcion'],
                                            'default_code': d['codigoPrincipal'],
                                            'standard_price': d['precioUnitario'],
                                                      })


                    if partner.property_account_position_id and product.supplier_taxes_id:
                        tax_ids = partner.property_account_position_id.map_tax(product.supplier_taxes_id).ids
                    else:
                        tax_ids = product.supplier_taxes_id.ids

                    account = product.property_account_expense_id or product.categ_id.property_account_expense_categ_id

                    if not tax_ids and not account:
                        e = "No se encuentra ingresado una CUENTA DE GASTOS y un IMPUESTO DE PROVEEDOR en el producto: {0}".format(product.name)
                        return e
                    elif not tax_ids and account:
                        e = "No se encuentra ingresado un IMPUESTO DE PROVEEDOR en el producto: {0}".format(product.name)
                        return e
                    elif tax_ids and not account:
                        e = "No se encuentra ingresado unz CUENTA DE GASTOS en el producto: {0}".format(product.name)
                        return e

                    lines.append((0, 0, {
                                    'product_id': product.id,
                                    'quantity': d['cantidad'],
                                    'price_unit': d['precioUnitario'],
                                    'name':  d['descripcion'],
                                    'account_id': account.id,
                                    'invoice_line_tax_ids': [(6, 0, tax_ids)],
                                    }))

            inv_dict = {
                    'comprobante_id': self.env['l10n_ec_sri.comprobante'].search(
                     [('code', '=', infoTributaria['codDoc'])], limit=1).id,
                    'secuencial': infoTributaria['secuencial'],
                    'partner_id': partner.id,
                    'date_invoice': self.normalize_date_to_odoo(fecha),
                    'invoice_line_ids': lines,
                    'establecimiento': infoTributaria['estab'],
                    'puntoemision': infoTributaria['ptoEmi'],
                    'autorizacion': autorizacion_dict['numeroAutorizacion'],
                    'type' : 'in_invoice'
                    }

        elif 'comprobanteRetencion' in comprobante.keys():
            infoTributaria = comprobante['comprobanteRetencion']['infoTributaria']
            key = 'comprobanteRetencion'
            fecha = comprobante['comprobanteRetencion']['infoCompRetencion']['fechaEmision']

            inv_obj = self.env['account.invoice']
            inv = {}
            inv_e = []
            no_sec = []
            docs = []
            impuesto_list = []
            numDocModificado = ''

            impuestos = comprobante['comprobanteRetencion']['impuestos']['impuesto']

            if isinstance(impuestos, dict):
                impuesto_list.append(impuestos)
                impuestos = impuesto_list

            try:
                for impuesto in impuestos:
                    if impuesto['numDocSustento'] not in docs:
                            docs.append(impuesto['numDocSustento'])

                docs = list(set(docs))

                for d in docs:
                    establecimiento = d[:3]
                    ptoemision = d[3:6]
                    secuencial = d[6:]
                    numDocModificado += establecimiento + "-" + ptoemision + "-" + secuencial
                    invoice = inv_obj.search([('establecimiento', '=', establecimiento),
                                             ('puntoemision', '=', ptoemision),
                                             ('secuencial', '=', secuencial),
                                             ('type', '=', 'out_invoice')])

                    if not invoice:
                        no_sec.append(d[6:])
                    else:
                        inv_e.append(invoice)

                fecha = comprobante['comprobanteRetencion']['infoCompRetencion']['fechaEmision']

                inv_dict = {
                        'r_comprobante_id': self.env['l10n_ec_sri.comprobante'].search(
                        [('code', '=', infoTributaria['codDoc'])], limit=1).id,
                        'fechaemiret1': self.normalize_date_to_odoo(fecha),
                        'estabretencion1': infoTributaria['estab'],
                        'ptoemiretencion1': infoTributaria['ptoEmi'],
                        'autretencion1': autorizacion_dict['numeroAutorizacion'],
                        'secretencion1': infoTributaria['secuencial'],
                        }

                inv = {
                    'exist': inv_e,
                    'noexist': no_sec
                    }

                if not invoice:
                    return "No se encuentra la factura {0} asociada al comprobante\n".format(numDocModificado)
            except:
                establecimiento = infoTributaria['estab']
                ptoemision = infoTributaria['ptoEmi']
                secuencial = infoTributaria['secuencial']
                numeroRetencion = establecimiento + "-" + ptoemision + "-" + secuencial
                return "Comprobante No. {0} no contiene documento sustento".format(numeroRetencion)

        elif 'notaCredito' in comprobante.keys():
            inv_obj = self.env['account.invoice']
            lines = []
            infoTributaria = comprobante['notaCredito']['infoTributaria']
            infoNotaCredito = comprobante['notaCredito']['infoNotaCredito']
            key = 'notaCredito'
            secuencial = infoTributaria['secuencial']

            vat = infoTributaria['ruc']
            partner = self.env['res.partner'].search([('vat', '=', vat)], limit=1)

            ntc = inv_obj.search([('secuencial', '=', infoTributaria['secuencial']),
                                      ('autorizacion', '=', autorizacion_dict['numeroAutorizacion']),
                                       ('establecimiento', '=', infoTributaria['estab']),
                                       ('puntoemision', '=', infoTributaria['ptoEmi']),
                                       ('type', '=', 'out_refund')])

            if ntc:
                return "Ya está registrada la Nota de Crédito con el secuencial: {0}".format(secuencial)

            numDocModificado = infoNotaCredito['numDocModificado']
            establecimientoMod = numDocModificado[:3]
            ptoemisionMod = numDocModificado[4:7]
            secuencialMod = numDocModificado[8:]

            inv_refund = inv_obj.search([('establecimiento', '=', establecimientoMod),
                                             ('puntoemision', '=', ptoemisionMod),
                                             ('secuencial', '=', secuencialMod),
                                             ('type', '=', 'in_invoice')])

            if not inv_refund:
                return "Nota Crédito: {0} no se encuentra factura: {1}".format(secuencial, secuencialMod)

            date_invoice = datetime.strptime(infoNotaCredito['fechaEmision'],'%d/%m/%Y').strftime('%Y-%m-%d')
            date = False
            description = infoNotaCredito['motivo']
            inv = inv_refund.refund(date_invoice, date, description, inv_refund.journal_id.id)
            inv.compute_taxes()

            detalle = comprobante['notaCredito']['detalles']['detalle']
            detalle_list = []

            if isinstance(detalle, dict):
                detalle_list.append(detalle)
                detalle = detalle_list

            supplier = self.env['product.supplierinfo']
            supplier = supplier.search([('name', '=', partner.id)])
            precio_total = 0

            lines = []
            if supplier:
                for d in detalle:

                    d_supplier = supplier.filtered(
                        lambda x: x.product_code == d['codigoPrincipal'] or
                        x.product_name == d['descripcion'] or
                        x.product_name in d['descripcion'] or
                        d['descripcion'] in x.product_name)

                    product = d_supplier.product_tmpl_id

                    if partner.property_account_position_id and product.supplier_taxes_id:
                        tax_ids = partner.property_account_position_id.map_tax(product.supplier_taxes_id).ids
                    else:
                        tax_ids = product.supplier_taxes_id.ids

                    account = product.property_account_expense_id or product.categ_id.property_account_expense_categ_id

                    if not tax_ids and account:
                        return "No se encuentra ingresado una cuenta y un impuesto\n"

                    lines.append((0, 0, {
                                    'product_id': d_supplier.product_tmpl_id.id,
                                    'quantity': d['cantidad'],
                                    'price_unit': d['precioUnitario'],
                                    'name':  d['descripcion'],
                                    'account_id': account.id,
                                    'invoice_line_tax_ids': [(6, 0, tax_ids)],
                                    }))

            elif line.product_id and line.agrupate_product_lines:
                for d in detalle:
                    precio_producto = float(d['cantidad']) * float(d['precioUnitario'])
                    precio_total += precio_producto

                lines.append((0, 0, {
                                    'product_id': line.product_id.id,
                                    'quantity': 1,
                                    'price_unit': precio_total,
                                    'name':  line.product_id.name,
                                    'account_id': int(line.product_id.property_account_expense_id.id),
                                    'invoice_line_tax_ids': [(6, 0, line.product_id.supplier_taxes_id.ids)],
                                    }))

            elif line.product_id:
                for d in detalle:
                    lines.append((0, 0, {
                                    'product_id': line.product_id.id,
                                    'quantity': d['cantidad'],
                                    'price_unit': d['precioUnitario'],
                                    'name':  d['descripcion'],
                                    'account_id': int(line.product_id.property_account_expense_id.id),
                                    'invoice_line_tax_ids': [(6, 0, line.product_id.supplier_taxes_id.ids)],
                                    }))

            elif not line.product_id:
                products = self.env['product.product']
                for d in detalle:
                    try:
                        product = products.filtered(
                                    lambda x : x.default_code == d['codigoPrincipal'] or
                                    x.name == d['description'] or
                                    d['descripcion'] in x.name)

                        product = products.search(
                                    ['|', ('default_code', '=', d['codigoPrincipal']),
                                         ('name', '=', d['descripcion'])])
                        if not product:
                            product = product.create({
                                            'name': d['descripcion'],
                                            'default_code': d['codigoPrincipal'],
                                            'standard_price': d['precioUnitario'],
                                                      })
                    except:
                        product = products.filtered(
                                    lambda x : x.default_code == d['codigoInterno'] or
                                    x.name == d['description'] or
                                    d['descripcion'] in x.name)

                        product = products.search(
                                    ['|', ('default_code', '=', d['codigoInterno']),
                                         ('name', '=', d['descripcion'])])

                        if not product:
                            product = product.create({
                                            'name': d['descripcion'],
                                            'default_code': d['codigoInterno'],
                                            'standard_price': d['precioUnitario'],
                                                      })

                    if partner.property_account_position_id and product.supplier_taxes_id:
                        tax_ids = partner.property_account_position_id.map_tax(product.supplier_taxes_id).ids
                    else:
                        tax_ids = product.supplier_taxes_id.ids

                    account = product.property_account_expense_id or product.categ_id.property_account_expense_categ_id

                    if not tax_ids and not account:
                        e = "No se encuentra ingresado una CUENTA DE GASTOS y un IMPUESTO DE PROVEEDOR en el producto: {0}".format(product.name)
                        return e
                    elif not tax_ids and account:
                        e = "No se encuentra ingresado un IMPUESTO DE PROVEEDOR en el producto: {0}".format(product.name)
                        return e
                    elif tax_ids and not account:
                        e = "No se encuentra ingresado unz CUENTA DE GASTOS en el producto: {0}".format(product.name)
                        return e

                    lines.append((0, 0, {
                                    'product_id': product.id,
                                    'quantity': d['cantidad'],
                                    'price_unit': d['precioUnitario'],
                                    'name':  d['descripcion'],
                                    'account_id': account.id,
                                    'invoice_line_tax_ids': [(6, 0, tax_ids)],
                                    'discount': d['descuento']
                                    }))

            inv_dict = {
                    'comprobante_id': self.env['l10n_ec_sri.comprobante'].search(
                     [('code', '=', infoTributaria['codDoc'])], limit=1).id,
                    'secuencial':secuencial,
                    'invoice_line_ids': lines,
                    'establecimiento': infoTributaria['estab'],
                    'puntoemision': infoTributaria['ptoEmi'],
                    'autorizacion': autorizacion_dict['numeroAutorizacion'],
                    'type' : 'in_refund'
                    }

        vals = self.get_de_dict(estado, xml, infoTributaria)
        de_obj = self.env['l10n_ec_sri.documento.electronico']
        de = de_obj.create(vals)

        clave_acceso = infoTributaria['claveAcceso']

        return de, key, infoTributaria, clave_acceso, inv_dict, inv, secuencial

    @api.multi
    def button_new_data(self):
        self.wizard_line_ids.unlink()
        self.data_ids.unlink()
        self.no_conciliate_ids.unlink()
        self.conciliate_ids.unlink()
        self.state = 'draft'

    def params_context(self):
        context = dict(self._context or {})
        active_model = context.get('active_model')
        active_ids = context.get('active_ids')
        return context, active_model, active_ids

    @api.multi
    def button_import_file(self):
        self.data_ids.unlink()
        self.conciliate_ids.unlink()
        self.no_conciliate_ids.unlink()
        if not self.wizard_line_ids:
            raise UserError(_('No lines to process'))

        resumen_dict = {'error_en_comprobante':[],
                        'total': 0}
        for file in self.wizard_line_ids.mapped('import_file'):
            error = self._process_file(file)
            if error:
                resumen_dict['error_en_comprobante'].append(error)
                resumen_dict['total'] += 1

        if resumen_dict['total'] >= 1:
            advices =u"Error en la composición del {0} comprobante".format(resumen_dict['total'])
            txtfile = self.generate_file(resumen_dict)
            return self.env['custom.pop.message'].messagebox(advices, txtfile)

    @api.multi
    def button_refresh(self):
        self.button_import_file()

    @api.multi
    def button_confirm(self):
        if not self.wizard_line_ids:
            raise UserError(_('No lines to process'))
        self.state = 'open'

    @api.one
    def generate_file(self, resumen_dict):
        """
        function called from button
        """
        txt_msg = ""
        msg = ""
        for res, data in resumen_dict.iteritems():
            try:
                txt_msg += res + ": \n"
                for list_dict in data:
                    try:
                        msg = "\t" + str(list_dict['comprobante']) + " : " + "".join(map(str, (list_dict['secuencial']))) + "\n"
                    except:
                        try:
                            msg = "\t" + str(list_dict['mensaje']) + "\n"
                        except:
                            try:
                                if type(list_dict) == list:
                                    for list in list_dict:
                                        msg = "\t" + list + "\n"
                            except:
                                msg = "\t" + str(list_dict) + "\n"
                    txt_msg += msg
            except:
                txt_msg += "\t" + str(data) + "\n"
        return txt_msg.decode('unicode_escape')


class ComprobanteElectronicoPreValidate(models.TransientModel):
    _name = "l10n_ec_sri.ce.pre.validate"
    _description = "Get SRI information before validating"

    ruc = fields.Char(string='Ruc',)
    partner_id = fields.Many2one('res.partner',index=True)
    razon_social_emisor = fields.Char(string='R.S Emisor',)
    comprobante = fields.Char(string='Comp.',)
    numero_factura = fields.Char(string='No Fac.',)
    doc_modificado = fields.Char(string='Doc Modificado',)
    clave_acceso = fields.Char(string='C. Acesso',)
    product_id = fields.Many2one(comodel_name='product.product', string='Producto')
    fecha = fields.Date('Fecha')
    xml = fields.Binary(string='XML', attachment=True)
    prevalidate_id = fields.Many2one('l10n_ec_sri.ce.import.wizard')
    validate = fields.Boolean('Validar')
    agrupate_product_lines = fields.Boolean('Agrupar', help="Agrupa las lineas de todos los productos en una sola")
    nivel = fields.Char('Nivel')

    @api.multi
    def validar_doc(self):
        context = dict(self._context or {})
        active_model = context.get('active_model')
        active_ids = context.get('active_ids')
        data = self.read()[0]
        prevalidate_line = self
        return self.env['l10n_ec_sri.ce.import.wizard'].validate_one(context,context, active_ids, prevalidate_line)

class ComprobanteEstado(models.TransientModel):
    _name = "l10n_ec_sri.doc.import.estado"
    _description = "Estados de los documentos importados"

    clave_acceso = fields.Char(string='C. Acesso',)
    numero_factura = fields.Char(string='No.Fac',)
    partner_id = fields.Many2one('res.partner', 'Proveedor', index=True)
    ruc = fields.Char(string='Ruc',)
    invoice_id = fields.Many2one(
        'account.invoice', string='Factura', )
    conciliate_id = fields.Many2one('l10n_ec_sri.ce.import.wizard',)
    no_conciliate_id = fields.Many2one('l10n_ec_sri.ce.import.wizard',)
    motivo = fields.Char(string='Motivo',)


