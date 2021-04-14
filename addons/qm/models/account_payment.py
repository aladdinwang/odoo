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


class PaymentRegister(models.AbstractModel):
    _name = "payment.register"
    _inherit = ["portal.mixin", "mail.thread", "mail.activity.mixin"]

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
        "account.journal", required=True, domain="[('type', 'in', ('bank', 'cash'))]"
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
    communication = fields.Text(string="Memo", tracking=True)

    # payment_ids = fields.One2many(
    #     "account.payment", "sale_register_id", string="Payments"
    # )

    cancel_by = fields.Many2one(
        "res.users", string="Cancel by", readonly=True, tracking=True
    )
    cancel_date = fields.Date(
        string="Cancelled Date", index=True, readonly=True, tracking=True
    )
    # 确认人， 确认日期
    reconciled_by = fields.Many2one(
        "res.users", string="Reconciled by", readonly=True, tracking=True
    )
    reconciled_date = fields.Date(
        string="Reconciled Date", index=True, readonly=True, tracking=True
    )

    def action_draft(self):
        self.write({"state": "draft"})

    def action_reconcile(self):
        recs = self.filtered(lambda x: x.state == "confirmed")
        recs.write(
            {
                "state": "reconciled",
                "reconciled_by": self.env.user.id,
                "reconciled_date": fields.Date.today(),
            }
        )

    def action_cancel(self):
        self.write(
            {
                "state": "cancelled",
                "cancel_by": self.env.user.id,
                "cancel_date": fields.Date.today(),
            }
        )


# 销售到款单
class SalePaymentRegister(models.Model):
    _name = "sale.payment.register"
    _inherit = "payment.register"

    _description = "Sale Payment Register"

    # return, returned已退票
    # posted 待付款
    # waiting 销售认领
    # reject 已驳回
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("waiting", "Waiting"),
            ("confirmed", "Confirmed"),
            ("reconciled", "Reconciled"),
            ("cancelled", "Cancelled"),
        ],
        readonly=True,
        default="draft",
        copy=False,
        string="Status",
    )
    line_ids = fields.One2many(
        "sale.payment.register.line", "register_id", string="Register Lines"
    )
    # 销售处理人
    confirm_by = fields.Many2one(
        "res.users", string="Confirm by", readonly=True, tracking=True
    )
    confirm_date = fields.Date(
        string="Confirm Date", index=True, readonly=True, tracking=True
    )

    @api.model
    def default_get(self, default_fields):
        rec = super(SalePaymentRegister, self).default_get(default_fields)
        journal_id = self.env["account.journal"].search(
            [("type", "in", ("bank", "cash"))], limit=1
        )
        payment_method_ids = journal_id.inbound_payment_method_ids.ids

        default_payment_method_id = self.env.context.get("default_payment_method_id")
        if default_payment_method_id:
            payment_method_ids.append(default_payment_method_id)

        rec["payment_type"] = "inbound"
        rec["partner_type"] = "customer"
        rec["journal_id"] = journal_id.id
        rec["payment_method_id"] = payment_method_ids and payment_method_ids[0] or False
        return rec

    def post(self):
        for rec in self:
            if not rec.name:
                if rec.payment_type == "inbound":
                    seq_code = "sale.payment.register.invoice"
                elif rec.payment_type == "outbound":
                    seq_code = "sale.payment.regiter.refund"
                elif rec.payment_type == "transfer":
                    seq_code = "sale.payment.register.transfer"
                rec.name = self.env["ir.sequence"].next_by_code(seq_code)

        self.filtered(lambda x: x.state == "draft").write({"state": "waiting"})

    def name_get(self):
        return [(x.id, x.name or _("Draft Payment Register")) for x in self]

    @api.onchange("amount", "line_ids", "line_ids.amount")
    def _onchange_amount(self):
        total_amount = sum(x.amount for x in self.line_ids)
        if self.amount < total_amount:
            return {"warning": {"title": _("警告"), "message": _("明细金额超出总金额")}}

    def action_confirm(self):
        recs = self.filtered(lambda x: x.state == "waiting")
        recs.write(
            {
                "confirm_by": self.env.user.id,
                "state": "confirmed",
                "confirm_date": fields.Date.today(),
            }
        )


