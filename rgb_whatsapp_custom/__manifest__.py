# -*- coding: utf-8 -*-
{
    'name': "WhatsApp Custom",

    'summary': "WhatsApp Customization",

    'description': """
    This module customizes the WhatsApp integration in Odoo.
    """,

    'author': "Ragab",
    'website': "",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'WhatsApp',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'whatsapp', 'calendar'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'data/data.xml',
        'views/event.xml',
    ],
}

