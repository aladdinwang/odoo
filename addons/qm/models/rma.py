# coding: utf-8
from odoo import fields, models, api, _
from odoo.exceptions import UserError


class Rma(models.Model):
    _name = "sale.rma"
    _inherit = ["portal.mixin", "mail.thread", "mail.activity.mixin"]
    _description = "Sale Rma"
    _order = "create_date desc, name desc, id desc"

    def _get_default_currency_id(self):
        return self.env.company.currency_id.id

    @api.depends("return_line_ids.price_total", "exchange_line_ids.price_total")
    def _compute_amount(self):
        for rec in self:
            rec.return_amount = 0
            rec.exchange_amount = 0

            rec.exchange_diff = rec.return_amount - rec.exchange_amount

    name = fields.Char(
        states={"draft": [("readonly", False)]},
        index=True,
        default=lambda self: _("New"),
    )
    type = fields.Selection(
        [("return", "Return"), ("exchange", "Exchange")], default="return"
    )
    sale_order_id = fields.Many2one(
        "sale.order", string="Sale Order", index=True, required=True, readonly=True
    )
    partner_id = fields.Many2one(
        "res.partner", related="sale_order_id.partner_id", index=True, store=True
    )
    is_dropshipping = fields.Boolean(related="sale_order_id.is_dropshipping")

    return_line_ids = fields.One2many("sale.rma.return_line", "rma_id")
    return_amount = fields.Monetary("Return Amount", compute="_compute_amount")
    exchange_amount = fields.Monetary("Exchange Amount", compute="_compute_amount")
    exchange_line_ids = fields.One2many("sale.rma.exchange_line", "rma_id")
    exchange_diff = fields.Monetary("Exchange diff", compute="_compute_amount")
    # 备注
    comment = fields.Text("Comment")

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("posted", "Posted"),
            ("done", "Done"),
            ("cancel", "Cancel"),
        ],
        string="Status",
        tracking=True,
        default="draft",
    )

    currency_id = fields.Many2one(
        "res.currency", default=_get_default_currency_id, required=True
    )

    @api.model
    def default_get(self, default_fields):
        rec = super().default_get(default_fields)
        active_id = self._context.get("active_id")
        active_model = self._context.get("active_model")
        if not active_id or active_model != "sale.order":
            return rec

        sale_order = (
            self.env["sale.order"]
            .browse(active_id)
            .filtered(lambda x: x.state not in ["cancel", "draft"])
        )
        if not sale_order:
            raise UserError("Not Valid Order!")

        rma = {"sale_order_id": sale_order.id, "type": "return"}

        return_lines = []
        for line in sale_order.order_line:
            return_lines.append(
                (
                    0,
                    0,
                    {
                        "sale_line_id": line.id,
                        "price_unit": line.price_unit,
                        "product_uom": line.product_uom.id,
                        "product_qty": line.product_uom_qty,
                    },
                )
            )

        rma["return_line_ids"] = return_lines
        rec.update(rma)
        return rec


class RmaReturnLine(models.Model):
    _name = "sale.rma.return_line"
    _inherit = ["portal.mixin", "mail.thread", "mail.activity.mixin"]
    _description = "Sale Rma Return Line"
    _order = "id desc"

    @api.depends("product_qty", "price_unit", "tax_id")
    def _compute_amount(self):
        for line in self:
            taxes = line.tax_id.compute_all(
                line.price_unit,
                line.rma_id.currency_id,
                line.product_qty,
                partner=line.rma_id.sale_order_id.partner_shipping_id,
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

    rma_id = fields.Many2one("sale.rma", index=True)
    sale_line_id = fields.Many2one("sale.order.line", required=True)
    product_id = fields.Many2one(
        "product.product", related="sale_line_id.product_id", index=True, store=True
    )
    product_uom_category_id = fields.Many2one(
        related="sale_line_id.product_id.uom_id.category_id", readonly=True
    )
    price_unit = fields.Float(
        "Unit Price", required=True, digit="Product Price", default=0.0
    )
    price_subtotal = fields.Monetary(
        compute="_compute_amount", string="Subtotal", store=True
    )
    price_total = fields.Monetary(compute="_compute_amount", string="Total", store=True)
    product_qty = fields.Float(
        string="Quantity", digits="Product Unit Of Measure", required=True, default=1.0
    )
    product_uom = fields.Many2one(
        "uom.uom",
        string="Unit of Measure",
        domain="[('category_id', '=', product_uom_category_id)]",
    )
    currency_id = fields.Many2one("res.currency", related="rma_id.currency_id")
    tax_id = fields.Many2many(related="sale_line_id.tax_id")


class RmaExchangeLine(models.Model):
    _name = "sale.rma.exchange_line"
    _inherit = ["portal.mixin", "mail.thread", "mail.activity.mixin"]
    _description = "Sale Rma Exchange Line"
    _order = "id desc"

    @api.depends("product_qty", "price_unit", "tax_id")
    def _compute_amount(self):
        for line in self:
            taxes = line.tax_id.compute_all(
                line.price_unit,
                line.rma_id.currency_id,
                line.product_qty,
                partner=line.rma_id.sale_order_id.partner_shipping_id,
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

    rma_id = fields.Many2one("sale.rma", index=True)
    product_id = fields.Many2one("product.product", index=True)
    product_uom_category_id = fields.Many2one(related="product_id.uom_id.category_id")
    product_qty = fields.Float(
        string="Quantity", digits="Product Unit Of Measure", required=True, default=1.0
    )
    product_uom = fields.Many2one(
        "uom.uom",
        string="Unit of Measure",
        domain="[('category_id', '=', product_uom_category_id)]",
    )

    price_unit = fields.Float(
        "Unit Price", required=True, digit="Product Price", default=0.0
    )
    price_subtotal = fields.Monetary(
        compute="_compute_amount", string="Subtotal", store=True
    )

    price_total = fields.Monetary(compute="_compute_amount", string="Total", store=True)
    currency_id = fields.Many2one("res.currency", related="rma_id.currency_id")
    tax_id = fields.Many2many(
        "account.tax",
        string="Taxes",
        domain=["|", ("active", "=", False), ("active", "=", True)],
    )

    def _compute_tax_id(self):
        for line in self:
            fpos = (
                line.rma_id.sale_order_id.fiscal_position_id
                or line.sale_order_id.partner_id.property_account_position_id
            )
            taxes = line.product_id.taxes_id.filtered(
                lambda r: not line.company_id or r.company_id == line.company_id
            )
            line.tax_id = (
                fpos.map_tax(
                    taxes,
                    line.product_id,
                    line.rma_id.sale_order_id.partner_shipping_id,
                )
                if fpos
                else taxes
            )

    @api.onchange("product_id")
    def product_id_change(self):
        if not self.product_id:
            return

        self._compute_tax_id()
        return {}
