from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    code = fields.Selection(selection_add=[("dropship", "DropShip")])
