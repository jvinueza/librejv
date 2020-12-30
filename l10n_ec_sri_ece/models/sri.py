# -*- coding: utf-8 -*-
import base64
import logging
import os
from io import BytesIO
import subprocess
import tempfile
import xml
from collections import OrderedDict
from datetime import datetime
from random import randrange

from lxml import etree as e
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import config

_logger = logging.getLogger(__name__)

try:
    import xmltodict
except ImportError:
    _logger.error(
        "The module xmltodict can't be loaded, try: pip install xmltodict")

try:
    from zeep import Client
except ImportError:
    _logger.warning("The module zeep can't be loaded, try: pip install zeep")

try:
    from barcode import generate
    from barcode.writer import ImageWriter
except ImportError:
    _logger.warning(
        "The module viivakoodi can't be loaded, try: pip install viivakoodi")


ESTADOS_POSITIVOS_SRI = [
    'AUTORIZADO',
    'EN PROCESO',
    'RECIBIDA'
]

ESTADOS_NEGATIVOS_SRI = [
    'DEVUELTA',
    'NO AUTORIZADO',
    'RECHAZADA'
]

class SriFirma(models.Model):
    _name = 'l10n_ec_sri.firma'

    name = fields.Char(string='Descripción', required=True, )
    p12 = fields.Binary(string='Archivo de firma p12', required=True, )
    clave = fields.Char(string='Contraseña', required=True, )
    path = fields.Char(string='Ruta en disco', readonly=True, )
    valid_to = fields.Date(string='', )

    def save_sign(self, p12):
        """
        Almacena la firma en disco
        :param p12: fields.Binary firma pfx
        :return: str() ruta del archivo
        """
        data_dir = config['data_dir']
        db = self.env.cr.dbname
        tmpp12 = tempfile.TemporaryFile()
        tmpp12 = tempfile.NamedTemporaryFile(suffix=".p12", prefix="firma_", dir=''.join(
            [data_dir, '/filestore/', db]), delete=False)  # TODO Cambiar la ruta
        tmpp12.write(base64.b64decode(p12))
        tmpp12.seek(0)
        return tmpp12.name

    @api.model
    def create(self, vals):
        if 'p12' in vals:
            vals['path'] = self.save_sign(vals['p12'])
        return super(SriFirma, self).create(vals)

    @api.multi
    def write(self, vals):
        if 'p12' in vals:
            vals['path'] = self.save_sign(vals['p12'])
        return super(SriFirma, self).write(vals)

    @api.multi
    def unlink(self):
        os.remove(self.path)
        return super(SriFirma, self).unlink()


class SriAmbiente(models.Model):
    _name = 'l10n_ec_sri.ambiente'

    name = fields.Char(string='Descripción', )
    ambiente = fields.Selection(
        [
            ('1', 'Pruebas'),
            ('2', 'Producción'),
        ],
        string='Ambiente', )
    recepcioncomprobantes = fields.Char(
        string='URL de recepción de comprobantes', )
    autorizacioncomprobantes = fields.Char(
        string='URL de autorización de comprobantes', )


