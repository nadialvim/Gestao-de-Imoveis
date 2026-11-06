import re

LIMITE = 500
_FAIXA = re.compile(r"^(\d+)\s*-\s*(\d+)$")


def parse_lista(texto, limite=LIMITE):
    """Converte '101, 102\\n201-203' em ['101', '102', '201', '202', '203'].

    Separadores: vírgula, ponto e vírgula ou quebra de linha. Faixas numéricas
    ('101-110') são expandidas; identificações com letras ('G2-05') ficam como estão.
    Duplicados são removidos mantendo a ordem. Levanta ValueError se inválido.
    """
    itens = []
    for token in re.split(r"[,;\n\r]+", texto or ""):
        token = token.strip()
        if not token:
            continue
        m = _FAIXA.match(token)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a > b:
                raise ValueError(f"faixa inválida: {token}")
            if b - a + 1 > limite:
                raise ValueError(f"faixa muito grande (máx. {limite}): {token}")
            itens.extend(str(n) for n in range(a, b + 1))
        else:
            if len(token) > 30:
                raise ValueError(f"identificação muito longa: {token[:20]}...")
            itens.append(token)
    unicos = list(dict.fromkeys(itens))
    if len(unicos) > limite:
        raise ValueError(f"máximo de {limite} unidades por vez")
    return unicos
