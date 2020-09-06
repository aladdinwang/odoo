from odoo import fields, models, api


class AccountMove(models.Model):
    _inherit = "account.move"

    payment_ids = fields.Many2many(
        "account.payment",
        "account_invoice_payment_rel",
        "invoice_id",
        "payment_id",
        string="Payments",
        copy=False,
        readonly=True,
    )
    payment_amount = fields.Monetary(compute="_compute_payment_amount", readonly=True)
    payment_difference = fields.Monetary(
        compute="_compute_payment_amount", readonly=True
    )
    state = fields.Selection(
        selection_add=[
            ("to_invoice", "To Invoice"),
            ("invoiced", "Invoiced"),
            ("sent", "Sent"),
            ("received", "Received"),
            ("returned", "Returned"),
        ]
    )

    state2 = fields.Selection(
        selection=[
            ("to_invoice", "To Invoice"),
            ("invoiced", "Invoiced"),
            ("sent", "Sent"),
            ("received", "Received"),
            ("returned", "Returned"),
        ],
        string="Status2",
        inverse="_set_state",
        required=True,
        copy=False,
        tracking=True,
        default="to_invoice",
    )

    invoice_ids = fields.Many2many(
        "account.invoice",
        "account_invoice_rel",
        "move_id",
        "invoice_id",
        string="Invoices",
        copy=False,
    )

    @api.depends("amount_total_signed", "payment_ids")
    def _compute_payment_amount(self):
        not_paid_moves = self.filtered(lambda m: m.invoice_payment_state == "not_paid")
        for move in self - not_paid_moves:
            payment_total = 0.0
            for p in move.payment_ids:
                payment_total += -p.amount if p.payment_type == "outbound" else p.amount
            move.payment_amount = payment_total
            move.payment_difference = move.amount_total_signed - payment_total
        not_paid_moves.payment_amount = 0
        not_paid_moves.payment_difference = 0

    def _set_state(self):
        for move in self:
            if move.state in ("to_invoice", "invoiced", "sent", "received", "returned"):
                move.write({"state": move.state2})

    def action_download_xlsx(self):
        return {
            "type": "ir.actions.act_url",
            "url": f'/qm/export/xlsx?model=account.move&ids={",".join([str(rec.id) for rec in self])}',
            "target": "self",
        }
