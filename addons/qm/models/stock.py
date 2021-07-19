from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    code = fields.Selection(selection_add=[("dropship", "DropShip")])


class StockMove(models.Model):
    _inherit = "stock.move"

    sale_return_line_id = fields.Many2one(
        "sale.rma.return_line",
        "Sale Return Line",
        ondelete="set null",
        index=True,
        readonly=True,
    )


#    sale_rma_exchange_line_id = fields.Many2one(
#        "sale.rma.exchange_line",
#        "Sale RMA Exchange Line",
#        ondelete="set null",
#        index=True,
#        readonly=True,
#    )


class Picking(models.Model):
    _inherit = "stock.picking"

    express_code = fields.Char(string="Express Reference", index=True)
