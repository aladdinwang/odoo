from odoo import api, fields, models, SUPERUSER_ID, _
from odoo.tools import float_compare


class SaleOrder(models.Model):
    _inherit = "sale.order"

    outer_name = fields.Char(string="Outer Order Reference")

    invoice_state = fields.Selection(
        [
            ("pending", "Pending"),
            ("to_invoice", "To Invoice"),
            ("invoiced", "Invoiced"),
            ("sent", "Sent"),
            ("received", "Received"),
            ("returned", "Returned"),
        ],
        string="Invoice State",
        default="pending",
        compute="_compute_invoice_state",
        store=True,
        readonly=True,
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        readonly=True,
        states={"draft": [("readonly", False)], "sent": [("readonly", False)]},
        required=True,
        change_default=True,
        index=True,
        tracking=1,
        domain="[('is_company', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
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

    delivery_type = fields.Selection(
        selection=[("warehouse", "Warehouse"), ("dropship", "Dropship")],
        string="Delivery Type",
        default="warehouse",
        tracking=True,
    )

    @api.depends("invoice_ids.state")
    def _compute_invoice_state(self):
        unconfirmed_orders = self.filtered(lambda so: so.state not in ["sale", "done"])
        unconfirmed_orders.invoice_state = "pending"
        confirmed_orders = self - unconfirmed_orders

        if not confirmed_orders:
            return

        _sale_order_invoice_states = {
            "to_invoice",
            "invoiced",
            "sent",
            "received",
            "returned",
        }

        for order in confirmed_orders:
            invoice_states = set(
                [
                    invoice.state
                    for invoice in order.invoice_ids
                    if invoice.state not in ["draft", "cancel"]
                ]
            )
            if any(state == "posted" for state in invoice_states):
                order.invoice_state = "pending"
            elif (
                len(invoice_states) == 1 and invoice_states & _sale_order_invoice_states
            ):
                order.invoice_state = list(invoice_states)[0]
            else:
                # use the last one state
                last_invoice = max(order.invoice_ids, default=None, key=lambda x: x.id)
                if last_invoice and last_invoice.state in _sale_order_invoice_states:
                    order.invoice_state = last_invoice.state
                else:
                    order.invoice_state = "pending"

    def action_to_invoice(self):
        sale_orders = self.filtered(
            lambda o: o.state in ["sale", "posted"] and o.invoice_state == "pending"
        )
        for order in sale_orders:
            new_invoice_ids = []
            for move in order.invoice_ids:
                if move.state == "posted":
                    new_invoice_ids.append((1, move.id, {"state": "to_invoice"}))
            order.write({"invoice_ids": new_invoice_ids})

    def _prepare_invoice(self):
        invoice_vals = super()._prepare_invoice()
        invoice_vals["partner_id"] = self.partner_id.id
        return invoice_vals

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
