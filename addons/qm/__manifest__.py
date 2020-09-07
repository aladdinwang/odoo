{
    "name": "QM",
    "version": "0.01",
    "category": "Sales/Sales",
    "depends": [
        "base",
        "mail",
        "uom",
        "sale",
        "sale_management",
        "account",
        "purchase",
        "l10n_cn_standard",
    ],
    "description": "专为荃玟定制",
    "data": [
        "data/tax.classification.csv",
        "data/product.category.csv",
        "data/ir.sequence.csv",
        "data/l10n_cn_chart_data.xml",
        "data/account.account.template.csv",
        "data/ir_sequence_data.xml",
        "data/account_tax_template_data.xml",
        "data/account_chart_template_data.xml",
        "views/product_views.xml",
        "views/res_partner_views.xml",
        "views/tax_views.xml",
        "views/purchase_views.xml",
        "views/account_move_views.xml",
        "views/sale_views.xml",
        "views/account_invoice_views.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
}
