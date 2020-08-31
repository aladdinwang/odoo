from odoo import api, fields, models, _
from odoo.osv import expression


class TaxClassification(models.Model):
    _name = "tax.classification"
    _description = "Tax Classification"

    name = fields.Char("Name", index=True, required=True)
    code = fields.Char("Code", index=True)
    code18 = fields.Char("Code18", index=True)

    def name_get(self):
        self.browse(self.ids).read(["name", "code"])
        return [
            (
                record.id,
                "%s%s" % (record.code and "[%s] " % record.code or "", record.name),
            )
            for record in self
        ]

    @api.model
    def _name_search(
        self, name="", args=None, operator="ilike", limit=100, name_get_uid=None
    ):
        if not args:
            args = []

        if name:
            positive_operators = ["=", "ilike", "=ilike", "like", "=like"]
            classification_ids = []
            if operator in positive_operators:
                classification_ids = self._search(
                    [("code", "=", name)] + args,
                    limit=limit,
                    access_rights_uid=name_get_uid,
                )
                if not classification_ids:
                    classification_ids = self._search(
                        [("name", "=", name)] + args,
                        limit=limit,
                        access_rights_uid=name_get_uid,
                    )

            if (
                not classification_ids
                and operator not in expression.NEGATIVE_TERM_OPERATORS
            ):
                classification_ids = self._search(
                    args + [("code", operator, name)], limit=limit
                )
                if not limit or len(classification_ids) < limit:
                    limit2 = (limit - len(classification_ids)) if limit else False
                    classification2_ids = self._search(
                        args
                        + [
                            ("name", operator, name),
                            ("id", "not in", classification_ids),
                        ],
                        limit=limit2,
                        access_rights_uid=name_get_uid,
                    )
                    classification_ids.extend(classification2_ids)
            elif (
                not classification_ids
                and operator in expression.NEGATIVE_TERM_OPERATORS
            ):
                domain = expression.OR(
                    [
                        ["&", ("code", operator, name), ("name", operator, name)],
                        ["&", ("code", "=", False), ("name", operator, name)],
                    ]
                )
                domain = expression.AND([args, domain])
                classification_ids = self._search(
                    domain, limit=limit, access_rights_uid=name_get_uid
                )
        else:
            classification_ids = self._search(
                args, limit=limit, access_rights_uid=name_get_uid
            )
        return models.lazy_name_get(
            self.browse(classification_ids).with_user(name_get_uid)
        )
