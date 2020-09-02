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
    express_code = fields.Char(string="Express Reference", index=True)
    invoice_date = fields.Date(
        string="Invoice Date", index=True, default=fields.Date.today()
    )
    sent_date = fields.Date(string="Sent Date", index=True, default=fields.Date.today())

    state = fields.Selection(
        selection=[("done", "Done"), ("cancel", "Cancelled")],
        string="Status",
        required=True,
        index=True,
        tracking=True,
        default="done",
    )

    def action_done(self):
        self.write({"state": "done"})

    def action_cancel(self):
        self.write({"state": "cancel"})
