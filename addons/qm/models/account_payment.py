from odoo import api, models, _, fields
from odoo.exceptions import UserError
from odoo.tools import float_compare


class AccountPayment(models.Model):
    _inherit = "account.payment"
    _order = "id desc"

    overpayment_amount = fields.Monetary(
        compute="_compute_overpayment_amount", readonly=True
    )

    def post(self):
        for pay in self:
            if pay.partner_type == "supplier":
                if pay.payment_type == "outbound" and pay.payment_difference > 0:
                    raise UserError(_("Amount is more than actual"))

                elif pay.payment_type == "inbound" and pay.payment_difference < 0:
                    raise UserError(_("Amount is more than actual"))
        return super(AccountPayment, self).post()

    @api.depends("invoice_ids", "amount", "payment_date", "currency_id", "payment_type")
    def _compute_overpayment_amount(self):
        for pay in self:
            partials = pay.move_line_ids.mapped(
                "matched_debit_ids"
            ) + pay.move_line_ids.mapped("matched_credit_ids")
            amount = 0.0
            for partial in partials:
                amount += partial.amount
            if float_compare(pay.amount, amount, precision_rounding=0.01) > 0:
                pay.overpayment_amount = pay.amount - amount
            else:
                pay.overpayment_amount = 0.0
