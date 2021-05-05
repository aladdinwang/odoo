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

    # 生成交货单
    def _get_warehouse_move_values(
        self,
        product_id,
        product_qty,
        product_uom,
        locaiton_id,
        name,
        origin,
        company_id,
        values,
    ):
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", company_id.id)], limit=1
        )
        picking_type = self.env["stock.picking.type"].search(
            [
                ("code", "=", "outgoing"),
                ("warehouse_id", "=", warehouse.id),
                ("default_location_src_id", "=", warehouse.lot_stock_id.id),
            ],
            limit=1,
        )
        return {
            "location_id": warehouse.lot_stock_id.id,
            "warehouse_id": warehouse.id,
            "picking_type_id": picking_type.id,
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

        # 如果可用库存是负数, 则直接生成需求池
        # 如果可用库存是正数，则计算差额生成需求池
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

            # 需求池需要的属性
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
            domain = rule._make_pr_get_domain(
                procurement.company_id, procurement.values, partner
            )

            def _update_procurment_values(procurement):
                procurement.values["supplier"] = supplier
                procurement.values["propagate_date"] = rule.propagate_date
                procurement.values[
                    "propagate_date_minimum_delta"
                ] = rule.propagate_date_minimum_delta
                procurement.values["propagate_cancel"] = rule.propagate_cancel

            if (
                not sale_line.order_id.is_dropshipping
                or float_compare(
                    qty_available,
                    0,
                    precision_rounding=procurement.product_id.uom_id.rounding,
                )
                > 0
            ):
                qty_available -= qty_needed
                forecasted_qties_by_loc[rule.location_src_id][
                    procurement.product_id.id
                ] -= qty_needed
                move_values = rule._get_stock_move_values(*procurement)
                move_values.update(self._get_warehouse_move_values(*procurement))

                move_values["procure_method"] = "make_to_stock"
                moves_values_by_company[procurement.company_id.id].append(move_values)

                # recheck qty_available
                forecasted_qties_by_loc[rule.location_src_id][
                    procurement.product_id.id
                ] = qty_available
                if (
                    float_compare(
                        qty_available,
                        0,
                        precision_rounding=procurement.product_id.uom_id.rounding,
                    )
                    < 0
                ):
                    new_product_qty = procurement.product_id.uom_id._compute_quantity(
                        abs(qty_available), procurement.product_uom
                    )
                    new_procurement = procurement._replace(product_qty=new_product_qty)
                    _update_procurment_values(new_procurement)
                    procurements_by_pr_domain[domain].append((new_procurement, rule))
            else:
                _update_procurement_values(procurement)
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
