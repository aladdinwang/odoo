from odoo import api, models, _, fields
from odoo.exceptions import UserError
from odoo.tools import float_compare


class AccountPayment(models.Model):
    _inherit = "account.payment"
    _order = "id desc"

    overpayment_amount = fields.Monetary(
        compute="_compute_overpayment_amount", readonly=True
    )
    sale_register_id = fields.Many2one("sale.payment.register", index=True)

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


# 销售到款单
class SalePaymentRegister(models.Model):
    _name = "sale.payment.register"
    _inherit = ["portal.mixin", "mail.thread", "mail.activity.mixin"]

    _description = "Sale Payment Register"

    name = fields.Char(readonly=True, copy=False)
    payment_type = fields.Selection(
        [
            ("outbound", "Send Money"),
            ("inbound", "Receive Money"),
            ("transfer", "Internal Transfer"),
        ],
        string="Payment Type",
        required=True,
        readonly=True,
        states={"draft": [("readonly", False)]},
    )
    partner_type = fields.Selection(
        [("customer", "Customer"), ("supplier", "Vendor")],
        tracking=True,
        readonly=True,
        states={"draft": [("readonly", False)]},
    )
    company_id = fields.Many2one(
        "res.company", related="journal_id.company_id", string="Company", readonly=True
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Partner",
        tracking=True,
        readonly=True,
        states={"draft": [("readonly", False)]},
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    payment_date = fields.Date(required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one(
        "account.journal", required=True, domain=[("type", "in", ("bank", "cash"))]
    )
    payment_method_id = fields.Many2one(
        "account.payment.method",
        string="Payment Method Type",
        required=True,
        help="Manual: Get paid by cash, check or any other method outside of Odoo.\n"
        "Electronic: Get paid automatically through a payment acquirer by requesting a transaction on a card saved by the customer when buying or subscribing online (payment token).\n"
        "Check: Pay bill by check and print it from Odoo.\n"
        "Batch Deposit: Encase several customer checks at once by generating a batch deposit to submit to your bank. When encoding the bank statement in Odoo, you are suggested to reconcile the transaction with the batch deposit.To enable batch deposit, module account_batch_payment must be installed.\n"
        "SEPA Credit Transfer: Pay bill from a SEPA Credit Transfer file you submit to your bank. To enable sepa credit transfer, module account_sepa must be installed ",
    )
    payment_method_code = fields.Char(
        related="payment_method_id.code",
        help="Technical field used to adapt the interface to the payment type selected.",
        readonly=True,
    )

    amount = fields.Monetary(
        string="Amount",
        required=True,
        readonly=True,
        states={"draft": [("readonly", False)]},
        tracking=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        required=True,
        readonly=True,
        states={"draft": [("readonly", False)]},
        default=lambda self: self.env.company.currency_id,
    )
    communication = fields.Char(string="Memo", tracking=True)

    # one2many line
    line_ids = fields.One2many(
        "sale.payment.register.line", "register_id", string="Register Lines"
    )
    payment_ids = fields.One2many(
        "account.payment", "sale_register_id", string="Payments"
    )

    # return, returned已退票
    # posted 待付款
    # waiting 销售认领
    # reject 已驳回
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("waiting", "Waiting"),
            ("reconciled", "Reconciled"),
            ("cancelled", "Cancelled"),
        ],
        readonly=True,
        default="draft",
        copy=False,
        string="Status",
    )

    cancel_by = fields.Many2one("res.users", string="Cancel by")
    cancel_date = fields.Date(string="Cancelled Date", index=True)
    reconciled_by = fields.Many2one("res.users", string="Reconciled by")
    reconciled_date = fields.Date(string="Reconciled Date", index=True)


class SalePaymentRegisterLine(models.Model):
    _name = "sale.payment.register.line"
    _description = "Sale Payment Register Line"

    register_id = fields.Many2one("sale.payment.register", index=True, required=True)
    invoice_id = fields.Many2one("account.move", index=True, required=True)
    amount = fields.Monetary(
        string="Amount",
        required=True,
        tracking=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="register_id.currency_id",
        readonly=True,
    )
    sequence = fields.Integer(default=10)
