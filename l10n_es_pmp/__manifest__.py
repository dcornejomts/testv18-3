{
    'name': 'Período Medio de Pago a Proveedores (España)',
    'version': '18.0.1.2.0',
    'category': 'Accounting/Localizations/Reporting',
    'summary': 'Calcula el PMP a proveedores para el Registro Mercantil (Ley 15/2010)',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'report/pmp_report.xml',
        'wizard/pmp_wizard_views.xml',
    ],
    'license': 'LGPL-3',
}
