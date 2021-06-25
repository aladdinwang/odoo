# coding: utf-8
from odoo import fields, models, api, _
from oddo.exceptions import UserError


class Rma(models.Model):
    _name = 'sale.rma'
    _inherit = ["portal.mixin", "mail.thread", "mail.activity.mixin"]
    _description = "Sale Rma"
    _order = "create_date desc, name desc, id desc"


    name = fields.Char(
        states={'draft': [('readonly', False)]},
        index=True,
        default=lambda self: _('New')
    )
    type = fields.Selection([('return', u'退货'), ('exchange', 'Exchange')])
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', index=True, required=True)
