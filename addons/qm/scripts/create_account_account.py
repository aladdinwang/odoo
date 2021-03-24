# 创建销售发票和采购发票
# odoo shell
import xmlrpc.client


password = "admin"
url = "http://localhost:8069"
username = "admin"

common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")


def odoo_shell_command():
    company = env["res.company"].browse(4)
    acc_templates = env["account.account.template"].browse([302, 303])

    chart = env["account.chart.template"].browse(7)

    template_vals = []
    for account_template in acc_templates:
        code_main = account_template.code and len(account_template.code) or 0
        code_digits = 6
        code_acc = account_template.code or ""
        if code_main > 0 and code_main <= code_digits:
            code_acc = str(code_acc) + (str("0" * (code_digits - code_main)))
        vals = chart._get_account_vals(company, account_template, code_acc, None)
        template_vals.append((account_template, vals))
    accounts = chart._create_records_with_xmlid(
        "account.account", template_vals, company
    )
    env.cr.commit()


def main():
    uid = common.authenticate("vgroups", username, password, {})


if "__main__" == __name__:
    main()
