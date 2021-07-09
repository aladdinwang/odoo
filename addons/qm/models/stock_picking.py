from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    code = fields.Selection(selection_add=[("dropship", "DropShip")])


class StockMove(models.Model):
    _inherit = "stock.move"

    sale_rma_return_line_id = fields.Many2one(
        "sale.rma.return_line",
        "Sale RMA Return Line",
        ondelete="set null",
        index=True,
        readonly=True,
    )
    sale_rma_exchange_line_id = fields.Many2one(
        "sale.rma.exchange_line",
        "Sale RMA Exchange Line",
        ondelete="set null",
        index=True,
        readonly=True,
    )
