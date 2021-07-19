from odoo import api, fields, models, SUPERUSER_ID, _
from odoo.exceptions import UserError
from odoo.tools import float_is_zero, float_compare


class SaleOrder(models.Model):
    _inherit = "sale.order"

    outer_name = fields.Char(string="Outer Order Reference")
    # invoice_state = fields.Selection(
    #     [
    #         ("pending", "Pending"),
    #         ("to_invoice", "To Invoice"),
    #         ("invoiced", "Invoiced"),
    #         ("sent", "Sent"),
    #         ("received", "Received"),
    #         ("returned", "Returned"),
    #     ],
    #     string="Invoice State",
    #     default="pending",
    #     compute="_compute_invoice_state",
    #     store=True,
    #     readonly=True,
    #     index=True,
    # )
    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        readonly=True,
        states={"draft": [("readonly", False)], "sent": [("readonly", False)]},
        required=True,
        change_default=True,
        index=True,
        tracking=1,
        domain="[('is_company', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
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

    # delivery_type = fields.Selection(
    #     selection=[("warehouse", "Warehouse"), ("dropship", "Dropship")],
    #     string="Delivery Type",
    #     default="warehouse",
    #     tracking=True,
    # )

    # picking_policy = fields.Selection(selection_add=[("dropship", "DropShip")])

    is_dropshipping = fields.Boolean("Is Dropshipping")
    payment_register_lines = fields.One2many(
        "sale.payment.register.line", "sale_order_id", readonly=True, copy=False
    )
    parent_id = fields.Many2one(
        "sale.order", ondelete="cascade", help="退换货订单，用此字段关联原订单"
    )
    rma_id = fields.Many2one("sale.rma", ondelete="cascade", help="退换货申请", index=True)

    # @api.depends("invoice_ids.state")
    # def _compute_invoice_state(self):
    #     unconfirmed_orders = self.filtered(lambda so: so.state not in ["sale", "done"])
    #     unconfirmed_orders.invoice_state = "pending"
    #     confirmed_orders = self - unconfirmed_orders

    #     if not confirmed_orders:
    #         return

    #     _sale_order_invoice_states = {
    #         "to_invoice",
    #         "invoiced",
    #         "sent",
    #         "received",
    #         "returned",
    #     }

    #     for order in confirmed_orders:
    #         invoice_states = set(
    #             [
    #                 invoice.state
    #                 for invoice in order.invoice_ids
    #                 if invoice.state not in ["draft", "cancel"]
    #             ]
    #         )
    #         if any(state == "posted" for state in invoice_states):
    #             order.invoice_state = "pending"
    #         elif (
    #             len(invoice_states) == 1 and invoice_states & _sale_order_invoice_states
    #         ):
    #             order.invoice_state = list(invoice_states)[0]
    #         else:
    #             # use the last one state
    #             last_invoice = max(order.invoice_ids, default=None, key=lambda x: x.id)
    #             if last_invoice and last_invoice.state in _sale_order_invoice_states:
    #                 order.invoice_state = last_invoice.state
    #             else:
    #                 order.invoice_state = "pending"

    def action_to_invoice(self):
        sale_orders = self.filtered(
            lambda o: o.state in ["sale", "posted"] and o.invoice_state == "pending"
        )
        for order in sale_orders:
            new_invoice_ids = []
            for move in order.invoice_ids:
                if move.state == "posted":
                    new_invoice_ids.append((1, move.id, {"state": "to_invoice"}))
            order.write({"invoice_ids": new_invoice_ids})

    def action_create_rma(self):
        self.ensure_one()
        return {
            "name": _("Create Sale RMA"),
            "res_model": "sale.rma",
            "view_mode": "form",
            "view_id": self.env.ref("qm.sale_rma_form").id,
            "context": self.env.context,
            "target": "new",
            "type": "ir.actions.act_window",
        }

    def _prepare_invoice(self):
        invoice_vals = super()._prepare_invoice()
        invoice_vals["partner_id"] = self.partner_id.id
        return invoice_vals

    @api.depends(
        "payment_register_lines",
        "payment_register_lines.state",
        "payment_register_lines.amount",
    )
    def _compute_payment_state(self):
        for order in self:
            paid_amount = sum(
                x.amount
                for x in self.payment_register_lines.filtered(
                    lambda x: x.state == "reconciled"
                )
            )
            total_amount = sum(
                x.amount
                for x in self.payment_register_lines.filtered(
                    lambda x: x.state not in ("cancelled",)
                )
            )
            if float_compare(total_amount, 0.0, precision_rounding=0.01) == 0:
                order.payment_state = "not_paid"
            elif (
                float_compare(paid_amount, order.amount_total, precision_rounding=0.01)
                >= 0
            ):
                order.payment_state = "paid"
            else:
                order.payment_state = "in_payment"

    def _prepare_receipt(self):
        self = self.with_context(
            default_company_id=self.company_id.id, force_company=self.company_id.id
        )
        journal = (
            self.env["account.move"]
            .with_context(default_type="out_receipt")
            ._get_default_journal()
        )

        receipt_vals = {
            "type": "out_receipt",
            "currency_id": self.pricelist_id.currency_id.id,
            "campaign_id": self.campaign_id.id,
            "invoice_user_id": self.env.user.id or self.user_id.id,
            "team_id": self.team_id.id or False,
            "partner_id": self.partner_invoice_id.id,
            "partner_shipping_id": self.partner_shipping_id.id,
            "invoice_partner_bank_id": self.company_id.partner_id.bank_ids[:1].id,
            "invoice_payment_term_id": self.payment_term_id.id,
            "fiscal_position_id": self.fiscal_position_id.id
            or self.partner_invoice_id.property_account_position_id.id,
            "journal_id": journal.id,
            "invoice_line_ids": [],
            "line_ids": [],
            "company_id": self.company_id.id,
            "invoice_date": fields.Date.today(),
            "invoice_vendor_bill_id": False,
            "purchase_id": False,
            "purchase_vendor_bill_id": False,
        }
        return receipt_vals


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.depends("invoice_lines.move_id.receipt_state", "invoice_lines.quantity")
    def _get_receipt_qty(self):
        for line in self:
            qty_receipt = 0.0
            for invoice_line in line.invoice_lines:
                if invoice_line.move_id.receipt_state not in ("cancel", "reject"):
                    if invoice_line.move_id.type == "out_receipt":
                        qty_receipt += invoice_line.product_uom_id._compute_quantity(
                            invoice_line.quantity, line.product_uom
                        )
            line.qty_receipt = qty_receipt

    @api.depends("qty_receipt", "product_uom_qty", "order_id.state")
    def _get_to_receipt_qty(self):
        for line in self:
            if line.order_id.state in ["sale", "done"]:
                if line.product_id.invoice_policy == "order":
                    line.qty_to_receipt = line.product_uom_qty - line.qty_receipt
                else:
                    line.qty_to_receipt = line.qty_delivered - line.qty_receipt
            else:
                line.qty_to_receipt = 0

    @api.depends("order_id")
    def _compute_parent_id(self):
        ...

    parent_id = fields.Many2one(
        "sale.order",
        compute="_compute_parent_id",
        string="Original Sale Order",
        store=True,
    )

    # 已开票数量
    qty_receipt = fields.Float(
        compute="_get_receipt_qty",
        string="Receipt quantity",
        store=True,
        readonly=True,
        digits="Product Unit of Measure",
    )

    # 待开票数量
    qty_to_receipt = fields.Float(
        compute="_get_to_receipt_qty",
        string="To Receipt Quantity",
        store=True,
        readonly=True,
        digits="Product Unit of Measure",
    )

    def _check_receipt_validity(self):
        if not self:
            raise UserError(_("One order line at least"))

        last_line = False
        for line in self:
            if last_line and last_line.order_partner_id != line.order_partner_id:
                raise UserError(_("Only one partner at most"))
            last_line = line

    def _prepare_receipt_line(self):
        self.ensure_one()
        company_id = self.env.context.get("company_id") or self.env.company.id
        account_id = self.env["account.account"].search(
            [("code", "=like", "7001%"), ("company_id", "=", company_id)], limit=1
        )

        return {
            "display_type": self.display_type,
            "sequence": self.sequence,
            "name": self.name,
            "product_id": self.product_id.id,
            "product_uom_id": self.product_uom.id,
            "quantity": self.qty_to_receipt,
            "price_unit": self.price_unit,
            "tax_ids": [(6, 0, self.tax_id.ids)],
            "analytic_account_id": self.order_id.analytic_account_id.id,
            "analytic_tag_ids": [(6, 0, self.analytic_tag_ids.ids)],
            "sale_line_ids": [(4, self.id)],
            "account_id": account_id.id,
        }

    # 根据勾选的sale.order.line, 创建开票申请
    # 一次只能生成一个
    def _create_receipt(self):
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        order_id = self[0].order_id
        move = order_id._prepare_receipt()
        for line in self:
            if float_is_zero(line.qty_to_receipt, precision_digits=precision):
                continue
            move["line_ids"].append((0, 0, line._prepare_receipt_line()))
        return move
