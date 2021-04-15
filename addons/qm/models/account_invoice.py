from odoo import fields, models, api


class AccountInvoice(models.Model):
    _name = "account.sale.invoice"
    _inherit = ["portal.mixin", "mail.thread", "mail.activity.mixin"]
    _description = "Account Sale Invoice"
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


class PurchaseInvoice(models.Model):
    _name = "account.purchase.invoice"
    _inherit = ["portal.mixin", "mail.thread", "mail.activity.mixin"]
    _description = "Purchase Invoice"

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
    # 开具日期
    posted_date = fields.Date(string="Posted Date", index=True)
    # 开具人
    posted_by = fields.Many2one("res.users", string="Posted by")

    cancel_date = fields.Date(string="Cancel Date", index=True)
    cancel_by = fields.Many2one("res.users", string="Cancel by")

    reject_reason = fields.Text("Reject Reason")
    reject_date = fields.Date(string="Reject Date", index=True)
    reject_by = fields.Many2one("res.users", string="Reject by")

    approved_by = fields.Many2one("res.users", string="Approved by")
    approved_date = fields.Date(string="Approved Date", index=True)

    verified_by = fields.Many2one("res.users", string="Verified by")
    verified_date = fields.Date(string="Verified Date", index=True)

    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("posted", "Posted"),  # 已录票
            ("cancelled", "Cancelled"),  # 已撤销
            ("reject", "Reject"),  # 已驳回
            ("approved", "Approved"),  # 已审核
            ("verified", "Verified"),  # 已认证
        ],
        string="Status",
        required=True,
        index=True,
        tracking=True,
        default="draft",
    )

    # partner_id computed自动计算


class PurchaseInvoiceLine(models.Model):
    _name = "account.purchase.invoice.line"
    _description = "Purchase Invoice line"

    @api.depends("product_qty", "price_unit", "taxes_id")
    def _compute_amount(self):
        for line in self:
            taxes = line.taxes_id.compute_all(
                line.price_unit,
                line.currency_id,
                line.product_qty,
                line.product_id,
                line.partner_id,
            )
            line.update(
                {
                    "price_tax": sum(
                        t.get("amount", 0.0) for t in taxes.get("taxes", [])
                    ),
                    "price_total": taxes["total_included"],
                    "price_subtotal": taxes["total_excluded"],
                }
            )

    @api.depends("product_uom", "product_qty", "product_id.uom_id")
    def _compute_product_uom_qty(self):
        for line in self:
            if line.product_id and line.product_id.uom_id != line.product_uom:
                line.product_uom_qty = line.product_uom._compute_quantity(
                    line.product_qty, line.product_id.uom_id
                )
            else:
                line.product_uom_qty = line.product_qty

    invoice_id = fields.Many2one("account.purchase.invoice", index=True, required=True)
    purchase_line_id = fields.Many2one(
        "purchase.order.line",
        "Original purchase order line",
        readonly=True,
        required=True,
    )
    taxes_id = fields.Many2many(
        "account.tax", related="purchase_line_id.taxes_id", readonly=True
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        related="purchase_line_id.product_id",
        readonly=True,
    )
    product_uom = fields.Many2one(
        "uom.uom",
        string="Unit of Measure",
        related="purchase_line_id.product_uom",
        readonly=True,
    )
    product_qty = fields.Float(
        string="Quantity", digits="Product Unit of Measure", required=True
    )
    product_uom_qty = fields.Float(
        string="Total Quantity", compute="_compute_product_uom_qty", store=True
    )
    price_unit = fields.Float(
        "Unit Price", related="purchase_line_id.price_unit", readonly=True
    )
    price_subtotal = fields.Monetary(
        compute="_compute_amount", string="Subtotal", store=True
    )
    price_total = fields.Monetary(compute="_compute_amount", string="Total", store=True)
    price_tax = fields.Float(compute="_compute_amount", string="Tax", store=True)
    currency_id = fields.Many2one(
        related="purchase_line_id.currency_id", store=True, readonly=True
    )
    partner_id = fields.Many2one(
        "res.partner", related="purchase_line_id.partner_id", readonly=True, store=True
    )
