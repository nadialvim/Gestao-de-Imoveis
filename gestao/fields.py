import inspect
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Callable, Optional


@dataclass
class Badge:
    """Valor de coluna exibido como etiqueta colorida (cor = sufixo de classe Bootstrap)."""
    texto: str
    cor: str = "secondary"

    def __str__(self):
        return self.texto


@dataclass
class Field:
    name: str
    label: str
    # text, money, int, date, month, bool, select (id inteiro), multi (vários ids),
    # choice (texto), lista
    kind: str = "text"
    required: bool = True
    choices: Optional[Callable] = None  # select/choice: ([obj]) -> [(valor, rótulo)]
    default: Optional[object] = None
    wide: bool = False  # ocupa a linha inteira no formulário de 2 colunas
    extra: bool = False  # não é coluna do modelo (só alimenta validate/before_save)
    section: Optional[str] = None  # subtítulo exibido antes do campo no formulário

    def opcoes(self, obj=None):
        """Opções do select; a função de opções pode receber o objeto em edição."""
        if not self.choices:
            return []
        if inspect.signature(self.choices).parameters:
            return self.choices(obj)
        return self.choices()

    def parse(self, raw):
        if self.kind == "bool":
            return raw is not None
        if self.kind == "multi":
            ids = []
            for item in raw or []:
                if str(item).strip():
                    try:
                        ids.append(int(item))
                    except ValueError:
                        raise ValueError("valor inválido")
            ids = list(dict.fromkeys(ids))
            if not ids and self.required:
                raise ValueError("campo obrigatório")
            return ids
        if self.kind == "lista":
            from .services.unidades import parse_lista

            return parse_lista(raw)
        raw = (raw or "").strip()
        if not raw:
            if self.required:
                raise ValueError("campo obrigatório")
            return None
        try:
            if self.kind == "money":
                value = Decimal(raw.replace(".", "").replace(",", ".")
                                if "," in raw else raw)
                if value < 0:
                    raise ValueError("não pode ser negativo")
                return value
            if self.kind in ("int", "select"):
                return int(raw)
            if self.kind == "choice":
                if raw not in {str(v) for v, _ in self.opcoes()}:
                    raise ValueError("opção inválida")
                return raw
            if self.kind == "date":
                return date.fromisoformat(raw)
            if self.kind == "month":
                ano, mes = raw.split("-")
                return date(int(ano), int(mes), 1)
        except InvalidOperation:
            raise ValueError("valor inválido")
        except (TypeError, ValueError) as exc:
            msg = str(exc)
            raise ValueError(msg if msg in ("não pode ser negativo", "opção inválida")
                             else "valor inválido")
        return raw

    def to_input(self, value):
        """Converte o valor do objeto para string do <input>."""
        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            return [str(v) for v in value]
        if self.kind == "month":
            return value.strftime("%Y-%m")
        if self.kind == "date":
            return value.isoformat()
        if self.kind == "money":
            return f"{Decimal(value):.2f}"
        return str(value)


@dataclass
class Resource:
    slug: str
    model: type
    singular: str
    plural: str
    fields: list
    columns: list  # [(titulo, fn(obj) -> str)]
    order: Optional[Callable] = None  # () -> order_by clause(s)
    month_field: Optional[str] = None  # habilita filtro ?mes=YYYY-MM
    validate: Optional[Callable] = None  # (data, obj) -> [erros]
    new_defaults: Optional[Callable] = None  # () -> dict de valores iniciais
    # campos de formulário que não são colunas do modelo (ex.: lista de apartamentos)
    extra_fields: list = field(default_factory=list)
    after_save: Optional[Callable] = None  # (obj, dados) -> mensagem opcional (pós-commit)
    before_save: Optional[Callable] = None  # (obj, dados) -> None (antes do commit)
    # filtros da listagem: [(coluna, rótulo, [(valor, texto)])] via ?coluna=valor
    filters: list = field(default_factory=list)
    ficha: Optional[str] = None  # endpoint da ficha (detalhe); 1ª coluna vira link e vira destino
    destino: Optional[Callable] = None  # (obj, dados) -> url após salvar (substitui a lista)
    sem_modelo: bool = False  # formulário que só dispara before_save (não grava o objeto)
    lista: bool = True  # False = sem tela de listagem própria
    titulo_novo: Optional[str] = None  # título do formulário de criação
