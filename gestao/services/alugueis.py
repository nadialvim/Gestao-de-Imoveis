"""Regras de aluguel compartilhadas por todas as telas (inquilino, imóvel, aluguel)."""
from ..extensions import db
from ..models import Contrato, Imovel


def erros_alvo(imovel_id):
    """Valor definido e disponibilidade do imóvel/vaga que será alugado."""
    alvo = db.session.get(Imovel, imovel_id)
    if alvo is None:
        return ["Imóvel não encontrado."]
    if not alvo.valor_aluguel_padrao:
        return [f"Defina o valor do aluguel de {alvo} antes de alugar."]
    atual = alvo.contrato_ativo
    if atual:
        return [f"Já está alugado: {alvo} ({atual.inquilino.nome}). "
                "Dê baixa no aluguel atual antes de alugar novamente."]
    return []


def erros_periodo(inicio, fim, dia):
    erros = []
    if not inicio or not fim:
        erros.append("Informe o início e o fim do aluguel.")
    elif fim < inicio:
        erros.append("A data final não pode ser anterior à inicial.")
    if not dia or not 1 <= dia <= 31:
        erros.append("Dia de vencimento deve estar entre 1 e 31.")
    return erros


def validar_alugueis(imovel_ids, inicio, fim, dia):
    """Erros para alugar uma lista de imóveis/vagas no mesmo período."""
    erros = erros_periodo(inicio, fim, dia)
    if not erros:
        for imovel_id in imovel_ids:
            erros.extend(erros_alvo(imovel_id))
    return erros


def criar_alugueis(inquilino, imovel_ids, inicio, fim, dia):
    """Cria um aluguel (contrato) por imóvel/vaga, com o valor cadastrado no imóvel.
    O inquilino precisa já estar na sessão (com id após flush)."""
    criados = []
    for imovel_id in imovel_ids:
        alvo = db.session.get(Imovel, imovel_id)
        c = Contrato(inquilino_id=inquilino.id, imovel_id=imovel_id, data_inicio=inicio,
                     data_fim=fim, dia_vencimento=dia, valor_mensal=alvo.valor_aluguel_padrao,
                     ativo=True)
        db.session.add(c)
        criados.append(c)
    return criados


def dar_baixa(contrato, data):
    """Encerra o aluguel (devolução). Retorna mensagem de erro ou None."""
    if not contrato.ativo:
        return "Este aluguel já foi encerrado."
    if data is None:
        return "Informe a data de devolução."
    if data < contrato.data_inicio:
        return "A devolução não pode ser anterior ao início do aluguel."
    contrato.ativo = False
    contrato.encerrado_em = data
    db.session.commit()
    return None


def debito_do_inquilino(inquilino_id):
    """Total e meses em débito de um inquilino (None se estiver em dia)."""
    from . import relatorio

    for item in relatorio.debitos()["inquilinos"]:
        if item["inquilino"].id == inquilino_id:
            return item
    return None
