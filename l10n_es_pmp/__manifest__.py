{
    'name': 'Período Medio de Pago a Proveedores (España)',
    'version': '18.0.1.2.0',
    'category': 'Accounting/Localizations/Reporting',
    'summary': 'Calcula el PMP a proveedores para el Registro Mercantil (Ley 15/2010)',
    'author': 'Madetosoft',
    'website': 'https://www.madetosoft.com',
    'description': """
Período Medio de Pago a Proveedores (España)
============================================

Calcula el Período Medio de Pago (PMP) a proveedores según la metodología
establecida por el ICAC y la Ley 15/2010 de medidas de lucha contra la morosidad,
requerido para el depósito de cuentas en el Registro Mercantil.

Funcionalidades
---------------
* Cálculo del ratio de pagos realizados y pendientes
* Detalle por factura con fecha de vencimiento y fechas de pago
* Soporte para facturas con múltiples cuotas (pagos parciales)
* Exportación a PDF y Excel
* Menú en Contabilidad > Reportes

Fórmula aplicada (Real Decreto 635/2014, modificado por RD 1040/2017)
----------------------------------------------------------------------
* Ratio pagados = Σ(días × importe) / total pagado
* Ratio pendientes = Σ(días × importe) / total pendiente
* PMP Total = (ratio_pagados × total_pagado + ratio_pendientes × total_pendiente) / total
""",
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'report/pmp_report.xml',
        'wizard/pmp_wizard_views.xml',
    ],
    'license': 'LGPL-3',
}
