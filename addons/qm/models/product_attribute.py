from odoo import fields, models, api


class ProductAttribute(models.Model):
    _inherit = "product.attribute"

    comment = fields.Char("Additional Information")

    def name_get(self):
        self.browse(self.ids).read(["comment"])
        return [
            (
                attr.id,
                "%s%s" % (attr.name, attr.comment and " [%s]" % attr.comment or ""),
            )
            for attr in self
        ]


class ProductTemplateAttributeValue(models.Model):
    _inherit = "product.template.attribute.value"

    def _is_from_single_value_line(self, only_active=True):
        return False
