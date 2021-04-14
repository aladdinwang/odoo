from collections import defaultdict
import datetime
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare

from odoo.addons.purchase.models.purchase import PurchaseOrder as Purchase


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    @api.model
    def _default_picking_type(self):
        return self._get_picking_type(
            self.env.context.get("company_id") or self.env.company.id
        )

    sale_order_ids = fields.Many2many("sale.order", string="Sale Orders")
    partner_id = fields.Many2one(
        "res.partner",
        string="Vendor",
        required=True,
        states=Purchase.READONLY_STATES,
        change_default=True,
        tracking=True,
        domain="[('is_company', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="You can find a vendor by its Name, TIN, Email or Internal Reference.",
    )

    payment_state = fields.Selection(
        selection=[
            ("not_paid", "Not Paid"),
            ("in_payment", "In Payment"),
            ("paid", "Paid"),
        ],
        string="Payment",
        default="not_paid",
        store=True,
        readonly=True,
        copy=False,
        tracking=True,
        compute="_compute_payment_state",
        index=True,
    )

    is_dropshipping = fields.Boolean(default=False, readonly=True)
    payment_register_ids = fields.One2many(
        "purchase.payment.register", "purhcase_order_id", readonly=True, copy=False
    )

    @api.depends("invoice_ids", "invoice_ids.state", "invoice_ids.amount_residual")
    def _compute_payment_state(self):
        for order in self:
            paid_amount = 0.0
            invoices = self.invoice_ids.filtered(lambda x: x.state == "posted")
            for invoice in invoices:
                paid_amount += invoice.amount_total - invoice.amount_residual
            if (
                float_compare(paid_amount, order.amount_total, precision_rounding=0.01)
                == 0
            ):
                order.payment_state = "paid"
            elif float_compare(paid_amount, 0, precision_rounding=0.01) > 0:
                order.payment_state = "in_payment"
            else:
                order.payment_state = "not_paid"

    @api.model
    def _get_picking_type(self, company_id):
        picking_type = self.env["stock.picking.type"].search(
            [("code", "=", "incoming"), ("warehouse_id.company_id", "=", company_id)]
        )
        if not picking_type:
            picking_type = self.env["stock.picking.type"].search(
                [("code", "=", "incoming"), ("warehouse_id", "=", False)]
            )
        return picking_type[:1]

    @api.model
    def default_get(self, default_fields):
        rec = super().default_get(default_fields)
        active_ids = self._context.get("active_ids") or self._context.get("active_id")
        active_model = self._context.get("active_model")

        if not active_ids or active_model != "purchase.request":
            return rec

        # 创建默认采购单
        reqs = (
            self.env["purchase.request"]
            .browse(active_ids)
            .filtered(lambda x: x.state == "open")
        )
        if not reqs:
            raise UserError(_("You can only select open request"))

        origins = set()
        customer_partner_id_tuples = []

        last_req = None
        for req in reqs:
            origins.add(req.sale_order_id.name)
            customer_partner_id_tuples.append(
                (req.customer_shipping_id.id, req.partner_id.id)
            )
            if last_req and last_req.is_dropshipping != req.is_dropshipping:
                raise UserError(_("Only one delivery type at most"))
            last_req = req

        # 如果没有选中, 则什么都不做
        if last_req is None:
            return

        partner_ids = set(x[1] for x in customer_partner_id_tuples)
        if len(partner_ids) > 1:
            raise UserError(_("Only one supplier at most"))

        if last_req.is_dropshipping:
            if len(customer_partner_id_tuples) > 1:
                raise UserError(_("Only one customer at most"))

        partner_id = last_req.partner_id
        is_dropshipping = last_req.is_dropshipping

        if is_dropshipping:
            picking_type_id = self.env["stock.picking.type"].search(
                [
                    ("sequence_code", "=", "DS"),
                    "|",
                    ("warehouse_id", "=", False),
                    ("warehouse_id.company_id", "=", self.env.company.id),
                ],
                limit=1,
            )
        else:
            picking_type_id = self.env["stock.picking.type"].search(
                [
                    ("sequence_code", "=", "OUT"),
                    "|",
                    ("warehouse_id", "=", False),
                    ("warehouse_id.company_id", "=", self.env.company.id),
                ],
                limit=1,
            )

        fpos = (
            self.env["account.fiscal.position"]
            .with_context(force_company=self.env.company.id)
            .get_fiscal_position(partner_id.id)
        )
        currency_id = (
            partner_id.with_context(
                force_company=self.env.company.id
            ).property_purchase_currency_id
            or self.env.company.currency_id
        )

        origins = set()
        sale_order_ids = set()
        new_order_lines = []
        now = datetime.datetime.now()
        for req in reqs:
            sale_order_ids.add(req.sale_order_id.id)
            origins.add(req.sale_order_id.name)
            product_id = req.product_id
            uom_po_qty = req.product_uom._compute_quantity(
                req.product_uom_qty, product_id.uom_po_id
            )
            seller = product_id.with_context(
                force_company=self.env.company.id
            )._select_seller(
                partner_id=partner_id,
                quantity=uom_po_qty,
                date=now,
                uom_id=product_id.uom_po_id,
            )
            taxes = product_id.supplier_taxes_id
            # fpos = po.fiscal_position_id
            taxes_id = fpos.map_tax(taxes, product_id, seller.name) if fpos else taxes
            if taxes_id:
                taxes_id = taxes_id.filtered(
                    lambda x: x.company_id.id == self.env.company.id
                )

            price_unit = (
                self.env["account.tax"]._fix_tax_included_price_company(
                    seller.price,
                    product_id.supplier_taxes_id,
                    taxes_id,
                    self.env.company,
                )
                if seller
                else 0.0
            )
            if (
                price_unit
                and seller
                and currency_id
                and seller.currency_id != currency_id
            ):
                price_unit = seller.currency_id._convert(
                    price_unit, currency_id, self.env.company, fields.Date.today()
                )

            product_lang = product_id.with_prefetch().with_context(
                lang=partner_id.lang, partner_id=partner_id.id
            )
            name = product_lang.display_name
            if product_lang.description_purchase:
                name += "\n" + product_lang.description_purchase

            date_planned = datetime.datetime.today() + relativedelta(
                days=seller.delay if seller else 0
            )
            new_order_lines.append(
                (
                    0,
                    0,
                    {
                        "name": name,
                        "product_qty": uom_po_qty,
                        "product_id": product_id.id,
                        "product_uom": product_id.uom_po_id.id,
                        "price_unit": price_unit,
                        "date_planned": date_planned,
                        "taxes_id": [(6, 0, taxes_id.ids)],
                        "request_id": req.id,
                    },
                )
            )

        order_vals = {
            "partner_id": partner_id.id,
            "user_id": self.env.user.id or False,
            "picking_type_id": picking_type_id.id,
            "company_id": self.env.company.id,
            "currency_id": currency_id.id,
            "dest_address_id": picking_type_id.default_location_dest_id.id,
            "origin": ",".join(sorted(origins)),
            "payment_term_id": partner_id.with_context(
                force_company=self.env.company.id
            ).property_supplier_payment_term_id.id,
            "fiscal_position_id": fpos,
            "date_order": datetime.datetime.now(),
            "group_id": False,
            "order_line": new_order_lines,
            "sale_order_ids": [(6, 0, [x for x in sorted(sale_order_ids)])],
            "is_dropshipping": last_req.is_dropshipping,
        }
        rec.update(order_vals)
        return rec

    def action_create_purchase_order(self):
        active_ids = self.env.context.get("active_ids")
        if not active_ids:
            return ""

        return {
            "name": _("Create Purchase Order"),
            "res_model": "purchase.order",
            "view_mode": "form",
            "view_id": self.env.ref("qm.view_purchase_order_form_qm").id,
            "context": self.env.context,
            "target": "new",
            "type": "ir.actions.act_window",
        }

    def action_create_purchase_payment_register(self):
        self.ensure_one()

        return {
            "name": _("Create Purchase Payment Register"),
            "res_model": "purchase.payment.register",
            "view_mode": "form",
            "view_id": self.env.ref("qm.view_purchase_payment_register_form").id,
            "context": self.env.context,
            "target": "new",
            "type": "ir.actions.act_window",
        }

    def action_view_payment_register(self):
        registers = self.mapped("payment_register_ids")
        action = self.env.ref("qm.action_purchase_payment_register").read()[0]
        if len(registers) > 1:
            action["domain"] = [("id", "in", registers.ids)]
        elif len(registers) == 1:
            form_view = [(self.env.ref("qm.view_purchase_register_form").id, "form")]
            if "views" in action:
                action["views"] = form_view + [
                    (state, view) for state, view in action["views"] if view != "form"
                ]
            else:
                action["views"] = form_view
            action["res_id"] = registers.id
        else:
            action = {"type": "ir.actions.act_window_close"}
        return action


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    request_id = fields.Many2one(
        "purchase.request", string="Purchase Request", index=True
    )


