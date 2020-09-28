from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
from odoo.osv import expression


class ProductCategory(models.Model):
    _inherit = "product.category"

    code = fields.Char("Reference")
    complete_code = fields.Char(
        "Complete Code", compute="_compute_complete_code", store=True
    )
    tax_classification_id = fields.Many2one("tax.classification", "Tax Classification")
    has_seq = fields.Boolean("Has ir.seq", compute="_compute_seq", store=True)
    number_next = fields.Integer(
        "Number Next", compute="_compute_seq", inverse="_set_number_next"
    )

    @api.depends("code", "parent_id.complete_code")
    def _compute_complete_code(self):
        for category in self:
            if category.parent_id:
                category.complete_code = "".join(
                    filter(None, [category.parent_id.complete_code, category.code])
                )
            else:
                category.complete_code = category.code

    @api.depends("complete_code")
    def _compute_seq(self):
        if not self._ids:
            return

        self.env.cr.execute(
            """
        SELECT categ.id, seq.number_next FROM product_category categ
        INNER JOIN ir_sequence seq ON seq.code = concat('product.', categ.complete_code)
        WHERE categ.id IN %s
        """,
            [self._ids],
        )
        categ_id_to_number_next = {x[0]: x[1] for x in self.env.cr.fetchall()}
        for categ in self:
            if categ.id in categ_id_to_number_next:
                categ.has_seq = True
                categ.number_next = categ_id_to_number_next[categ.id]
            else:
                categ.has_seq = False
                categ.number_next = False

    def _set_number_seq(self):
        for categ in self:
            self.env["ir.sequence"].search(
                [("code", "=", f"product.{categ.complete_code}")]
            ).write({"number_next": categ.number_next})

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
    _order = "id desc"

    default_code = fields.Char(
        "Internal Reference",
        compute="_compute_default_code",
        store=True,
        index=True,
        inverse="_validate_default_code",
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

    @api.constrains("default_code")
    def _validate_default_code(self):
        for product in self:
            if self.search_count([("default_code", "=", product.default_code)]) > 1:
                raise ValidationError(_("Default code is duplicate"))


class ProductTemplate(models.Model):
    _inherit = "product.template"
    _order = "id desc"

    @api.model
    def default_get(self, default_fields):
        values = super().default_get(default_fields)
        values["type"] = "product"
        return values

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

    def _set_default_code(self):
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.default_code = template.product_variant_ids[0].default_code


class ProductAttribute(models.Model):
    _name = "product.attribute"
    _inherit = "product.attribute"

    create_variant = fields.Selection(
        [("always", "Instantly"), ("dynamic", "Dynamically"), ("no_variant", "Never")],
        default="dynamic",
        string="Variants Creation Mode",
        help="""- Instantly: All possible variants are created as soon as the attribute and its values are added to a product.
        - Dynamically: Each variant is created only when its corresponding attributes and values are added to a sales order.
        - Never: Variants are never created for the attribute.
        Note: the variants creation mode cannot be changed once the attribute is used on at least one product.""",
        required=True,
    )
