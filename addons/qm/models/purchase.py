from odoo import api, fields, models, _
from odoo.tools import float_compare


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    READONLY_STATES = {
        "purchase": [("readonly", True)],
        "done": [("readonly", True)],
        "cancel": [("readonly", True)],
    }

    sale_order_ids = fields.Many2many("sale.order", string="Sale Orders")
    partner_id = fields.Many2one(
        "res.partner",
        string="Vendor",
        required=True,
        states=READONLY_STATES,
        change_default=True,
        tracking=True,
        domain="[('is_company', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="You can find a vendor by its Name, TIN, Email or Internal Reference.",
    )

    payment_state = fields.Selection(
        selection=[
            ("not_paid", "Not Paid"),
            ("in_payment", "In Payment"),
            ("paid", "Paid"),
        ],
        string="Payment",
        default="not_paid",
        store=True,
        readonly=True,
        copy=False,
        tracking=True,
        compute="_compute_payment_state",
        index=True,
    )

    @api.depends("invoice_ids", "invoice_ids.state", "invoice_ids.amount_residual")
    def _compute_payment_state(self):
        for order in self:
            paid_amount = 0.0
            invoices = self.invoice_ids.filtered(lambda x: x.state == "posted")
            for invoice in invoices:
                paid_amount += invoice.amount_total - invoice.amount_residual
            if (
                float_compare(paid_amount, order.amount_total, precision_rounding=0.01)
                == 0
            ):
                order.payment_state = "paid"
            elif float_compare(paid_amount, 0, precision_rounding=0.01) > 0:
                order.payment_state = "in_payment"
            else:
                order.payment_state = "not_paid"


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    request_id = fields.Many2one(
        "purchase.request", string="Purchase Request", index=True
    )


class PurchaseRequest(models.Model):
    """
    sku需求池
    """

    _name = "purchase.request"
    _inherit = ["mail.thread", "mail.activity.mixin", "portal.mixin"]
    _description = "Purchase Request"
    _order = "id desc"

    @api.depends("sale_line_id")
    def _compute_partner_id_domain(self):
        for rec in self:
            rec.partner_ids = [
                (6, 0, rec.mapped("product_id.product_tmpl_id.seller_ids.name").ids)
            ]

    name = fields.Char(
        states={"draft": [("readonly", False)]},
        index=True,
        default=lambda self: _("New"),
    )
    sale_line_id = fields.Many2one(
        "sale.order.line", string="Sale Order Line", index=True, requried=True
    )
    sale_order_id = fields.Many2one(
        "sale.order", related="sale_line_id.order_id", index=True, readonly=True
    )
    customer_id = fields.Many2one(
        "res.partner", related="sale_order_id.partner_id", readonly=True, store=True
    )
    delivery_type = fields.Selection(
        related="sale_order_id.delivery_type", readonly=True
    )
    purchase_line_ids = fields.One2many(
        "purchase.order.line", "request_id", string="Purchase Lines"
    )
    purchase_line_count = fields.Integer(
        string="Purchase Line Count", compute="_compute_purchase_line", readonly=True
    )
    product_id = fields.Many2one(
        "product.product", related="sale_line_id.product_id", readonly=True, index=True
    )
    product_uom_qty = fields.Float(
        string="Quantity",
        digits="Product Unit of Measure",
        related="sale_line_id.product_uom_qty",
        readonly=True,
        tracking=True,
    )
    product_uom = fields.Many2one(
        "uom.uom", related="sale_line_id.product_uom", readonly=True
    )
    qty_purchased = fields.Float(
        "Purchased Qty", compute="_compute_purchase_line", readonly=True, tracking=True
    )
    qty_to_purchase = fields.Float(
        "To Purchase Qty", compute="_compute_purchase_line", index=True, tracking=True
    )
    state = fields.Selection(
        selection=[("open", "In progress"), ("done", "Done"), ("cancel", "Cancelled")],
        string="Status",
        copy=False,
        default="open",
        readonly=True,
    )
    partner_ids = fields.Many2many("res.partner", compute=_compute_partner_id_domain)
    partner_id = fields.Many2one(
        "res.partner", "Partner", domain="[('id', 'in', partner_ids)]"
    )

    @api.model
    def create(self, vals):
        if vals.get("name", _("New")) == _("New"):
            vals["name"] = self.env["ir.sequence"].next_by_code(
                "purchase.request"
            ) or _("New")
        result = super().create(vals)
        return result

    @api.depends("purchase_line_ids")
    def _compute_purchase_line(self):
        for rec in self:
            line_ids = rec.purchase_line_ids.filtered(lambda x: x.state != "cancel")
            rec.purchase_line_count = len(line_ids)
            qty_purchased = sum(x.product_qty for x in line_ids)
            rec.qty_purchased = qty_purchased
            rec.qty_to_purchase = rec.product_uom_qty - qty_purchased

    def action_view_purchase_line(self):
        purchase_line_ids = self.mapped("purchase_line_ids")
        action = self.env.ref("action_purchase_order_line").read()[0]
        if len(purchase_line_ids) <= 0:
            action = {"type": "ir.actions.act_window_close"}
        action["context"] = {"default_user_id": self.user_id.id}
        return action

    @api.onchange("sale_line_id")
    def _onchange_sale_line_id(self):
        for rec in self:
            rec.partner_id = False

        return {
            "domain": {
                "partner_id": [
                    (
                        "id",
                        "in",
                        self.mapped("product_id.product_tmpl_id.seller_ids.name").ids,
                    )
                ]
            }
        }