class PurchaseRequest(models.Model):
    """
    sku需求池
    """

    _name = "purchase.request"
    _inherit = ["mail.thread", "mail.activity.mixin", "portal.mixin"]
    _description = "Purchase Request"
    _order = "id desc"

    @api.depends("sale_line_id")
    def _compute_partner_id_domain(self):
        for rec in self:
            rec.partner_ids = [
                (6, 0, rec.mapped("product_id.product_tmpl_id.seller_ids.name").ids)
            ]

    name = fields.Char(
        states={"draft": [("readonly", False)]},
        index=True,
        default=lambda self: _("New"),
    )
    sale_line_id = fields.Many2one(
        "sale.order.line", string="Sale Order Line", index=True, requried=True
    )
    sale_order_id = fields.Many2one(
        "sale.order", related="sale_line_id.order_id", index=True, readonly=True
    )
    customer_id = fields.Many2one(
        "res.partner", related="sale_order_id.partner_id", readonly=True, store=True
    )
    customer_shipping_id = fields.Many2one(
        "res.partner",
        related="sale_order_id.partner_shipping_id",
        readonly=True,
        store=True,
    )
    # delivery_type = fields.Selection(
    #     related="sale_order_id.delivery_type", readonly=True
    # )
    # picking_policy = fields.Selection(
    #     related="sale_order_id.picking_policy", readonly=True
    # )
    is_dropshipping = fields.Boolean(
        related="sale_order_id.is_dropshipping", readonly=True
    )
    purchase_line_ids = fields.One2many(
        "purchase.order.line", "request_id", string="Purchase Lines"
    )
    purchase_line_count = fields.Integer(
        string="Purchase Line Count", compute="_compute_purchase_line", readonly=True
    )
    product_id = fields.Many2one(
        "product.product", related="sale_line_id.product_id", readonly=True, index=True
    )
    product_uom_qty = fields.Float(
        string="Quantity",
        digits="Product Unit of Measure",
        related="sale_line_id.product_uom_qty",
        readonly=True,
        tracking=True,
    )
    product_uom = fields.Many2one(
        "uom.uom", related="sale_line_id.product_uom", readonly=True
    )
    qty_purchased = fields.Float(
        "Purchased Qty", compute="_compute_purchase_line", readonly=True, tracking=True
    )
    qty_to_purchase = fields.Float(
        "To Purchase Qty", compute="_compute_purchase_line", index=True, tracking=True
    )
    state = fields.Selection(
        selection=[("open", "In progress"), ("done", "Done"), ("cancel", "Cancelled")],
        string="Status",
        copy=False,
        default="open",
        readonly=True,
    )
    partner_ids = fields.Many2many("res.partner", compute=_compute_partner_id_domain)
    partner_id = fields.Many2one(
        "res.partner", "Partner", domain="[('id', 'in', partner_ids)]"
    )

    @api.model
    def create(self, vals):
        if vals.get("name", _("New")) == _("New"):
            vals["name"] = self.env["ir.sequence"].next_by_code(
                "purchase.request"
            ) or _("New")
        result = super().create(vals)
        return result

    @api.depends("purchase_line_ids")
    def _compute_purchase_line(self):
        for rec in self:
            line_ids = rec.purchase_line_ids.filtered(lambda x: x.state != "cancel")
            rec.purchase_line_count = len(line_ids)
            qty_purchased = sum(x.product_qty for x in line_ids if x != "cancel")
            rec.qty_purchased = qty_purchased
            rec.qty_to_purchase = rec.product_uom_qty - qty_purchased

            if rec.state == "open" and rec.qty_to_purchase <= 0:
                rec.state = "done"
            elif rec.state == "done" and rec.qty_to_purchase > 0:
                rec.state = "open"

    def action_view_purchase_line(self):
        purchase_line_ids = self.mapped("purchase_line_ids")
        action = self.env.ref("qm.action_purchase_order_line").read()[0]
        if len(purchase_line_ids) <= 0:
            action = {"type": "ir.actions.act_window_close"}
        action["domain"] = [("id", "in", purchase_line_ids.ids)]
        action["context"] = {"default_user_id": self.env.user.id}
        return action

    @api.onchange("sale_line_id")
    def _onchange_sale_line_id(self):
        for rec in self:
            rec.partner_id = False

        return {
            "domain": {
                "partner_id": [
                    (
                        "id",
                        "in",
                        self.mapped("product_id.product_tmpl_id.seller_ids.name").ids,
                    )
                ]
            }
        }

    @api.model
    def _get_picking_type(self, company_id):
        picking_type = self.env["stock.picking.type"].search(
            [("code", "=", "incoming"), ("warehouse_id.company_id", "=", company_id.id)]
        )
        if not picking_type:
            picking_type = self.env["stock.picking.type"].search(
                [("code", "=", "incoming"), ("warehouse_id", "=", False)]
            )
        return picking_type[:1]

    def action_request_create_purchase_order(self):
        origins = set()
        customer_partner_id_tuples = []

        last_rec = None
        for rec in self:
            origins.add(rec.sale_order_id.name)
            customer_partner_id_tuples.append(
                (rec.customer_shipping_id.id, rec.partner_id.id)
            )
            if last_rec and last_rec.is_dropshipping != rec.is_dropshipping:
                raise UserError(_("Only one delivery type at most"))
            last_rec = rec

        # 如果没有选中, 则什么都不做
        if last_rec is None:
            return

        partner_ids = set(x[1] for x in customer_partner_id_tuples)
        if len(partner_ids) > 1:
            raise UserError(_("Only one supplier at most"))

        if last_rec.is_dropshipping:
            if len(customer_partner_id_tuples) > 1:
                raise UserError(_("Only one customer at most"))

        return (
            self.env["purchase.order"]
            .with_context(
                active_ids=self.ids, active_model="purchase.request", active_id=self.id
            )
            .action_create_purchase_order()
        )
