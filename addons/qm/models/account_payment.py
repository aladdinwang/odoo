from odoo import models, _
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def post(self):
        for pay in self:
            if pay.partner_type == "supplier":
                if pay.payment_type == "outbound" and pay.payment_difference > 0:
                    raise UserError(_("Amount is more than actual"))

                elif pay.payment_type == "inbound" and pay.payment_difference < 0:
                    raise UserError(_("Amount is more than actual"))
        return super(AccountPayment, self).post()
