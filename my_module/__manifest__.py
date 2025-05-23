# -*- coding: utf-8 -*-
{
    'name': "Chatbot AI",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
Long description of module's purpose
    """,

    'author': "Sellside",
    #'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Discuss',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['mail', 'project', 'discuss'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'data/chatbot_ai_data.xml',
    ],
    # only loaded in demonstration mode
    #'demo': [
    #    'demo/demo.xml',
    #],
    'license': 'LGPL-3',
    'installable': True,  # ← Agrega esto
    'auto_install': False,  #
}


