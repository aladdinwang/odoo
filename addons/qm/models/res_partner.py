# 继承res.partner
from odoo import api, fields, models, tools, _


class Partner(models.Model):
    _inherit = "res.partner"

    account_address = fields.Char("Account Street")
    account_phone = fields.Char("Account Phone")
    account_name = fields.Char("Account Name")
