from odoo import api, models, _, fields
from odoo.exceptions import UserError


class Order(models.Model):
    _name = "hoaya.order"
    _inherit = ["mail.thread", "mail.activity.mixin", "portal.mixin"]
    _description = "Hoaya Order"
    _order = "id desc"

    def _get_default_platform_currency_id(self):
        currency = self.env["res.currency"].search([("name", "=", "USD")], limit=1)
        return currency.id

    def _get_default_logistics_currency_id(self):
        currency = self.env["res.currency"].search([("name", "=", "CNY")], limit=1)
        return currency.id

    name = fields.Char(
        states={"draft": [("readonly", False)]},
        index=True,
        default=lambda self: _("New"),
    )
    brand = fields.Char(index=True)
    date_order = fields.Datetime(states={"draft": [("readonly", False)]}, index=True)

    platform_currency_id = fields.Many2one(
        "res.currency", "Currency", default=_get_default_platform_currency_id
    )
    logistics_currency_id = fields.Many2one(
        "res.currency", "Currency", default=_get_default_logistics_currency_id
    )

    amount_total = fields.Monetary(
        "Amount Total", currency_field="platform_currency_id"
    )
    amount_tax = fields.Monetary("Amount Tax", currency_field="platform_currency_id")
    amount_payment = fields.Monetary(
        "Amount Payment", currency_field="platform_currency_id"
    )

    order_reference = fields.Char()
    tracking_number = fields.Char("Tracking Number", index=True)
    courier_tracking_number = fields.Char("Courier Tracking Number", index=True)

    # 挂号费
    register_fee = fields.Monetary(
        "Register Fee", currency_field="logistics_currency_id"
    )
    # 运费
    shipping_cost = fields.Monetary(
        "Shipping Cost", currency_field="logistics_currency_id"
    )
    total_shipping_cost = fields.Monetary(
        "Total Shipping Cost", currency_field="logistics_currency_id"
    )
    weight = fields.Float("Weight")
    volume_weight = fields.Float("Volume Weight")
    cost_weight = fields.Float("Cost Weight")
    time_online = fields.Datetime("Time Online")
    state = fields.Selection(
        [("draft", "Draft"), ("waiting", "Waiting"), ("done", "Done")],
        readonly=True,
        default="draft",
        copy=False,
        index=True,
        string="Status",
    )

    @api.model
    def load(self, fields, data):
        result = super().load(fields, data)
        records = self.browse(result["ids"])

        for record in records:
            print(record.get_external_id())

        return result
