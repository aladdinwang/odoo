from odoo import fields, models, api, _


# Todo: 最后整理的时候，去掉冗余


class AccountMove(models.Model):
    _inherit = "account.move"

    # payment_ids = fields.Many2many(
    #     "account.payment",
    #     "account_invoice_payment_rel",
    #     "invoice_id",
    #     "payment_id",
    #     string="Payments",
    #     copy=False,
    #     readonly=True,
    # )

    # payment_amount = fields.Monetary(compute="_compute_payment_amount", readonly=True)
    # payment_difference = fields.Monetary(
    #     compute="_compute_payment_amount", readonly=True
    # )

    # state = fields.Selection(
    #     selection_add=[
    #         ("to_invoice", "To Invoice"),
    #         ("invoiced", "Invoiced"),
    #         ("sent", "Sent"),
    #         ("received", "Received"),
    #         ("returned", "Returned"),
    #     ]
    # )

    # state2 = fields.Selection(
    #     selection=[
    #         ("to_invoice", "To Invoice"),
    #         ("invoiced", "Invoiced"),
    #         ("sent", "Sent"),
    #         ("received", "Received"),
    #         ("returned", "Returned"),
    #     ],
    #     string="Status2",
    #     inverse="_set_state",
    #     required=True,
    #     copy=False,
    #     tracking=True,
    #     default="to_invoice",
    # )

    # 发票状态
    receipt_state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("posted", "Posted"),
            ("approved", "Approved"),
            ("reject", "Rejected"),
            ("cancel", "Cancelled"),
        ],
        string="Status",
        required=True,
        index=True,
        tracking=True,
        default="draft",
    )

    # 提交日期，提交人
    posted_date = fields.Date(string="Posted Date", index=True)
    posted_by = fields.Many2one("res.users", string="Posted by")

    # 审核日期，审核人
    approve_date = fields.Date(
        string="Approve Date", index=True, default=fields.Date.today()
    )
    approve_by = fields.Many2one("res.users", string="Approved by")

    # 驳回日期，驳回人
    reject_date = fields.Date(
        string="Reject Date", index=True, default=fields.Date.today()
    )
    reject_by = fields.Many2one("res.users", string="Reject by")
    reject_reason = fields.Char("Reject Reason")

    # 作废
    cancel_date = fields.Date(
        string="Cancel Date", index=True, default=fields.Date.today()
    )
    cancel_by = fields.Many2one("res.users", string="Cancelled by")
    cancel_reason = fields.Char(string="Cancel reason")

    invoice_ids = fields.Many2many(
        "account.sale.invoice",
        "account_sale_invoice_rel",
        "move_id",
        "invoice_id",
        string="Invoices",
        copy=False,
    )

    sale_line_count = fields.Integer(
        compute="_compute_sale_line_count",
        string="Sale Line Count",
        copy=False,
        default=0,
        store=True,
    )

    # @api.depends("amount_total_signed", "payment_ids")
    # def _compute_payment_amount(self):
    #     not_paid_moves = self.filtered(lambda m: m.invoice_payment_state == "not_paid")
    #     for move in self - not_paid_moves:
    #         payment_total = 0.0
    #         for p in move.payment_ids:
    #             payment_total += -p.amount if p.payment_type == "outbound" else p.amount
    #         move.payment_amount = payment_total
    #         move.payment_difference = move.amount_total_signed - payment_total
    #     not_paid_moves.payment_amount = 0
    #     not_paid_moves.payment_difference = 0

    # def _set_state(self):
    #     for move in self:
    #         if move.state in ("to_invoice", "invoiced", "sent", "received", "returned"):
    #             move.write({"state": move.state2})

    @api.model
    def default_get(self, default_fields):
        rec = super(AccountMove, self).default_get(default_fields)
        active_ids = self._context.get("active_ids") or self._context.get("active_id")
        active_model = self._context.get("active_model")

        if not active_ids or active_model != "sale.order.line":
            return rec

        sale_lines = (
            self.env["sale.order.line"]
            .browse(active_ids)
            .filtered(
                lambda x: x.state not in ("draft", "cancel") and x.qty_to_receipt > 0
            )
        )

        # hack, account.move.create会再次调用default_get
        if not sale_lines and not any(
            set(default_fields)
            - {"invoice_vendor_bill_id", "purchase_id", "purchase_vendor_bill_id"}
        ):
            return rec

        sale_lines._check_receipt_validity()
        new_rec = sale_lines._create_receipt()
        rec.update(new_rec)
        return rec

    def action_download_xlsx(self):
        return {
            "type": "ir.actions.act_url",
            "url": f'/qm/export/xlsx?model=account.move&ids={",".join([str(rec.id) for rec in self])}',
            "target": "self",
        }

    @api.depends(
        "line_ids.debit",
        "line_ids.credit",
        "line_ids.currency_id",
        "line_ids.amount_currency",
        "line_ids.amount_residual",
        "line_ids.amount_residual_currency",
        "line_ids.payment_id.state",
    )
    def _compute_amount(self):
        invoice_ids = [
            move.id
            for move in self
            if move.id and move.is_invoice(include_receipts=True)
        ]
        self.env["account.payment"].flush(["state"])
        if invoice_ids:
            self._cr.execute(
                """
                    SELECT move.id
                    FROM account_move move
                    JOIN account_move_line line ON line.move_id = move.id
                    JOIN account_partial_reconcile part ON part.debit_move_id = line.id OR part.credit_move_id = line.id
                    JOIN account_move_line rec_line ON
                        (rec_line.id = part.credit_move_id AND line.id = part.debit_move_id)
                        OR
                        (rec_line.id = part.debit_move_id AND line.id = part.credit_move_id)
                    JOIN account_payment payment ON payment.id = rec_line.payment_id
                    JOIN account_journal journal ON journal.id = rec_line.journal_id
                    WHERE payment.state IN ('posted', 'sent')
                    AND journal.post_at = 'bank_rec'
                    AND move.id IN %s
                """,
                [tuple(invoice_ids)],
            )
            in_payment_set = set(res[0] for res in self._cr.fetchall())
        else:
            in_payment_set = {}

        for move in self:
            total_untaxed = 0.0
            total_untaxed_currency = 0.0
            total_tax = 0.0
            total_tax_currency = 0.0
            total_residual = 0.0
            total_residual_currency = 0.0
            total = 0.0
            total_currency = 0.0
            currencies = set()

            for line in move.line_ids:
                if line.currency_id:
                    currencies.add(line.currency_id)

                if move.is_invoice(include_receipts=True):
                    # === Invoices ===

                    if not line.exclude_from_invoice_tab:
                        # Untaxed amount.
                        total_untaxed += line.balance
                        total_untaxed_currency += line.amount_currency
                        total += line.balance
                        total_currency += line.amount_currency
                    elif line.tax_line_id:
                        # Tax amount.
                        total_tax += line.balance
                        total_tax_currency += line.amount_currency
                        total += line.balance
                        total_currency += line.amount_currency
                    elif line.account_id.user_type_id.type in ("receivable", "payable"):
                        # Residual amount.
                        total_residual += line.amount_residual
                        total_residual_currency += line.amount_residual_currency
                else:
                    # === Miscellaneous journal entry ===
                    if line.debit:
                        total += line.balance
                        total_currency += line.amount_currency

            if move.type == "entry" or move.is_outbound():
                sign = 1
            else:
                sign = -1
            move.amount_untaxed = sign * (
                total_untaxed_currency if len(currencies) == 1 else total_untaxed
            )
            move.amount_tax = sign * (
                total_tax_currency if len(currencies) == 1 else total_tax
            )
            move.amount_total = sign * (
                total_currency if len(currencies) == 1 else total
            )
            move.amount_residual = -sign * (
                total_residual_currency if len(currencies) == 1 else total_residual
            )
            move.amount_untaxed_signed = -total_untaxed
            move.amount_tax_signed = -total_tax
            move.amount_total_signed = abs(total) if move.type == "entry" else -total
            move.amount_residual_signed = total_residual

            currency = (
                len(currencies) == 1 and currencies.pop() or move.company_id.currency_id
            )
            is_paid = (
                currency
                and currency.is_zero(move.amount_residual)
                or not move.amount_residual
            )

            # Compute 'invoice_payment_state'.
            if move.type == "entry":
                move.invoice_payment_state = False
            elif (
                move.state
                in ("posted", "to_invoice", "invoiced", "sent", "received", "returned")
                and is_paid
            ):
                if move.id in in_payment_set:
                    move.invoice_payment_state = "in_payment"
                else:
                    move.invoice_payment_state = "paid"
            else:
                move.invoice_payment_state = "not_paid"

    def action_create_receipt(self):
        active_ids = self._context.get("active_ids") or self._context.get("active_id")
        if not active_ids:
            return ""

        return {
            "name": _("Create Sale Receipt"),
            "res_model": "account.move",
            "view_mode": "form",
            "view_id": self.env.ref("qm.view_account_move_form_qm").id,
            "context": self.env.context,
            "target": "new",
            "type": "ir.actions.act_window",
        }

    def action_post(self):
        res = super().action_post()
        self.filtered(lambda x: x.receipt_state == "draft").write(
            {
                "receipt_state": "posted",
                "posted_by": self.env.user.id,
                "posted_date": fields.Date.today(),
            }
        )
        return res

    def action_approve(self):
        self.filtered(lambda x: x.receipt_state == "posted").write(
            {
                "receipt_state": "approved",
                "approve_by": self.env.user.id,
                "approve_date": fields.Date.today(),
            }
        )

    def action_reject(self):
        self.filtered(lambda x: x.receipt_state == "posted").write(
            {
                "receipt_state": "reject",
                "reject_by": self.env.user.id,
                "reject_date": fields.Date.today(),
            }
        )

    def button_draft(self):
        super().button_draft()
        self.write({"receipt_state": "draft"})

    def action_cancel(self):
        self.button_cancel()
        self.write({"receipt_state": "cancel"})

    def _get_sequence(self):
        seq = super()._get_sequence()
        if self.type == "out_receipt":
            return self.env.ref("qm.seq_account_move_out_receipt")
        else:
            return seq

    def action_view_sale_lines(self):
        self.ensure_one()
        action = self.env.ref("qm.action_order_lines_to_receipt").read()[0]
        action["domain"] = [
            ("id", "in", self.mapped("invoice_line_ids.sale_line_ids").ids)
        ]
        return action

    @api.depends("invoice_line_ids.sale_line_ids")
    def _compute_sale_line_count(self):
        for move in self:
            move.sale_line_count = len(move.invoice_line_ids.sale_line_ids.ids)
