# -*- coding: utf-8 -*-
from odoo import api, fields, models


ADDRESS_FIELDS = ('vat', 'street', 'street2', 'zip', 'city', 'state_id', 'country_id')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _display_address(self, without_company=False):
        '''
        The purpose of this function is to build and return an address formatted accordingly to the
        standards of the country where it belongs.

        :param address: browse record of the res.partner to format
        :returns: the address formatted in a display that fit its country habits (or the default ones
            if not country is specified)
        :rtype: string
        '''

        # get the information that will be injected into the display format
        # get the address format
        address_format = self._get_address_format()
        args = {
            'state_code': self.state_id.code or '',
            'state_name': self.state_id.name or '',
            'country_code': self.country_id.code or '',
            'country_name': self._get_country_name(),
            'company_name': self.commercial_company_name or '',
        }
        for field in self._address_fields():
            args[field] = getattr(self, field) or ''
        if without_company:
            args['company_name'] = ''
        elif self.commercial_company_name:
            address_format = '%(company_name)s\n' + address_format
        return address_format % args

    def _address_fields(self):
        """ Returns the list of address fields that are synced from the parent
        when the `use_parent_address` flag is set. """
        return list(ADDRESS_FIELDS)

    def _default_country_id(self):
        country = self.env['res.country'].search([('code', '=ilike', 'EC')])
        return country

    country_id = fields.Many2one(default=_default_country_id, )

    vat = fields.Char('Identificacion fiscal', size=13, required=True)
    formapago_id = fields.Many2one(
        'l10n_ec_sri.formapago', string='Forma de pago principal', )
    parterel = fields.Boolean(
        string="¿Es parte relacionada?", copy=False, )

    @api.onchange('property_account_position_id')
    def _onchange_property_account_position(self):
        if self.property_account_position_id:
            fiscal = self.property_account_position_id
            payable, receivable, formapago = self._get_payable_receivable(fiscal=fiscal)
            if not self.property_account_payable_id:
                self.property_account_payable_id = payable
            if not self.property_account_receivable_id:
                self.property_account_receivable_id = receivable
            if not self.formapago_id:
                self.formapago_id = formapago

    def _get_fiscal_position(self, vat=False):
        fiscal = fiscal_obj = self.env['account.fiscal.position']
        vat = vat or self.vat
        # Si tiene 10 dígitos es una cédula
        if len(vat) == 10 and vat.isdigit():
            fiscal = self.env.ref('l10n_ec_sri.fiscal_position_consumidor')
        # Si tiene 13 dígitos, es número y termina en 001 es un RUC.
        elif len(vat) == 13 and vat.isdigit() and vat[-3:] == '001':
            d = vat[2:3]
            # # Si el tercer dígito es 6 debe ser una institución pública.
            if d == '6':
                fiscal = self.env.ref('l10n_ec_sri.fiscal_position_gobierno')
            # Si el tercer dígito es 9 es sociedad o extranjero sin cédula.
            elif d == '9':
                fiscal = self.env.ref('l10n_ec_sri.fiscal_position_sociedad')
            # Si el tercer dígito es menor a 6 es una persona natural.
            elif d in ('0','1','2','3','4','5'):
                fiscal = self.env.ref('l10n_ec_sri.fiscal_position_natural')
        else:
            # Si no podemos identificar la posición fiscal, es del exterior.
            fiscal = self.env.ref('l10n_ec_sri.fiscal_position_exterior')
        return fiscal

    def _get_payable_receivable(self, fiscal=False):
        payable = receivable = self.env['account.account']
        formapago = self.env['l10n_ec_sri.formapago']
        if fiscal:
            payable = fiscal.property_account_payable_id
            receivable = fiscal.property_account_receivable_id
            formapago = fiscal.formapago_id
        return payable, receivable, formapago

    @api.model
    def create(self, vals):
        res = super(ResPartner, self).create(vals)
        vat = vals.get('vat', False)
        fiscal = vals.get('property_account_position_id', False)

        # Si la posición fiscal está en vals, la respetamos.
        if not fiscal and vat:
            fiscal = self._get_fiscal_position(vat=vat)
        else:
            fiscal = self.env['account.fiscal.position'].browse(fiscal)

        # Con la posición fiscal calculamos las cuentas contables.
        p, r, f = self._get_payable_receivable(fiscal=fiscal)

        # Respetamos los datos de vals, sino, ponemos los calculados.
        payable = vals.get('property_account_payable_id', p.id)
        receivable = vals.get('property_account_receivable_id', r.id)
        formapago = vals.get('formapago_id', f.id)
        res.update(
            {
                'property_account_position_id': fiscal.id,
                'property_account_receivable_id': receivable,
                'property_account_payable_id': payable,
                'formapago_id': formapago,
            }
        )
        return res

