import calendar
from datetime import date


def parse_mes(valor):
    """'YYYY-MM' -> (ano, mes); inválido/ausente = mês atual."""
    try:
        ano, mes = (valor or "").split("-")
        ano, mes = int(ano), int(mes)
        if 1 <= mes <= 12 and 1900 <= ano <= 2200:
            return ano, mes
    except ValueError:
        pass
    hoje = date.today()
    return hoje.year, hoje.month


def intervalo_mes(ano, mes):
    ultimo = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, 1), date(ano, mes, ultimo)
