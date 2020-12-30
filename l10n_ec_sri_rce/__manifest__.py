# -*- coding: utf-8 -*-
{
    'name': "SRI - Recepción de comprabantes electronicos",
    'summary': """SRI Emisión de comprobantes electrónicos off-line.""",
    'version': '12.0.0.0.1',
    'author': "Fabrica de Software Libre,Odoo Community Association (OCA),Integreación de Sistemas Corporativos (ISISCOR)",
    'maintainer': 'Fabrica de Software Libre, Integreación de Sistemas Corporativos',
    'website': 'http://www.libre.ec',
    'license': 'OPL-1',
    'category': 'Account',
    'depends': [
        'base',
        'l10n_ec_sri_ece',
        'base_custom_popup_message',
    ],
    'data': [
        'wizards/ce_import_view.xml',
        'views/account_invoice.xml',
    ],
    'demo': [],
    'test': [],
    'installable': True,
}
