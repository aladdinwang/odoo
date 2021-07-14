# coding: utf-8
import collections

from odoo import fields, models, api, _
from odoo.tools.float_utils import float_compare
from odoo.exceptions import UserError, ValidationError

from odoo.addons.purchase.models.purchase import PurchaseOrder as Purchase


class Rma(models.Model):
    _name = "sale.rma"
    _inherit = ["portal.mixin", "mail.thread", "mail.activity.mixin"]
    _description = "Sale Rma"
    _order = "create_date desc, name desc, id desc"

    def _get_default_currency_id(self):
        return self.env.company.currency_id.id

    @api.constrains("return_line_ids")
    def _check_duplicate_return_line_ids(self):
        c = collections.Counter(x.sale_line_id.id for x in self.return_line_ids)
        for line in reversed(self.return_line_ids):
            if c[line.sale_line_id.id] > 1:
                raise ValidationError(f"订单项 {line.sale_line_id.name} 重复了")

    @api.depends("return_line_ids.price_total", "exchange_line_ids.price_total")
    def _compute_amount(self):
        for rec in self:
            rec.return_amount = sum(rec.return_line_ids.mapped("price_total"), 0)
            rec.exchange_amount = sum(rec.exchange_line_ids.mapped("price_total"), 0)

            rec.exchange_diff = rec.return_amount - rec.exchange_amount

    name = fields.Char(
        states={"draft": [("readonly", False)]},
        index=True,
        default=lambda self: _("New"),
    )
    type = fields.Selection(
        [("return", "RMA Return"), ("exchange", "Exchange")], default="return"
    )
    sale_order_id = fields.Many2one(
        "sale.order", string="Sale Order", index=True, required=True, readonly=True
    )
    partner_id = fields.Many2one(
        "res.partner", related="sale_order_id.partner_id", index=True, store=True
    )
    is_dropshipping = fields.Boolean(related="sale_order_id.is_dropshipping")

    return_line_ids = fields.One2many("sale.rma.return_line", "rma_id")
    return_amount = fields.Monetary("Return Amount", compute="_compute_amount")
    exchange_amount = fields.Monetary("Exchange Amount", compute="_compute_amount")
    exchange_line_ids = fields.One2many("sale.rma.exchange_line", "rma_id")
    exchange_diff = fields.Monetary("Exchange diff", compute="_compute_amount")
    # 备注
    comment = fields.Text("Comment")

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("posted", "Posted"),
            ("done", "Done"),
            ("cancel", "Cancel"),
        ],
        string="Status",
        tracking=True,
        default="draft",
    )

    currency_id = fields.Many2one(
        "res.currency", default=_get_default_currency_id, required=True
    )

    company_id = fields.Many2one(
        "res.company",
        "Company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )

    return_picking_ids = fields.Many2many(
        "stock.picking",
        compute="_compute_return_picking",
        string="Return Pickings",
        copy=False,
        store=True,
    )
    return_picking_count = fields.Integer(
        compute="_compute_return_picking",
        string="Return Picking Count",
        default=0,
        store=True,
    )
    return_picking_type_id = fields.Many2one(
        "stock.picking.type", compute="_compute_return_picking_type"
    )

    # return_shipping_id 退货地址
    # exchange_shipping_id 发货地址
    # 添加help
    return_shipping_id = fields.Many2one(
        "res.partner",
        string="Return Address",
        required=True,
        readonly=True,
        states={"draft": [("readonly", False)]},
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="接收退货商品的地址",
    )

    #    exchange_shipping_id = fields.Many2one(
    #        'res.partner',
    #        string='Exchange Address',
    #        required=True,
    #        readonly=True,
    #        states={
    #            'draft': [('readonly', False)]
    #        },
    #        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    #        help='发出换货产品的地址'
    #    )

    @api.depends(
        "return_line_ids.move_ids.picking_id",
        "return_line_ids.move_ids.state",
        "return_line_ids.move_ids.returned_move_ids",
    )
    def _compute_return_picking(self):
        for rma in self:
            pickings = self.env["stock.picking"]
            for return_line in rma.return_line_ids:
                moves = return_line.move_ids | return_line.move_ids.mapped(
                    "returned_move_ids"
                )
                pickings |= moves.mapped("picking_id")

            rma.return_picking_ids = pickings
            rma.picking_count = len(pickings)

    @api.model
    def _get_incoming_picking_type(self):
        picking_type = self.env["stock.picking.type"].search(
            [
                ("code", "=", "incoming"),
                ("warehouse_id.company_id", "=", self.env.company.id),
            ],
            limit=1,
        )
        return picking_type

    @api.model
    def _get_dropship_return_picking_type(self):
        picking_type = self.env["stock.picking.type"].search(
            [("sequence_code", "=", "DSR"), ("company_id", "=", self.env.company.id)],
            limit=1,
        )
        return picking_type

    @api.depends("return_shipping_id")
    def _compute_return_picking_type(self):
        for rma in self:
            if not rma.return_shipping_id:
                continue

            if (
                self.env.company.partner_id
                and self.env.company.partner_id == rma.return_shipping_id
            ):
                self.return_picking_type_id = self._get_incoming_picking_type()
            else:
                self.return_picking_type_id = self._get_dropship_return_picking_type()

    @api.model
    def default_get(self, default_fields):
        rec = super().default_get(default_fields)
        active_id = self._context.get("active_id")
        active_model = self._context.get("active_model")
        if not active_id or active_model != "sale.order":
            return rec

        sale_order = (
            self.env["sale.order"]
            .browse(active_id)
            .filtered(lambda x: x.state not in ["cancel", "draft"])
        )
        if not sale_order:
            raise UserError("Not Valid Order!")

        rma = {"sale_order_id": sale_order.id, "type": "return"}

        return_lines = []
        for line in sale_order.order_line:
            return_lines.append(
                (
                    0,
                    0,
                    {
                        "sale_line_id": line.id,
                        "product_uom": line.product_uom.id,
                        "product_qty": line.product_uom_qty,
                        "tax_id": [(6, 0, line.tax_id.ids)],
                        "product_id": line.product_id.id,
                        "price_unit": line.price_unit,
                        "price_subtotal": line.price_subtotal,
                    },
                )
            )

        rma["return_line_ids"] = return_lines
        rec.update(rma)
        return rec

    def post(self):
        self.write(
            {
                "state": "posted",
                "name": self.env["ir.sequence"].next_by_code("qm.sale.rma"),
            }
        )

        self._create_picking()

        # Todo: 根据rma生成新的销售订单

    def action_cancel(self):
        ...

    def action_done(self):
        ...

    def action_draft(self):
        ...

    @api.model
    def _prepare_return_picking(self):
        if not self.partner_id.property_stock_supplier.id:
            raise UserError(
                _("You must set a Vendor Location for this partner %s")
                % self.partner_id.name
            )

        return {
            "picking_type_id": self.return_picking_type_id.id,
            "partner_id": self.partner_id.id,
            "user_id": False,
            "date": self.create_date,
            "origin": self.name,
            "location_id": self.env.ref("stock.stock_location_customers").id,
            "location_dest_id": self.return_picking_type_id.default_location_dest_id.id,
            "company_id": self.company_id.id,
        }

    def _create_picking(self):
        StockPicking = self.env["stock.picking"]
        for rma in self:
            if any(
                [
                    ptype in ["product", "consu"]
                    for ptype in rma.return_line_ids.mapped("product_id.type")
                ]
            ):
                pickings = rma.return_picking_ids.filtered(
                    lambda x: x.state not in ("done", "cancel")
                )
                if not pickings:
                    res = rma._prepare_return_picking()
                    picking = StockPicking.create(res)
                else:
                    picking = pickings[0]
                moves = rma.return_line_ids._create_stock_moves(picking)
                moves = moves.filtered(
                    lambda x: x.state not in ("done", "cancel")
                )._action_confirm()
                seq = 0
                for move in sorted(moves, key=lambda move: move.date_expected):
                    seq += 5
                    move.sequence = seq
                moves._action_assign()
                picking.message_post_with_view(
                    "mail.message_origin_link",
                    values={"self": picking, "origin": order},
                    subtype_id=self.env.ref("mail.mt_note").id,
                )
        return True


class RmaReturnLine(models.Model):
    _name = "sale.rma.return_line"
    _inherit = ["portal.mixin", "mail.thread", "mail.activity.mixin"]
    _description = "Sale Rma Return Line"
    _order = "id desc"

    @api.depends("sale_line_id", "product_qty", "price_unit", "tax_id")
    def _compute_amount(self):
        for line in self:
            taxes = line.tax_id.compute_all(
                line.price_unit,
                line.rma_id.currency_id,
                line.product_qty,
                partner=line.rma_id.sale_order_id.partner_shipping_id,
            )
            line.update(
                {
                    "price_tax": sum(
                        t.get("amount", 0.0) for t in taxes.get("taxes", [])
                    ),
                    "price_total": taxes["total_included"],
                    "price_subtotal": taxes["total_excluded"],
                }
            )

    rma_id = fields.Many2one("sale.rma", index=True)
    sale_line_id = fields.Many2one("sale.order.line", required=True)
    product_id = fields.Many2one(
        "product.product", related="sale_line_id.product_id", index=True, store=True
    )
    product_uom_category_id = fields.Many2one(
        related="sale_line_id.product_id.uom_id.category_id", readonly=True
    )
    price_unit = fields.Float("Unit Price", required=True, digit="Product Price")
    price_subtotal = fields.Monetary(
        compute="_compute_amount", string="Subtotal", store=True
    )
    price_tax = fields.Monetary(compute="_compute_amount", string="Taxes", store=True)
    price_total = fields.Monetary(compute="_compute_amount", string="Total", store=True)
    product_qty = fields.Float(
        string="Quantity", digits="Product Unit Of Measure", required=True, default=1.0
    )
    product_uom = fields.Many2one(
        "uom.uom",
        string="Unit of Measure",
        domain="[('category_id', '=', product_uom_category_id)]",
    )
    currency_id = fields.Many2one("res.currency", related="rma_id.currency_id")
    tax_id = fields.Many2many(related="sale_line_id.tax_id")
    company_id = fields.Many2one(related="rma_id.company_id")
    move_ids = fields.One2many(
        "stock.move",
        "sale_return_line_id",
        string="Reservation",
        readonly=True,
        ondelete="set null",
        copy=False,
    )

    @api.onchange("sale_line_id")
    def _onchange_sale_line_id(self):
        if not self.sale_line_id:
            return
        self.product_uom = self.sale_line_id.product_uom
        self.price_unit = self.sale_line_id.price_unit
        self.product_qty = self.sale_line_id.product_uom_qty

    def _get_stock_move_price_unit(self):
        self.ensure_one()
        line = self[0]
        rma = line.rma_id
        price_unit = line.price_unit
        if line.tax_id:
            price_unit = line.tax_id.with_context(round=False).compute_all(
                price_unit,
                currency=line.rma_id.currency_id,
                quantity=1.0,
                product=line.product_id,
                partner=line.rma_id.partner_id,
            )["total_void"]
        if line.product_uom.id != line.product_id.uom_id.id:
            price_unit *= line.product_uom.factor / line.product_id.uom_id.factor
        if rma.currency_id != rma.company_id.currency_id:
            price_unit = rma.currency_id._convert(
                price_unit,
                rma.company_id.currency_id,
                self.company_id,
                self.create_date or fields.Date.today(),
                round=False,
            )
        return price_unit

    def _prepare_stock_moves(self, picking):
        self.ensure_one()
        res = []

        if self.product_id.type not in ["product", "consu"]:
            return res

        qty = 0.0
        price_unit = self._get_stock_move_price_unit()
        for move in self.move_ids.filtered(
            lambda x: x.state != "cancel" and not x.location_dest_id.usage == "supplier"
        ):
            qty += move.product_uom._compute_quantity(
                move.product_uom_qty, self.product_uom, rounding_method="HALF-UP"
            )

        template = {
            "name": (self.rma_id.name or "")[:2000],
            "product_id": self.product_id.id,
            "date": self.rma_id.create_date,
            "date_expected": False,
            "location_id": self.env.ref("stock.stock_location_customers").id,
            "location_dest_id": self.rma_id.return_picking_type_id.default_location_dest_id.id,
            "picking_id": picking.id,
            "partner_id": self.rma_id.partner_id.id,
            # "move_dest_ids": [(4, x) for x in self.move_dest_ids.ids],
            "state": "draft",
            "rma_return_line_id": self.id,
            "company_id": self.rma_id.company_id.id,
            "price_unit": price_unit,
            "picking_type_id": self.rma_id.return_picking_type_id.id,
            "group_id": False,
            "origin": self.rma_id.name,
            # "route_ids": [],
            "warehouse_id": self.rma_id.return_picking_type_id.warehouse_id.id,
        }

        diff_quantity = self.product_qty - qty
        if float_compare(
            diff_quantity, 0.0, precision_rounding=self.product_uom.rounding
        ):
            line_uom = self.product_uom
            quant_uom = self.product_id.uom_id
            product_uom_qty, product_uom = line_uom._adjust_uom_quantities(
                diff_quantity, quant_uom
            )
            template["product_uom_qty"] = product_uom_qty
            template["product_uom"] = product_uom.id
            res.append(template)
        return res

    def _create_stock_moves(self, picking):
        values = []
        for line in self:
            for val in line._prepare_stock_moves(picking):
                values.append(val)
            values.append(val)
        return self.env["stock.move"].create(values)


class RmaExchangeLine(models.Model):
    _name = "sale.rma.exchange_line"
    _inherit = ["portal.mixin", "mail.thread", "mail.activity.mixin"]
    _description = "Sale Rma Exchange Line"
    _order = "id desc"

    @api.depends("product_qty", "price_unit", "tax_id")
    def _compute_amount(self):
        for line in self:
            taxes = line.tax_id.compute_all(
                line.price_unit,
                line.rma_id.currency_id,
                line.product_qty,
                partner=line.rma_id.sale_order_id.partner_shipping_id,
            )
            line.update(
                {
                    "price_tax": sum(
                        t.get("amount", 0.0) for t in taxes.get("taxes", [])
                    ),
                    "price_total": taxes["total_included"],
                    "price_subtotal": taxes["total_excluded"],
                }
            )

    rma_id = fields.Many2one("sale.rma", index=True)
    product_id = fields.Many2one("product.product", index=True)
    product_uom_category_id = fields.Many2one(related="product_id.uom_id.category_id")
    product_qty = fields.Float(
        string="Quantity", digits="Product Unit Of Measure", required=True, default=1.0
    )
    product_uom = fields.Many2one(
        "uom.uom",
        string="Unit of Measure",
        domain="[('category_id', '=', product_uom_category_id)]",
    )

    price_unit = fields.Float(
        "Unit Price", required=True, digit="Product Price", default=0.0
    )
    price_subtotal = fields.Monetary(
        compute="_compute_amount", string="Subtotal", store=True
    )
    price_tax = fields.Monetary(compute="_compute_amount", string="Taxes", store=True)

    price_total = fields.Monetary(compute="_compute_amount", string="Total", store=True)
    currency_id = fields.Many2one("res.currency", related="rma_id.currency_id")
    tax_id = fields.Many2many(
        "account.tax",
        string="Taxes",
        domain=["|", ("active", "=", False), ("active", "=", True)],
    )

    company_id = fields.Many2one(related="rma_id.company_id")
    #    move_ids = fields.One2many(
    #        "stock.move",
    #        "sale_exchange_line_id",
    #        string="Reservation",
    #        readonly=True,
    #        ondelete="set null",
    #        copy=False,
    #    )

    def _compute_tax_id(self):
        for line in self:
            fpos = (
                line.rma_id.sale_order_id.fiscal_position_id
                or line.rma_id.sale_order_id.partner_id.property_account_position_id
            )
            taxes = line.product_id.taxes_id.filtered(
                lambda r: not line.company_id or r.company_id == line.company_id
            )
            line.tax_id = (
                fpos.map_tax(
                    taxes,
                    line.product_id,
                    line.rma_id.sale_order_id.partner_shipping_id,
                )
                if fpos
                else taxes
            )

    def _get_display_price(self, product):
        sale_order = self.rma_id.sale_order_id
        if sale_order.pricelist_id.discount_policy == "with_discount":
            return product.with_context(pricelist=sale_order.pricelist_id.id).price

        final_price, rule_id = sale_order.pricelist_id.with_context(
            product_context
        ).get_product_price_rule(
            self.product_id, self.product_qty or 1.0, self.rma_id.partner_id
        )
        base_price, currency = self.with_context(
            product_context
        )._get_real_price_currency(
            product,
            rule_id,
            self.product_qty,
            self.product_uom,
            sale_order.pricelist_id.id,
        )

        if currency != sale_order.pricelist_id.currency_id:
            base_price = currency._convert(
                base_price,
                sale_order.pricelist_id.currency_id,
                sale_order.company_id or self.env.company,
                sale_order.date_order or fields.Date.today(),
            )
        return max(base_price, final_price)

    @api.onchange("product_id")
    def _onchange_product_id_change(self):
        if not self.product_id:
            return

        self._compute_tax_id()

        # uom & price_unit
        self.product_uom = self.product_id.uom_id
        self.price_unit = self.env["account.tax"]._fix_tax_included_price_company(
            self._get_display_price(self.product_id),
            self.product_id.taxes_id,
            self.tax_id,
            self.company_id,
        )

        return {}
