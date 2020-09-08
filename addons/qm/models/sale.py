from odoo import api, fields, models, SUPERUSER_ID, _


class SaleOrder(models.Model):
    _inherit = "sale.order"

    outer_name = fields.Char(string="Outer Order Reference")

    invoice_state = fields.Selection(
        [
            ("pending", "Pending"),
            ("to_invoice", "To Invoice"),
            ("invoiced", "Invoiced"),
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
        domain="['&', ('company_type', '=', 'company'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )

    @api.depends("invoice_ids.state")
    def _compute_invoice_state(self):
        unconfirmed_orders = self.filtered(lambda so: so.state not in ["sale", "done"])
        unconfirmed_orders.invoice_state = "pending"
        confirmed_orders = self - unconfirmed_orders

        if not confirmed_orders:
            return

        for order in confirmed_orders:
            invoice_state_all = [invoice.state for invoice in order.invoice_ids]
            if invoice_state_all and all(
                state == "to_invoice" for state in invoice_state_all
            ):
                order.invoice_state = "to_invoice"
            elif invoice_state_all and all(
                state in ("invoiced", "sent", "received") for state in invoice_state_all
            ):
                order.invoice_state = "invoiced"
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
