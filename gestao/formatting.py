from decimal import Decimal

MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def brl(value):
    if value is None:
        return ""
    value = Decimal(value)
    s = f"{value:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def data_br(value):
    return value.strftime("%d/%m/%Y") if value else ""


def mes_br(value):
    return f"{MESES[value.month - 1]}/{value.year}" if value else ""


def register_filters(app):
    app.jinja_env.filters["brl"] = brl
    app.jinja_env.filters["data_br"] = data_br
    app.jinja_env.filters["mes_br"] = mes_br
