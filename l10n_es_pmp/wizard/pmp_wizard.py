from odoo import models, fields, api, _
from odoo.exceptions import UserError
import datetime


class L10nEsPmpWizard(models.TransientModel):
    _name = 'l10n.es.pmp.wizard'
    _description = 'Período Medio de Pago a Proveedores'

    date_from = fields.Date(
        string='Desde',
        required=True,
        default=lambda self: datetime.date.today().replace(month=1, day=1),
    )
    date_to = fields.Date(
        string='Hasta',
        required=True,
        default=lambda self: datetime.date.today().replace(month=12, day=31),
    )
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        default=lambda self: self.env.company,
    )
    pmp_paid = fields.Float(string='PMP Pagadas (días)', digits=(10, 2), readonly=True)
    pmp_pending = fields.Float(string='PMP Pendientes (días)', digits=(10, 2), readonly=True)
    pmp_total = fields.Float(string='PMP Total (días)', digits=(10, 2), readonly=True)
    line_ids = fields.One2many('l10n.es.pmp.line', 'wizard_id', string='Detalle')

    def action_compute(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('La fecha de inicio no puede ser posterior a la fecha de fin.'))

        self.line_ids.unlink()

        # Facturas pagadas: usa fecha del banco si existe, sino fecha del pago
        self.env.cr.execute("""
            SELECT
                am.name                                          AS invoice_name,
                rp.name                                          AS partner_name,
                am.invoice_date,
                aml_pay.date                                     AS payment_date,
                apr.amount                                       AS amount,
                GREATEST(aml_pay.date - am.invoice_date, 0)     AS days,
                'paid'                                          AS line_type
            FROM account_move am
            JOIN res_partner rp           ON rp.id = am.partner_id
            JOIN account_move_line aml    ON aml.move_id = am.id
            JOIN account_account aa       ON aa.id = aml.account_id
                                        AND aa.account_type = 'liability_payable'
            JOIN account_partial_reconcile apr ON apr.credit_move_id = aml.id
            JOIN account_move_line aml_pay     ON aml_pay.id = apr.debit_move_id
            WHERE am.move_type    = 'in_invoice'
              AND am.state        = 'posted'
              AND am.company_id   = %(company_id)s
              AND am.invoice_date BETWEEN %(date_from)s AND %(date_to)s
        """, {
            'company_id': self.company_id.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
        })
        paid_rows = self.env.cr.dictfetchall()

        # Facturas pendientes o pagadas parcialmente
        self.env.cr.execute("""
            SELECT
                am.name                                          AS invoice_name,
                rp.name                                          AS partner_name,
                am.invoice_date,
                NULL::date                                       AS payment_date,
                ABS(aml.amount_residual)                         AS amount,
                GREATEST(%(date_to)s - am.invoice_date, 0)      AS days,
                'pending'                                        AS line_type
            FROM account_move am
            JOIN res_partner rp        ON rp.id = am.partner_id
            JOIN account_move_line aml ON aml.move_id = am.id
            JOIN account_account aa    ON aa.id = aml.account_id
                                     AND aa.account_type = 'liability_payable'
            WHERE am.move_type         = 'in_invoice'
              AND am.state             = 'posted'
              AND am.company_id        = %(company_id)s
              AND am.invoice_date      BETWEEN %(date_from)s AND %(date_to)s
              AND am.payment_state     IN ('not_paid', 'partial')
              AND ABS(aml.amount_residual) > 0
        """, {
            'company_id': self.company_id.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
        })
        pending_rows = self.env.cr.dictfetchall()

        PmpLine = self.env['l10n.es.pmp.line']
        for row in paid_rows + pending_rows:
            PmpLine.create({
                'wizard_id': self.id,
                'invoice_name': row['invoice_name'],
                'partner_name': row['partner_name'],
                'invoice_date': row['invoice_date'],
                'payment_date': row['payment_date'],
                'amount': float(row['amount']),
                'days': int(row['days']),
                'line_type': row['line_type'],
            })

        paid_lines = self.line_ids.filtered(lambda l: l.line_type == 'paid')
        pending_lines = self.line_ids.filtered(lambda l: l.line_type == 'pending')

        total_paid = sum(paid_lines.mapped('amount'))
        total_pending = sum(pending_lines.mapped('amount'))
        total = total_paid + total_pending

        self.pmp_paid = (
            sum(l.amount * l.days for l in paid_lines) / total_paid
            if total_paid else 0.0
        )
        self.pmp_pending = (
            sum(l.amount * l.days for l in pending_lines) / total_pending
            if total_pending else 0.0
        )
        self.pmp_total = (
            sum(l.amount * l.days for l in self.line_ids) / total
            if total else 0.0
        )

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n.es.pmp.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class L10nEsPmpLine(models.TransientModel):
    _name = 'l10n.es.pmp.line'
    _description = 'Línea de detalle PMP'

    wizard_id = fields.Many2one('l10n.es.pmp.wizard', required=True, ondelete='cascade')
    invoice_name = fields.Char(string='Factura')
    partner_name = fields.Char(string='Proveedor')
    invoice_date = fields.Date(string='Fecha Factura')
    payment_date = fields.Date(string='Fecha Pago Banco')
    amount = fields.Float(string='Importe', digits=(16, 2))
    days = fields.Integer(string='Días')
    line_type = fields.Selection(
        [('paid', 'Pagada'), ('pending', 'Pendiente')],
        string='Estado',
    )
