from collections import defaultdict
from dateutil.relativedelta import relativedelta
from itertools import groupby

from odoo import api, fields, models, _
from odoo.tools import float_compare
from odoo.exceptions import UserError


class StockRule(models.Model):
    _inherit = "stock.rule"

    action = fields.Selection(selection_add=[("request", "PurchaseRequest")])

    def _make_pr_get_domain(self, company_id, values, partner):
        # 不考虑group_id，越简单越好
        domain = (
            ("state", "=", "draft"),
            ("sale_line_id", "=", values["sale_line_id"]),
        )
        return domain

    def _prepare_purchase_request(
        self, product_id, product_qty, product_uom, company_id, values
    ):
        partner = values["supplier"].name
        procurement_uom_pr_qty = product_uom._compute_quantity(
            product_qty, product_id.uom_po_id
        )
        sale_line = self.env["sale.order.line"].browse(values["sale_line_id"])
        seller = product_id.with_context(force_company=company_id.id)._select_seller(
            partner_id=partner,
            quantity=procurement_uom_pr_qty,
            date=sale_line.order_id.date_order.date(),
            uom_id=product_id.uom_po_id,
        )

        # move_dest_ids该怎么处理
        # move_dest_ids在
        # 不记录move_dest_ids，在生成采购单的时候再去取
        # 通过sale_order_line.move_ids来去获取
        return {
            "product_uom_qty": procurement_uom_pr_qty,
            "product_id": product_id.id,
            "product_uom": product_id.uom_po_id.id,
            "sale_line_id": values["sale_line_id"],
            "partner_id": seller.name.id,
        }

    @api.model
    def _run_request(self, procurements):
        # 重新_run_buy生成purchase.request
        # 如果取消销售单的话，则应该取消对应的需求池，回滚移库
        forecasted_qties_by_loc = defaultdict(dict)
        for procurement, rule in procurements:
            if not rule.location_src_id:
                msg = _("No source location defined on stock rule: %s!") % (rule.name,)
                raise UserError(msg)

            product_id = procurement.product_id
            forecasted_qties_by_loc[rule.location_src_id][
                product_id.id
            ] = product_id.free_qty

        procurements_by_pr_domain = defaultdict(list)
        moves_values_by_company = defaultdict(list)
        for procurement, rule in procurements:
            qty_needed = procurement.product_uom._compute_quantity(
                procurement.product_qty, procurement.product_id.uom_id
            )
            qty_available = forecasted_qties_by_loc[rule.location_src_id][
                procurement.product_id.id
            ]
            sale_line = self.env["sale.order.line"].browse(
                procurement.values["sale_line_id"]
            )
            if (
                float_compare(
                    qty_needed,
                    qty_available,
                    precision_rounding=procurement.product_id.uom_id.rounding,
                )
                <= 0
                and not sale_line.order_id.is_dropshipping
            ):
                forecasted_qties_by_loc[rule.location_src_id][
                    procurement.product_id.id
                ] -= qty_needed
                move_values = rule._get_stock_move_values(*procurement)
                move_values["procure_method"] = "make_to_stock"
                moves_values_by_company[procurement.company_id.id].append(move_values)
            else:
                procurement_date_planned = fields.Datetime.from_string(
                    procurement.values["date_planned"]
                )
                schedule_date = procurement_date_planned - relativedelta(
                    days=procurement.company_id.po_lead
                )

                supplier = procurement.product_id._select_seller(
                    partner_id=procurement.values.get("supplier_id"),
                    quantity=procurement.product_qty,
                    date=schedule_date.date(),
                    uom_id=procurement.product_uom,
                )
                if not supplier:
                    msg = _(
                        "There is no matching vendor price to generate the purchase order for product %s (no vendor defined, minimum quantity not reached, dates not valid, ...). Go on the product form and complete the list of vendors."
                    ) % (procurement.product_id.display_name)
                    raise UserError(msg)

                partner = supplier.name
                procurement.values["supplier"] = supplier
                procurement.values["propagate_date"] = rule.propagate_date
                procurement.values[
                    "propagate_date_minimum_delta"
                ] = rule.propagate_date_minimum_delta
                procurement.values["propagate_cancel"] = rule.propagate_cancel
                domain = rule._make_pr_get_domain(
                    procurement.company_id, procurement.values, partner
                )
                procurements_by_pr_domain[domain].append((procurement, rule))

        # 创建出库单
        for company_id, moves_values in moves_values_by_company.items():
            moves = (
                self.env["stock.move"]
                .sudo()
                .with_context(force_company=company_id)
                .create(moves_values)
            )
            moves._action_confirm()

        # 创建需求池
        for domain, procurements_rules in procurements_by_pr_domain.items():
            procurements, rules = zip(*procurements_rules)
            pr = (
                self.env["purchase.request"]
                .sudo()
                .search([dom for dom in domain], limit=1)
            )
            company_id = procurements[0].company_id
            for procurement in procurements:
                if not pr:
                    vals = rules[0]._prepare_purchase_request(
                        procurement.product_id,
                        procurement.product_qty,
                        procurement.product_uom,
                        company_id,
                        procurement.values,
                    )
                    pr = (
                        self.env["purchase.request"]
                        .with_context(force_comanpy=company_id.id)
                        .sudo()
                        .create(vals)
                    )
                else:
                    vals = self._prepare_purchase_request(
                        procurement.product_id,
                        procurement.product_qty,
                        procurement.product_uom,
                        company_id,
                        procurement.values,
                        pr,
                    )
                    vals.pop("sale_line_id")
                    pr.write(vals)


class ProcurementGroup(models.Model):
    _inherit = "procurement.group"

    move_type = fields.Selection(selection_add=[("dropship", "Dropship")])
