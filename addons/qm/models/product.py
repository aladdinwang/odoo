from odoo import fields, models, api


class ProductCategory(models.Model):
    _inherit = "product.category"

    code = fields.Char("Reference")
    complete_code = fields.Char(
        "Complete Code", compute="_compute_complete_code", store=True
    )
    tax_classification_id = fields.Many2one("tax.classification", "Tax Classification")

    @api.depends("code", "parent_id.complete_code")
    def _compute_complete_code(self):
        for category in self:
            if category.parent_id:
                category.complete_code = "".join(
                    filter(None, [category.parent_id.complete_code, category.code])
                )
            else:
                category.complete_code = category.code


class ProductProduct(models.Model):
    _inherit = "product.product"

    default_code = fields.Char(
        "Internal Reference", compute="_compute_default_code", store=True, index=True
    )

    @api.depends("product_tmpl_id.categ_id")
    def _compute_default_code(self):
        for product in self:
            if product.product_tmpl_id.categ_id:
                product.default_code = "".join(
                    filter(
                        None,
                        [
                            product.product_tmpl_id.categ_id.complete_code,
                            self.env["ir.sequence"].next_by_code("product.product"),
                        ],
                    )
                )
                print(product.default_code)