class SalePaymentRegisterLine(models.Model):
    _name = "sale.payment.register.line"
    _description = "Sale Payment Register Line"

    register_id = fields.Many2one("sale.payment.register", index=True, required=True)
    # invoice_id = fields.Many2one("account.move", index=True, required=True)
    # 关联销售单
    sale_order_id = fields.Many2one("sale.order", index=True, required=True)
    amount = fields.Monetary(string="Amount", required=True, tracking=True)
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="register_id.currency_id",
        readonly=True,
    )
    sequence = fields.Integer(default=10)


class PurchasePaymentRegister(models.Model):
    _name = "purchase.payment.register"
    _inherit = "payment.register"

    _description = "Purchase Payment Register Line"

    purchase_order_id = fields.Many2one(
        "purchase.order", index=True, required=True, readonly=True
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),  # 草稿
            ("waiting", "Waiting"),  # 待财务付款
            ("reconciled", "Reconciled"),  # 已付款
            ("reject", "Reject"),  # 已驳回
            ("return", "return"),  # 已退票
            ("cancelled", "Cancelled"),  # 已取消
        ],
        readonly=True,
        default="draft",
        copy=False,
        string="Status",
    )

    reject_by = fields.Many2one(
        "res.users", string="Reject by", readonly=True, tracking=True
    )
    reject_date = fields.Date(
        string="Reject Date", index=True, readonly=True, tracking=True
    )
    reject_reason = fields.Text(string="Reject reason", tracking=True)
    confirm_by = fields.Many2one(
        "res.users", string="Confirm by", readonly=True, tracking=True
    )
    confirm_date = fields.Date(
        string="Confirm Date", index=True, readonly=True, tracking=True
    )

    return_by = fields.Many2one(
        "res.users", string="Return by", readonly=True, tracking=True
    )
    return_date = fields.Date(
        string="Return Date", index=True, readonly=True, tracking=True
    )

    def name_get(self):
        return [(x.id, x.name or _("Draft Payment Register")) for x in self]

    @api.model
    def default_get(self, default_fields):
        rec = super().default_get(default_fields)
        active_ids = self._context.get("active_ids") or self._context.get("active_id")
        active_model = self._context.get("active_model")

        if not active_ids or active_model != "purchase.order":
            return rec

        purchase_order = self.env["purchase.order"].browse(active_ids[0])
        journal_id = self.env["account.journal"].search(
            [("type", "in", ("bank", "cash"))], limit=1
        )
        payment_method_ids = journal_id.inbound_payment_method_ids.ids

        default_payment_method_id = self.env.context.get("default_payment_method_id")
        if default_payment_method_id:
            payment_method_ids.append(default_payment_method_id)

        rec["payment_type"] = "outbound"
        rec["partner_type"] = "supplier"
        rec["journal_id"] = journal_id.id
        rec["purchase_order_id"] = purchase_order.id
        rec["payment_method_id"] = payment_method_ids and payment_method_ids[0] or False
        rec["partner_id"] = purchase_order.partner_id.id
        return rec

    def post(self):
        for rec in self:

            if not rec.name:
                if rec.payment_type == "inbound":
                    seq_code = "purchase.payment.register.refund"
                elif rec.payment_type == "outbound":
                    seq_code = "purchase.payment.register.invoice"
                elif rec.payment_type == "transfer":
                    seq_code = "purchase.payment.register.transfer"
                rec.name = self.env["ir.sequence"].next_by_code(seq_code)

        self.filtered(lambda x: x.state == "draft").write(
            {
                "state": "waiting",
                "confirm_by": self.env.user.id,
                "confirm_date": fields.Date.today(),
            }
        )

    def action_return(self):
        recs = self.filtered(lambda x: x.state in ("waiting", "reconciled", "reject"))
        recs.write(
            {
                "state": "return",
                "return_by": self.env.user.id,
                "return_date": fields.Date.today(),
            }
        )

    def action_reject(self):
        recs = self.filtered(lambda x: x.state in ("waiting", "return"))
        recs.write(
            {
                "state": "reject",
                "reject_by": self.env.user.id,
                "reject_date": fields.Date.today(),
            }
        )
