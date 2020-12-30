# -*- coding: utf-8 -*-
{
    'name': "SRI - Emision de comprabantes electronicos",
    'summary': """SRI Emisión de comprobantes electrónicos off-line.""",
    'version': '12.0.0.0.1',
    'author': "Fabrica de Software Libre,Odoo Community Association (OCA)",
    'maintainer': 'Fabrica de Software Libre',
    'website': 'http://www.libre.ec',
    'license': 'OPL-1',
    'category': 'Account',
    'depends': [
        'base',
        'l10n_ec_sri',
        'stock_picking_invoice_link',
        'partner_contact_tradename',
        'account_invoice_discount_amount',
        'base_mail_custom_attachment',
        'base_mail_custom_cc',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ambiente.xml',
        'data/data.xml',
        'views/account_invoice.xml',
        'views/res_company.xml',
        'views/res_partner.xml',
        'views/sri.xml',
        'views/report_paper_format.xml',
        'views/account_invoice_report.xml',
        'data/invoice_action_data.xml',
    ],
    'demo': [],
    'test': [],
    'installable': True,
}