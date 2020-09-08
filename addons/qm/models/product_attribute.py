from odoo import fields, models, api


class ProductTemplateAttributeValue(models.Model):
    _inherit = "product.template.attribute.value"

    def _is_from_single_value_line(self, only_active=True):
        return False
