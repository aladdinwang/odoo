# 继承res.partner
from odoo import api, fields, models, tools, _


class Partner(models.Model):
    _inherit = "res.partner"

    account_address = fields.Char("Account Street")
    account_phone = fields.Char("Account Phone")
    account_name = fields.Char("Account Name")

    supplier_type = fields.Selection(
        string="Supplier Type",
        selection=[("agent", "Agent"), ("dealer", "Dealer"), ("producer", "Producer")],
    )
    customer_type = fields.Selection(
        string="Customer Type",
        selection=[
            ("person", "Person"),
            ("dealer", "Dealer"),
            ("platform", "Platform"),
            ("endpoint", "Endpoint"),
        ],
    )

    @api.model
    def default_get(self, default_fields):
        values = super().default_get(default_fields)
        print(default_fields)
        if "country_id" in default_fields:
            values["country_id"] = (
                self.env["res.country"].search([("code", "=", "CN")], limit=1).id
            )
        return values
