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
    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        readonly=True,
        states={"draft": [("readonly", False)], "sent": [("readonly", False)]},
        required=True,
        change_default=True,
        index=True,
        tracking=1,
        domain="[('company_type', '=', 'company'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
