"""Organização das unidades de um prédio em andares (para o desenho do prédio)."""
import re


def ordem_natural(identificacao):
    """Chave de ordenação natural: 2 < 10 < 101 < A1 (números antes de textos)."""
    partes = re.split(r"(\d+)", str(identificacao))
    return [(0, int(t), "") if t.isdigit() else (1, 0, t.lower()) for t in partes if t]


def andar_do_apartamento(identificacao):
    """101 -> 1, 205 -> 2, 1204 -> 12 (tudo menos os 2 últimos dígitos). None se não seguir o padrão."""
    ident = str(identificacao).strip()
    if ident.isdigit() and len(ident) >= 3:
        return int(ident[:-2])
    return None


def montar_andares(imoveis):
    """Agrupa apartamentos por andar e lojas no térreo, do andar mais alto para o térreo.

    Cada item: {"rotulo", "tipo" ('andar' | 'terreo' | 'lojas' | 'outros'), "unidades"}.
    Apartamentos fora do padrão numérico vão para "Outros apartamentos". Vagas e casas não entram.
    """
    por_andar, lojas, outros = {}, [], []
    for i in imoveis:
        if i.tipo == "loja":
            lojas.append(i)
        elif i.tipo == "apartamento":
            andar = andar_do_apartamento(i.identificacao)
            if andar is None:
                outros.append(i)
            else:
                por_andar.setdefault(andar, []).append(i)

    def ordenar(unidades):
        return sorted(unidades, key=lambda u: ordem_natural(u.identificacao))

    andares = []
    for n in sorted((a for a in por_andar if a > 0), reverse=True):
        andares.append({"rotulo": f"{n}º andar", "tipo": "andar", "unidades": ordenar(por_andar[n])})
    if 0 in por_andar:
        andares.append({"rotulo": "Térreo", "tipo": "terreo", "unidades": ordenar(por_andar[0])})
    if lojas:
        andares.append({"rotulo": "Térreo — lojas", "tipo": "lojas", "unidades": ordenar(lojas)})
    if outros:
        andares.append({"rotulo": "Outros apartamentos", "tipo": "outros", "unidades": ordenar(outros)})
    return andares
