import base64
import io
import datetime

from odoo import models, fields, api, _
from odoo.exceptions import UserError


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
    pmp_paid = fields.Float(string='Ratio pagos realizados (días)', digits=(10, 2), readonly=True)
    pmp_pending = fields.Float(string='Ratio pagos pendientes (días)', digits=(10, 2), readonly=True)
    pmp_total = fields.Float(string='PMP Total (días)', digits=(10, 2), readonly=True)
    line_ids = fields.One2many('l10n.es.pmp.line', 'wizard_id', string='Detalle')

    def action_compute(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('La fecha de inicio no puede ser posterior a la fecha de fin.'))

        self.line_ids.unlink()

        self.env.cr.execute("""
            SELECT
                am.name                                          AS invoice_name,
                rp.name                                          AS partner_name,
                am.invoice_date,
                aml.date_maturity                                AS invoice_due_date,
                aml_pay.date                                     AS payment_date,
                ap.date                                          AS payment_date_manual,
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
            LEFT JOIN account_payment ap        ON ap.move_id = aml_pay.move_id
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

        self.env.cr.execute("""
            SELECT
                am.name                                          AS invoice_name,
                rp.name                                          AS partner_name,
                am.invoice_date,
                aml.date_maturity                                AS invoice_due_date,
                NULL::date                                       AS payment_date,
                ap.date                                          AS payment_date_manual,
                ABS(aml.amount_residual)                         AS amount,
                GREATEST(%(date_to)s - am.invoice_date, 0)      AS days,
                'pending'                                        AS line_type
            FROM account_move am
            JOIN res_partner rp        ON rp.id = am.partner_id
            JOIN account_move_line aml ON aml.move_id = am.id
            JOIN account_account aa    ON aa.id = aml.account_id
                                     AND aa.account_type = 'liability_payable'
            LEFT JOIN account_move__account_payment amp ON amp.invoice_id = am.id
            LEFT JOIN account_payment ap                ON ap.id = amp.payment_id
            WHERE am.move_type         = 'in_invoice'
              AND am.state             = 'posted'
              AND am.company_id        = %(company_id)s
              AND am.invoice_date      BETWEEN %(date_from)s AND %(date_to)s
              AND am.payment_state     IN ('not_paid', 'partial', 'in_payment')
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
                'invoice_due_date': row['invoice_due_date'],
                'payment_date': row['payment_date'],
                'payment_date_manual': row['payment_date_manual'],
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

    def action_print_pdf(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Primero calculá el PMP.'))
        return self.env.ref('l10n_es_pmp.action_report_pmp').report_action(self)

    def action_export_excel(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Primero calculá el PMP.'))

        try:
            import xlsxwriter
        except ImportError:
            raise UserError(_('La librería xlsxwriter no está disponible.'))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('PMP Proveedores')

        fmt_title = workbook.add_format({'bold': True, 'font_size': 14})
        fmt_bold = workbook.add_format({'bold': True})
        fmt_header = workbook.add_format({
            'bold': True, 'bg_color': '#374151', 'font_color': '#FFFFFF',
            'border': 1,
        })
        fmt_paid = workbook.add_format({'font_color': '#16a34a'})
        fmt_pending = workbook.add_format({'font_color': '#d97706'})
        fmt_date = workbook.add_format({'num_format': 'dd/mm/yyyy'})
        fmt_money = workbook.add_format({'num_format': '#,##0.00'})
        fmt_total = workbook.add_format({'bold': True, 'top': 1, 'num_format': '#,##0.00'})

        sheet.set_column(0, 0, 12)
        sheet.set_column(1, 1, 24)
        sheet.set_column(2, 2, 28)
        sheet.set_column(3, 6, 16)
        sheet.set_column(7, 7, 15)
        sheet.set_column(8, 8, 8)

        sheet.write(0, 0, 'Período Medio de Pago a Proveedores', fmt_title)
        sheet.write(1, 0, f'Empresa: {self.company_id.name}', fmt_bold)
        sheet.write(2, 0, f'Período: {self.date_from} — {self.date_to}', fmt_bold)
        sheet.write(3, 0, f'Ratio pagos realizados: {self.pmp_paid:.2f} días', fmt_bold)
        sheet.write(4, 0, f'Ratio pagos pendientes: {self.pmp_pending:.2f} días', fmt_bold)
        sheet.write(5, 0, f'PMP Total: {self.pmp_total:.2f} días', fmt_bold)

        headers = ['Estado', 'Factura', 'Proveedor', 'Fecha Factura', 'Fecha Vencimiento', 'Fecha Pago Manual', 'Fecha Pago Banco', 'Importe (€)', 'Días']
        for col, h in enumerate(headers):
            sheet.write(7, col, h, fmt_header)

        row = 8
        for line in self.line_ids:
            is_paid = line.line_type == 'paid'
            fmt_state = fmt_paid if is_paid else fmt_pending
            sheet.write(row, 0, 'Pagada' if is_paid else 'Pendiente', fmt_state)
            sheet.write(row, 1, line.invoice_name or '')
            sheet.write(row, 2, line.partner_name or '')
            if line.invoice_date:
                sheet.write_datetime(
                    row, 3,
                    datetime.datetime.combine(line.invoice_date, datetime.time()),
                    fmt_date,
                )
            if line.invoice_due_date:
                sheet.write_datetime(
                    row, 4,
                    datetime.datetime.combine(line.invoice_due_date, datetime.time()),
                    fmt_date,
                )
            if line.payment_date_manual:
                sheet.write_datetime(
                    row, 5,
                    datetime.datetime.combine(line.payment_date_manual, datetime.time()),
                    fmt_date,
                )
            if line.payment_date:
                sheet.write_datetime(
                    row, 6,
                    datetime.datetime.combine(line.payment_date, datetime.time()),
                    fmt_date,
                )
            sheet.write(row, 7, line.amount, fmt_money)
            sheet.write(row, 8, line.days)
            row += 1

        total_amount = sum(self.line_ids.mapped('amount'))
        sheet.write(row, 6, 'TOTAL', fmt_total)
        sheet.write(row, 7, total_amount, fmt_total)

        workbook.close()
        output.seek(0)

        filename = f'PMP_Proveedores_{self.date_from}_{self.date_to}.xlsx'
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'res_model': self._name,
            'res_id': self.id,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }


class L10nEsPmpLine(models.TransientModel):
    _name = 'l10n.es.pmp.line'
    _description = 'Línea de detalle PMP'

    wizard_id = fields.Many2one('l10n.es.pmp.wizard', required=True, ondelete='cascade')
    invoice_name = fields.Char(string='Factura')
    partner_name = fields.Char(string='Proveedor')
    invoice_date = fields.Date(string='Fecha Factura')
    invoice_due_date = fields.Date(string='Fecha Vencimiento')
    payment_date = fields.Date(string='Fecha Pago Banco')
    payment_date_manual = fields.Date(string='Fecha Pago Manual')
    amount = fields.Float(string='Importe', digits=(16, 2))
    days = fields.Integer(string='Días')
    line_type = fields.Selection(
        [('paid', 'Pagada'), ('pending', 'Pendiente')],
        string='Estado',
    )
