from odoo import fields, models, api, _
from odoo.exceptions import UserError


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
    posted_date = fields.Date(string="Posted Date", index=True, readonly=True)
    # 开具人
    posted_by = fields.Many2one("res.users", string="Posted by", readonly=True)

    cancel_date = fields.Date(string="Cancel Date", index=True, readonly=True)
    cancel_by = fields.Many2one("res.users", string="Cancel by", readonly=True)

    reject_reason = fields.Text("Reject Reason", readonly=True)
    reject_date = fields.Date(string="Reject Date", index=True, readonly=True)
    reject_by = fields.Many2one("res.users", string="Reject by", readonly=True)

    approved_by = fields.Many2one("res.users", string="Approved by", readonly=True)
    approved_date = fields.Date(string="Approved Date", index=True, readonly=True)

    verified_by = fields.Many2one("res.users", string="Verified by", readonly=True)
    verified_date = fields.Date(string="Verified Date", index=True, readonly=True)

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
    # partner_id computed自动计算
    # 检查是不是同一个partner的采购单明细
    partner_id = fields.Many2one("res.partner", readonly=True, index=True)
    # compute类型的partner_order_ids
    purchase_order_ids = fields.Many2many(
        "purchase.order",
        compute="_compute_purchase_order",
        string="Purchase Orders",
        copy=False,
    )

    # 明细
    line_ids = fields.One2many(
        "account.purchase.invoice.line", "invoice_id", string="Lines", readonly=True
    )

    def default_get(self, default_fields):
        rec = super().default_get(default_fields)
        active_ids = self._context.get("active_ids") or self._context.get("active_id")
        active_model = self._context.get("active_model")

        if not active_ids or active_model != "account.purchase.invoice":
            return rec

        purchase_lines = (
            self.env["purchase.order.line"]
            .browse(active_ids)
            .filtered(lambda x: x.state not in ("draft", "cancel"))
        )
        if not purchase_lines:
            raise UserError(_("You can only select valid order lines"))

        last_line = None
        new_lines = []
        for line in purchase_lines:
            if last_line and last_line.partner_id != line.partner_id:
                raise UserError(_("Only one partner at most"))
            last_line = line

            new_lines.append(
                (0, 0, {"purchase_line_id": line.id, "product_qty": line.product_qty})
            )

        new_vals = {"partner_id": last_line.partner_id.id, "line_ids": new_lines}
        rec.update(new_vals)
        return rec

    @api.depends("line_ids.purchase_line_id")
    def _compute_purchase_order(self):
        for rec in self:
            purchase_orders = rec.mapped("line_ids.purchase_line_id.order_id")
            rec.purchase_order_ids = purchase_orders

    def action_draft(self):
        ...

    def post(self):
        ...

    def action_cancel(self):
        ...

    def action_reject(self):
        ...

    def action_approve(self):
        ...

    def action_verify(self):
        ...

    def action_create_purchase_invoice(self):
        active_ids = self.env.context.get("active_ids")
        if not active_ids:
            return ""

        return {
            "name": _("Create Purchase Invoice"),
            "res_model": "account.purchase.invoice",
            "view_mode": "form",
            "view_id": self.env.ref("qm.view_account_purchase_invoice_form_qm"),
            "context": self.env.context,
            "target": "new",
            "type": "ir.actions.act_window",
        }


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
