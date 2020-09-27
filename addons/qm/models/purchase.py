from odoo import api, fields, models
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
