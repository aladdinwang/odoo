from odoo import api, fields, models, _


class TaxClassification(models.Model):
    _name = "tax.classification"
    _description = "Tax Classification"

    name = fields.Char("Name", index=True, required=True)
    code = fields.Char("Code", index=True)
    code18 = fields.Char("Code18", index=True)
