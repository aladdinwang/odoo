import functools
import io
import json
import logging
from itertools import count
import uuid
import werkzeug
import werkzeug.exceptions


from odoo import http
from odoo.http import (
    content_disposition,
    request,
    serialize_exception as _serialize_exception,
)
from odoo.tools.misc import xlsxwriter

_logger = logging.getLogger(__name__)


def serialize_exception(f):
    @functools.wraps(f)
    def wrap(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            _logger.exception("An exception occured during an http request")
            se = _serialize_exception(e)
            error = {"code": 200, "message": "Odoo Server Error", "data": se}
            return werkzeug.exceptions.InternalServerError(json.dumps(error))

    return wrap


class ExcelExport(http.Controller):
    @http.route("/qm/export/xlsx", type="http", auth="user")
    @serialize_exception
    def index(self, model, ids):
        headers = {
            "invoice_name": "单据号",
            "sale_order_name": "销售合同号",
            "partner_name": "客户名称",
            "vat": "客户税号",
            "partner_address": "注册地址电话",
            "acc_number": "开户行账号",
            "sku_code": "商户Sku号",
            "product_name": "商品名称",
            "sku_variant": "规格",
            "quantity": "数量",
            "price": "含税单价",
            "amount": "含税总价",
            "uom": "单位",
            "tax_classification_code9": "税收编码9位",
            "tax_classification_code18": "税收编码18位",
            "tax_classification_name": "票面简称",
        }

        def _writer_row_dict(worksheet, row_index_it, data):
            row = [data.get(k) for k in headers]
            row_index = next(row_index_it)
            for i, value in enumerate(row):
                if isinstance(value, (int, float)):
                    worksheet.write_number(row_index, i, value)
                else:
                    worksheet.write_string(row_index, i, value or "")

        def _get_acc_number(partner):
            if not partner.bank_ids:
                return ""

            return " ".join(
                (partner.bank_ids[0].bank_name, partner.bank_ids[0].acc_number)
            )

        def _get_sku_variant(product):
            ret = []
            for v in product.product_template_attribute_value_ids:
                ret.append(f"{v.product_attribute_value_id.name}")
            return " ".join(ret)

        row_index_it = count()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        worksheet = workbook.add_worksheet()

        _writer_row_dict(worksheet, row_index_it, headers)
        invoice_ids = list(map(int, ids.split(",")))
        for invoice in request.env["account.move"].browse(invoice_ids):
            for line in invoice.invoice_line_ids:
                # if not (line.price_total > 0 and line.price_unit == line.price_total and not line.tax_line_id):
                #     continue

                row = {
                    "invoice_name": invoice.name,
                    "sale_order_name": invoice.invoice_origin,
                    "partner_name": line.partner_id.account_name,
                    "vat": line.partner_id.vat,
                    "partner_address": " ".join(
                        map(
                            str,
                            [
                                line.partner_id.account_address,
                                line.partner_id.account_phone,
                            ],
                        )
                    ),
                    "acc_number": _get_acc_number(line.partner_id),
                    "sku_code": line.product_id.code,
                    "product_name": line.product_id.product_tmpl_id.name,
                    "sku_variant": _get_sku_variant(line.product_id),
                    "quantity": line.quantity,
                    "price": line.price_unit,
                    "amount": line.price_unit * line.quantity,
                    "uom": line.product_uom_id.name,
                    "tax_classification_code9": line.product_id.product_tmpl_id.categ_id.tax_classification_id.code,
                    "tax_classification_code18": line.product_id.product_tmpl_id.categ_id.tax_classification_id.code18,
                    "tax_classification_name": line.product_id.product_tmpl_id.categ_id.tax_classification_id.name,
                }
                _writer_row_dict(worksheet, row_index_it, row)

        workbook.close()
        return request.make_response(
            output.getvalue(),
            headers=[
                ("Content-Disposition", content_disposition(self.filename(model))),
                ("Content-Type", self.content_type),
            ],
        )

    @property
    def content_type(self):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    def filename(self, base):
        return uuid.uuid4().hex + ".xlsx"