class SriDocumentoElectronico(models.Model):
    _name = 'l10n_ec_sri.documento.electronico'

    @api.multi
    def name_get(self):
        return [(documento.id, '%s %s' % (documento.claveacceso, documento.estado)) for documento in self]

    @api.model
    def create(self, vals):
        res = super(SriDocumentoElectronico, self).create(vals)
        if not res:
            return

        line = self.env['l10n_ec_sri.documento.electronico.queue.line']
        line.create({
            'queue_id': self.env.ref('l10n_ec_sri_ece.documento_electronico_queue').id,
            'documento_electronico_id': res.id,
        })

        return res

    @api.multi
    def validate_xsd_schema(self, xml, xsd_path):
        """

        :param xml: xml codificado como utf-8
        :param xsd_path: /dir/archivo.xsd
        :return:
        """
        xsd_path = os.path.join(__file__, "../..", xsd_path)
        xsd_path = os.path.abspath(xsd_path)

        xsd = open(xsd_path)
        schema = e.parse(xsd)
        xsd = e.XMLSchema(schema)

        xml = e.XML(xml)

        try:
            xsd.assertValid(xml)
            return True
        except e.DocumentInvalid:
            return False

    @api.multi
    def modulo11(self, clave):
        digitos = list(clave)
        nro = 6  # cantidad de digitos en cada segmento
        segmentos = [digitos[n:n + nro] for n in range(0, len(digitos), nro)]
        total = 0
        while segmentos:
            segmento = segmentos.pop()
            factor = 7  # numero inicial del mod11
            for s in segmento:
                total += int(s) * factor
                factor -= 1
        mod = 11 - (total % 11)
        if mod == 11:
            mod = 0
        elif mod == 10:
            mod = 1
        return mod

    @api.multi
    def firma_xades_bes(self, xml, p12, clave):
        """
        :param xml: cadena xml
        :param clave: clave en formato base64
        :param p12: archivo p12 en formato base64
        :return:
        """
        jar_path = os.path.join(__file__, "../../src/xadesBes/firma.jar")
        jar_path = os.path.abspath(jar_path)

        cmd = ['java', '-jar', jar_path, xml, p12, clave]

        try:
            subprocess.check_output(cmd)
            sp = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT)
            res = sp.communicate()
            return res[0]
        except subprocess.CalledProcessError as se:
            _logger.exception('FIRMA ELECTRONICA FALLIDA: %s' % se.returncode)
            raise UserError(
                _("Firma electrónica fallida, por favor, "
                  "verifique el archivo y la contraseña"
                 )
            )

    @api.multi
    def process_de(self):
        if self.estado == 'NO ENVIADO':
            self.send_de_backend()
        elif self.estado in ('RECIBIDA', 'EN PROCESO'):
            self.receive_de_offline()
        elif self.estado == 'DEVUELTA':
            if "CLAVE ACCESO REGISTRADA" in self.mensajes:
                self.receive_de_offline()
        if self.estado in ('DEVUELTA', 'NO AUTORIZADO', 'RECHAZADA'):
            # TODO: NOTIFICAR AL USUARIO.
            pass
        return True

    @api.multi
    def send_de_backend(self):
        """
        Envía el documento electrónico desde el backend
        para evitar demoras en caso de que el SRI se encuentre
        fuera de línea.

        """
        ambiente_id = self.env.user.company_id.ambiente_id
        xml = base64.b64decode(self.xml_file)

        # Si la función es llamada sin xml puede ser un
        # comprobante ingresado manualmente por el usuario.
        if not xml and self.claveacceso:
            try:
                # Intentamos obtener el estado con la clave
                # provista por el usuario.
                self.receive_de_offline()
                return
            except:
                return

        envio = self.send_de_offline(ambiente_id, xml)
        if envio:
            self.write({
                'estado': envio['estado'] or 'NO ENVIADO',
                'mensajes': envio['comprobantes'] or '',
            })
            return True
        else:
            return False

    @api.multi
    def send_de_offline(self, ambiente_id, xml):
        """
        :param ambiente_id: recordset del ambiente
        :param xml: documento xml en base 64
        :return: respuesta del SRI
        """
        client = Client(ambiente_id.recepcioncomprobantes)
        with client.options(raw_response=False):
            response = client.service.validarComprobante(xml)
        return response

    @api.multi
    def receive_de_offline(self):
        ambiente_id = self.env.user.company_id.ambiente_id
        claveacceso = self.claveacceso

        client = Client(ambiente_id.autorizacioncomprobantes)
        with client.options(raw_response=False):
            response = client.service.autorizacionComprobante(claveacceso)
            try:
                # El SRI retorna numeroComprobantes 0 cuando tiene errores
                # en su sistema y no se almacena el comprobante correctamente.
                if response['numeroComprobantes'] == '0':
                    # Volvemos a enviar el comprobante.
                    self.send_de_backend()
                    return
                else:
                    autorizaciones = response['autorizaciones']['autorizacion'][0]
            except:
                self.mensajes = str(response)
                return False

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
            comprobante = xml.sax.saxutils.unescape(
                xmltodict.unparse(autorizacion))
            self.write({
                'estado': autorizaciones['estado'],
                'mensajes': autorizaciones['mensajes'],
                'xml_file': base64.b64encode(comprobante.encode('utf-8')),
                'fechaautorizacion': fields.Datetime.to_string(autorizaciones['fechaAutorizacion']),
            })

            # Enviar correo si el documento es AUTORIZADO.
            try:
                sent = self.reference.send_email_de()
                # Si se envía, marcamos la línea como enviada.
                if sent:
                    line_obj = self.env['l10n_ec_sri.documento.electronico.queue.line']
                    line = line_obj.search([('documento_electronico_id','=', self.id)], limit=1)
                    line.sent = True
            except:
                pass
        else:
            self.write({
                'estado': autorizaciones['estado'],
                'mensajes': autorizaciones['mensajes'],
            })
        return True

    @api.multi
    def get_documento_electronico_dict(
            self, ambiente_id, comprobante_id, documento, claveacceso, tipoemision, reference):
        # Generamos el xml en memoria.
        xml = xmltodict.unparse(documento, pretty=False)
        xml = xml.encode('utf8')

        # Validamos el esquema.
        xsd_path = 'src/esquemasXsd/Factura_V_1_1_0.xsd'
        self.validate_xsd_schema(xml, xsd_path)

        firma = self.env.user.company_id.firma_id
        #TODO JV: clave = base64.b64encode(firma.clave.tobytes()).decode('ascii')
        clave = base64.b64encode(firma.clave.encode('utf-8'))
        
        if not os.path.exists(firma.path):
            firma.write({
                'path': firma.save_sign(firma.p12),
            })
        #TODO JV: p12 = base64.b64encode(firma.path)
        p12 = base64.b64encode(firma.path.encode('utf-8')
        xml = self.firma_xades_bes(xml, p12, clave)
        filename = ''.join([claveacceso, '.xml'])

        # Creamos el diccionario del documento electrónico.
        vals = {
            'xml_file': base64.b64encode(xml),
            'xml_filename': filename,
            'estado': 'NO ENVIADO',
            'mensajes': '',
            'ambiente': ambiente_id.ambiente,
            'tipoemision': tipoemision,
            'claveacceso': claveacceso,
            'reference': reference,
            'comprobante_id': comprobante_id.id,
        }
        return vals

    @api.multi
    def get_claveacceso(self, fecha, comprobante, ruc, ambiente_id,
                        establecimiento, puntoemision, secuencial):
        """
        :param fecha: fields.Date
        :param comprobante: código del tipo de comprobante en str zfill(2)
        :param ruc: de la empresa en str
        :param ambiente_id: recordset
        :param comprobante: str
        :param puntoemision: str
        :param secuencial: str
        :return:
        """
        inv = self.env['account.invoice']
        today = fields.Datetime.from_string(inv.date_tz(fields.Date.today()))
        fecha = datetime.strptime(fecha, '%Y-%m-%d')
        if today < fecha:
            raise UserError(_("No puede generar una documento electrónico con fecha futura."))
        data = [
            fecha.strftime('%d%m%Y'),
            str(comprobante),
            str(ruc),
            str(ambiente_id.ambiente),
            str(establecimiento).zfill(3),
            str(puntoemision).zfill(3),
            str(secuencial).zfill(9),
            str(randrange(1, 99999999)).zfill(8),
            '1',
        ]
        try:
            claveacceso = ''.join(data)
            claveacceso += str(self.modulo11(claveacceso))
        except:
            raise UserError(_(
                u"""
                Falta informacion:
                fecha = %s,
                comprobante = %s,
                ruc = %s,
                ambiente = %s,
                establecimiento = %s,
                puntoemision = %s,
                secuencial = %s,
                nro aleatorio = %s,
                Tipo de emisión = %s,
                """ % tuple(data)))
        return claveacceso

    @api.multi
    def _get_reference_models(self):
        records = self.env['ir.model'].search(
            ['|', ('model', '=', 'account.invoice'), ('model', '=', 'stock.picking')])
        return [(record.model, record.name) for record in records] + [('', '')]

    reference = fields.Reference(
        string='Reference', selection='_get_reference_models')

    comprobante_id = fields.Many2one(
        'l10n_ec_sri.comprobante', string='Comprobante', copy=False, )

    tipoemision = fields.Selection(
        [
            ('1', 'Emisión normal'),
            ('2', 'Emisión por indisponibilidad del sistema'),
        ],
        string='Tipo de emisión', )

    ambiente = fields.Selection([
        ('1', 'Pruebas'),
        ('2', 'Producción'),
    ], string='Ambiente', )

    @api.one
    def get_barcode_128(self):
        if self.claveacceso:
            file_data = BytesIO()
            generate('code128', u'{}'.format(self.claveacceso),
                     writer=ImageWriter(), output=file_data)
            file_data.seek(0)
            self.barcode128 = base64.encodestring(file_data.read())

    claveacceso = fields.Char('Clave de acceso', )
    barcode128 = fields.Binary('Barcode', compute=get_barcode_128)
    fechaautorizacion = fields.Datetime('Fecha y hora de autorización', )
    mensajes = fields.Text('Mensajes', )
    estado = fields.Selection([
        ('NO ENVIADO', 'NO ENVIADO'),  # Documentos fuera de línea.
        ('RECIBIDA', 'RECIBIDA'),
        ('EN PROCESO', 'EN PROCESO'),
        ('DEVUELTA', 'DEVUELTA'),
        ('AUTORIZADO', 'AUTORIZADO'),
        ('NO AUTORIZADO', 'NO AUTORIZADO'),
        ('RECHAZADA', 'RECHAZADA'),
    ])

    xml_file = fields.Binary('Archivo XML', attachment=True, readonly=True, )
    xml_filename = fields.Char('Filename', )


class SriDocumentosElectronicosQueue(models.Model):
    _name = 'l10n_ec_sri.documento.electronico.queue'
    _description = 'Documentos Electronicos queue'

    name = fields.Char(string='Name', )
    queue_line_ids = fields.One2many(
        'l10n_ec_sri.documento.electronico.queue.line',
        'queue_id',
        string='Cola de documentos electrónicos',
    )

    @api.model
    def process_de_queue(self, ids=None):
        queue = self.env.ref('l10n_ec_sri_ece.documento_electronico_queue')

        to_delete = queue.queue_line_ids.filtered(
            lambda x:
                # Eliminamos las autorizadas que han sido enviadas por correo.
                (x.sent == True and x.estado == 'AUTORIZADO')
                # Las que no tienen documento electrónico.
                or not x.documento_electronico_id
                # Los estados de rechazo también terminan el proceso.
                # Se reinicia con la corrección del documento.
                or x.estado in ('DEVUELTA', 'NO AUTORIZADO', 'RECHAZADA')
        )
        if to_delete:
            # Usamos try porque es posible que el cron se ejecute
            # al mismo tiempo que una orden manual del usuario
            # y se intente borrar dos veces el mismo record.
            try:
                to_delete.unlink()
            except:
                pass

        # Eliminamos los documentos electronicos que han sido sustituidos.
        corregidas = queue.queue_line_ids.filtered(lambda x: not x.reference)
        for c in corregidas:
            # Dejamos las líneas para que se eliminen en la próxima ejecución.
            c.documento_electronico_id.unlink()

        pendientes = queue.queue_line_ids
        for p in pendientes:
            de = p.documento_electronico_id
            if de.estado == 'NO ENVIADO':
                de.send_de_backend()

            if de.estado in ('RECIBIDA', 'EN PROCESO'):
                de.receive_de_offline()

            if not p.sent and p.estado == 'AUTORIZADO':
                try:
                    sent = de.reference.send_email_de()
                    p.sent = sent
                except:
                    p.sent = False


class SriDocumentosElectronicosQueueLine(models.Model):
    _name = 'l10n_ec_sri.documento.electronico.queue.line'
    _description = 'Documentos Electronicos queue line'
    _order = 'create_date desc'

    sent = fields.Boolean(string='Sent', )
    estado = fields.Selection(
        string='State', related="documento_electronico_id.estado",
        store=True, )

    documento_electronico_id = fields.Many2one(
        'l10n_ec_sri.documento.electronico', string='Documento electronico', )
    reference = fields.Reference(
        related='documento_electronico_id.reference', string=_('Reference'))
    queue_id = fields.Many2one(
        'l10n_ec_sri.documento.electronico.queue', string='Queue', )

