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

    name = fields.Char(
        states={"draft": [("readonly", False)]},
        index=True,
        default=lambda self: _("New"),
    )
    type = fields.Selection([("return", "Return"), ("exchange", "Exchange")])
    sale_order_id = fields.Many2one(
        "sale.order", string="Sale Order", index=True, required=True
    )
    partner_id = fields.Many2one(
        "sale.order", related="sale_order_id.partner_id", index=True, store=True
    )
    is_dropshipping = fields.Boolean(related="sale_order_id.is_dropshipping")

    return_line_ids = fields.One2many("sale.rma.return_line", "rma_id")
    return_amount = fields.Monetary("Return Amount")
    exchange_amount = fields.Monetary("Exchange Amount")
    exchange_line_ids = fields.One2many("sale.rma.exchange_line", "rma_id")
    exchange_diff = fields.Monetary("Exchange diff")
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
    )

    currency_id = fields.Many2one(
        "res.currency", default=_get_default_currency_id, required=True
    )


class RmaReturnLine(models.Model):
    _name = "sale.rma.return_line"
    _inherit = ["portal.mixin", "mail.thread", "mail.activity.mixin"]
    _description = "Sale Rma Return Line"
    _order = "create_date desc, name desc, id desc"

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
        compute="_compute_amount", string="Subtotal", readonly=True, store=True
    )
    product_qty = fields.Float(
        string="Quantity", digits="Product Unit Of Measure", required=True, default=1.0
    )
    product_uom = fields.Many2one(
        "uom.uom",
        string="Unit of Measure",
        domain="[('category_id', '=', product_uom_category_id)]",
    )
    currency_id = fields.Many2one("res.currency", related="rma_id.currency_id")


class RmaExchangeLine(models.Model):
    _name = "sale.rma.exchange_line"
    _inherit = ["portal.mixin", "mail.thread", "mail.activity.mixin"]
    _description = "Sale Rma Exchange Line"
    _order = "create_date desc, name desc, id desc"

    rma_id = fields.Many2one("sale.rma", index=True)
    product_id = fields.Many2one("product.product", index=True)
    product_uom_category_id = fields.Many2one(
        "uom.category", compute="_compute_product_uom_category_id"
    )
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
        compute="_compute_amount", string="Subtotal", readonly=True, store=True
    )
    currency_id = fields.Many2one("res.currency", related="ram_id.currency_id")
