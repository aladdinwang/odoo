from odoo import api, fields, models, _


class ResPartnerBank(models.Model):
    _inherit = "res.partner.bank"

    tax_number = fields.Char("Tax Number")
    company_name = fields.Char("Company Name")
