from odoo import fields, models, api
from odoo.osv import expression


class ProductCategory(models.Model):
    _inherit = "product.category"

    code = fields.Char("Reference")
    complete_code = fields.Char(
        "Complete Code", compute="_compute_complete_code", store=True
    )
    tax_classification_id = fields.Many2one("tax.classification", "Tax Classification")

    @api.depends("code", "parent_id.complete_code")
    def _compute_complete_code(self):
        for category in self:
            if category.parent_id:
                category.complete_code = "".join(
                    filter(None, [category.parent_id.complete_code, category.code])
                )
            else:
                category.complete_code = category.code

    @api.model
    def _name_search(
        self, name="", args=None, operator="ilike", limit=100, name_get_uid=None
    ):
        if not args:
            args = []

        if name:
            positive_operators = ["=", "ilike", "=ilike", "like", "=like"]
            cate_ids = []

            if operator in positive_operators:
                cate_ids = self._search(
                    [("complete_code", "=", name)] + args,
                    limit=limit,
                    access_rights_uid=name_get_uid,
                )
                if not cate_ids:
                    cate_ids = self._search(
                        [("name", "=", name)] + args,
                        limit=limit,
                        access_rights_uid=name_get_uid,
                    )
            if not cate_ids and operator not in expression.NEGATIVE_TERM_OPERATORS:
                cate_ids = self._search(
                    args + [("complete_code", operator, name)], limit=limit
                )
                if not limit or len(cate_ids) < limit:
                    limit2 = (limit - len(cate_ids)) if limit else False
                    cate2_ids = self._search(
                        args + [("name", operator, name), ("id", "not in", cate_ids)],
                        limit=limit2,
                        access_rights_uid=name_get_uid,
                    )
                    cate_ids.extend(cate2_ids)
            elif not cate_ids and operator in expression.NEGATIVE_TERM_OPERATORS:
                domain = expression.OR(
                    [
                        [
                            "&",
                            ("complete_code", operator, name),
                            ("name", operator, name),
                        ],
                        ["&", ("complete_code", "=", False), ("name", operator, name)],
                    ]
                )
                domain = expression.AND([args, domain])
                cate_ids = self._search(
                    domain, limit=limit, access_rights_uid=name_get_uid
                )
        else:
            cate_ids = self._search(args, limit=limit, access_rights_uid=name_get_uid)
        return models.lazy_name_get(self.browse(cate_ids).with_user(name_get_uid))


class ProductProduct(models.Model):
    _inherit = "product.product"

    default_code = fields.Char(
        "Internal Reference", compute="_compute_default_code", store=True, index=True
    )

    @api.depends("product_tmpl_id.categ_id")
    def _compute_default_code(self):
        for product in self:
            if product.product_tmpl_id.categ_id:
                product.default_code = "".join(
                    filter(
                        None,
                        [
                            product.product_tmpl_id.categ_id.complete_code,
                            self.env["ir.sequence"].next_by_code(
                                f"product.{product.product_tmpl_id.categ_id.complete_code}"
                            ),
                        ],
                    )
                )


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.onchange("company_id")
    def _onchange_company_id(self):
        return {
            "domain": {
                "property_account_income_id": self.company_id
                and [
                    ("company_id", "=", self.company_id.id),
                    ("internal_group", "=", "income"),
                ]
                or [],
                "property_account_expense_id": self.company_id
                and [
                    ("company_id", "=", self.company_id.id),
                    ("internal_group", "=", "expense"),
                ]
                or [],
                "property_account_creditor_price_difference": self.company_id
                and [
                    ("company_id", "=", self.company_id.id),
                    ("internal_group", "=", "equity"),
                ]
                or [],
            }
        }
