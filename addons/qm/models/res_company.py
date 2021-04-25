# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _


class ResCompany(models.Model):
    _inherit = "res.company"

    # -------------------------------------------------------------------------
    # Sequences
    # -------------------------------------------------------------------------
    def _create_dropship_sequence(self):
        dropship_vals = []
        for company in self:
            dropship_vals.append(
                {
                    "name": "Dropship (%s)" % company.name,
                    "code": "stock.dropshipping",
                    "company_id": company.id,
                    "prefix": "DS/",
                    "padding": 5,
                }
            )
        if dropship_vals:
            self.env["ir.sequence"].create(dropship_vals)

    @api.model
    def create_missing_dropship_sequence(self):
        company_ids = self.env["res.company"].search([])
        company_has_dropship_seq = (
            self.env["ir.sequence"]
            .search([("code", "=", "stock.dropshipping")])
            .mapped("company_id")
        )
        company_todo_sequence = company_ids - company_has_dropship_seq
        company_todo_sequence._create_dropship_sequence()

    def _create_per_company_sequences(self):
        super(ResCompany, self)._create_per_company_sequences()
        self._create_dropship_sequence()

    # -------------------------------------------------------------------------
    # Picking types
    # -------------------------------------------------------------------------
    def _create_dropship_picking_type(self):
        dropship_vals = []
        for company in self:
            sequence = self.env["ir.sequence"].search(
                [("code", "=", "stock.dropshipping"), ("company_id", "=", company.id)]
            )
            dropship_vals.append(
                {
                    "name": "Dropship",
                    "company_id": company.id,
                    "warehouse_id": False,
                    "sequence_id": sequence.id,
                    "code": "incoming",
                    "default_location_src_id": self.env.ref(
                        "stock.stock_location_suppliers"
                    ).id,
                    "default_location_dest_id": self.env.ref(
                        "stock.stock_location_customers"
                    ).id,
                    "sequence_code": "DS",
                }
            )
        if dropship_vals:
            self.env["stock.picking.type"].create(dropship_vals)

    @api.model
    def create_missing_dropship_picking_type(self):
        company_ids = self.env["res.company"].search([])
        company_has_dropship_picking_type = (
            self.env["stock.picking.type"]
            .search([("name", "=", "Dropship")])
            .mapped("company_id")
        )
        company_todo_picking_type = company_ids - company_has_dropship_picking_type
        company_todo_picking_type._create_dropship_picking_type()

    def _create_per_company_picking_types(self):
        super(ResCompany, self)._create_per_company_picking_types()
        self._create_dropship_picking_type()

    # -------------------------------------------------------------------------
    # Stock rules
    # -------------------------------------------------------------------------
    def _create_purchase_request_rule(self):
        purchase_request_route = self.env.ref("qm.route_purchase_request")
        supplier_location = self.env.ref("stock.stock_location_suppliers")
        customer_location = self.env.ref("stock.stock_location_customers")

        dropship_vals = []
        for company in self:
            warehouse = self.env["stock.warehouse"].search(
                [("company_id", "=", company.id)], limit=1
            )
            location_src_id = warehouse.lot_stock_id
            receipt_picking_type = self.env["stock.picking.type"].search(
                [
                    ("code", "=", "outgoing"),
                    ("warehouse_id", "=", warehouse.id),
                    ("default_location_src_id", "=", location_src_id.id),
                ],
                limit=1,
            )
            dropship_vals.append(
                {
                    "name": "%s → %s" % ("Purchase request", customer_location.name),
                    "action": "request",
                    "location_id": customer_location.id,
                    "location_src_id": location_src_id.id,
                    "procure_method": "mts_else_mto",
                    "route_id": purchase_request_route.id,
                    "picking_type_id": receipt_picking_type.id,
                    "company_id": company.id,
                }
            )
        if dropship_vals:
            self.env["stock.rule"].create(dropship_vals)

    @api.model
    def create_missing_purchase_request_rule(self):
        purchase_request_route = self.env.ref("qm.route_purchase_request")

        company_ids = self.env["res.company"].search([])
        company_has_dropship_rule = (
            self.env["stock.rule"]
            .search([("route_id", "=", purchase_request_route.id)])
            .mapped("company_id")
        )
        company_todo_rule = company_ids - company_has_dropship_rule
        company_todo_rule = company_ids
        company_todo_rule._create_purchase_request_rule()

    def _create_per_company_rules(self):
        super(ResCompany, self)._create_per_company_rules()
        # self._create_dropship_rule()
