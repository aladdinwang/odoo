from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    code = fields.Char("Reference")
    tax_classification_id = fields.Many2one("tax.classification", "Tax Classification")
