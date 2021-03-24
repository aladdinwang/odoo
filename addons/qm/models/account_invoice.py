from odoo import fields, models, api


class AccountInvoice(models.Model):
    _name = "account.invoice"
    _inherit = ["portal.mixin", "mail.thread", "mail.activity.mixin"]
    _description = "Account Invoice"
    _order = "create_date desc, name desc, id desc"

    @api.model
    def _get_default_currency(self):
        dummy, currency_id = self.env["ir.model.data"].get_object_reference(
            "base", "CNY"
        )
        return currency_id

    name = fields.Char(
        string="Invoice Reference", required=True, copy=False, index=True
    )
    code = fields.Char(string="Invoice Code", required=True, copy=False, index=True)
    type = fields.Selection(
        selection=[("normal", "Normal"), ("special", "Special")],
        string="Type",
        required=True,
        index=True,
        default="special",
    )
    currency_id = fields.Many2one(
        "res.currency",
        store=True,
        readonly=True,
        tracking=True,
        required=True,
        string="Currency",
        default=_get_default_currency,
    )
    amount_tax = fields.Monetary(string="Taxes", default=0.0)
    amount_untaxed = fields.Monetary(string="Untaxed Amount", default=0.0)
    amount_total = fields.Monetary(string="Total", default=0.0)
    courier = fields.Char(string="Courier")
    express_code = fields.Char(string="Express Reference", index=True)
    # 开具日期
    posted_date = fields.Date(string="Posted Date", index=True)
    # 开具人
    posted_by = fields.Many2one("res.users", string="Posted by")

    cancel_date = fields.Date(string="Cancel Date", index=True)
    cancel_by = fields.Many2one("res.users", string="Cancel by")
    cancel_reason = fields.Char("Cancel reason")

    writeoff_date = fields.Date(string="Writeoff Date", index=True)
    writeoff_name = fields.Char("Writeoff reference")
    writeoff_code = fields.Char("Writeoff code")
    writeoff_by = fields.Many2one("res.users", string="Writeoff by")

    sent_date = fields.Date(string="Sent Date", index=True)
    sent_type = fields.Selection(
        selection=[("express", "Express"), ("self_pickup", "Self Pickup")],
        string="Sent Type",
        tracking=True,
        default="express",
    )
    sent_by = fields.Many2one("res.users", string="Sent by")

    return_date = fields.Date("Return date", index=True)
    return_by = fields.Many2one("res.users", string="Return by")

    taken_date = fields.Date("Taken date")
    taken_by = fields.Char("Taken by")

    """
    draft, posted, cancel, writeoff, sent, taken, return
    """
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("posted", "Posted"),
            ("sent", "Sent"),
            ("return", "Return"),
            ("taken", "Taken"),
            ("cancel", "Cancelled"),
        ],
        string="Status",
        required=True,
        index=True,
        tracking=True,
        default="draft",
    )
    # Todo: 税率去掉
    tax_rate = fields.Selection(
        selection=[
            ("1%", "1%"),
            ("3%", "3%"),
            ("6%", "6%"),
            ("9%", "9%"),
            ("13%", "13%"),
        ],
        string="Tax Rate",
        default="13%",
    )

    def action_done(self):
        self.write({"state": "done"})

    def action_cancel(self):
        self.write({"state": "cancel"})


"""
# purchase.invoice
class SaleInvoice(models.Model):
    # 开票申请
    _name = "sale.invoice"
    _inherit = ["portal.mixin", "mail.thread", "mail.activity.mixin"]
    _description = "Customer Invoice"
    _order = "create_date desc, name desc, id desc"

    @api.model
    def _get_default_currency(self):
        dummy, currency_id = self.env["ir.model.data"].get_object_reference(
            "base", "CNY"
        )
        return currency_id

    name = fields.Char(
        string="Invoice Reference", required=True, copy=False, index=True
    )
    code = fields.Char(string="Invoice Code", required=True, copy=False, index=True)
    type = fields.Selection(
        selection=[("normal", "Normal"), ("special", "Special")],
        string="Type",
        required=True,
        index=True,
        default="special",
    )
    currency_id = fields.Many2one(
        "res.currency",
        store=True,
        readonly=True,
        tracking=True,
        required=True,
        string="Currency",
        default=_get_default_currency,
    )

    # create_date 申请日期
    reject_date = fields.Date(
        string="Reject Date", index=True, default=fields.Date.today()
    )  # 驳回人
    reject_by = fields.Many2one("res.users", string="Reject by")
    reject_reason = fields.Char("Reject Reason")
    cancel_date = fields.Date(
        string="Cancel Date", index=True, default=fields.Date.today()
    )  # 作废日期
    cancel_by = fields.Many2one("res.users", string="Cancelled by")
    cancel_reason = fields.Char(string="Cancel reason")

    approve_date = fields.Date(
        string="Approve Date", index=True, default=fields.Date.today()
    )  # 审核日期
    approve_by = fields.Many2one("res.users", string="Approved by")

    # draft, posted, cancel, reject, approved

    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("posted", "Posted"),
            ("approved", "Approved"),
            ("reject", "Reject"),
            ("cancel", "Cancelled"),
        ],
        string="Status",
        required=True,
        index=True,
        tracking=True,
        default="draft",
    )
    amount_tax = fields.Monetary(string="Taxes", default=0.0)
    amount_untaxed = fields.Monetary(string="Untaxed Amount", default=0.0)
    amount_total = fields.Monetary(string="Total", default=0.0)


class SaleInvoiceLine(models.Model):
    _name = "sale.invoice.line"
    _inherit = ["portal.mixin", "mail.thread", "mail.activity.mixin"]
    _description = "Sale Invoice Line"

    sale_line_id = fields.Many2one(
        "sale.order.line", "Original sale order line", readonly=True, required=True
    )
    tax_id = fields.Many2many(
        "account.tax", related="sale_line_id.tax_id", string="Taxes", readonly=True
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        related="sale_line_id.product_id",
        readonly=True,
    )
    price_unit = fields.Float(
        "Unit Price", related="sale_line_id.price_unit", readonly=True
    )
    price_subtotal = fields.Monetary(
        compute="_compute_amount", string="Subtotal", readonly=True, store=True
    )
    price_tax = fields.Float(
        compute="_compute_amount", string="Total Tax", readonly=True, store=True
    )
    price_total = fields.Float(
        compute="_compute_amount", string="Total", readonly=True, store=True
    )
    discount = fields.Float(
        string="Discount (%)", related="sale_line_id.discount", readonly=True
    )

    product_uom_qty = fields.Float(
        string="Quantity", digits="Product Unit of Measure", required=True, default=1.0
    )
    product_uom = fields.Many2one(
        "uom.uom",
        string="Unit of Measure",
        realted="sale_line_id.product_uom",
        readonly=True,
    )
"""
