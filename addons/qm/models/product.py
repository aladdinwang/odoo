from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = 'product.category'

    code = fields.Char('Reference')





