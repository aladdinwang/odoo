from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    sale_order_ids = fields.Many2many("sale.order", string="Sale Orders")
