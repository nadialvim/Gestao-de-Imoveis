from dataclasses import dataclass
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
    kind: str = "text"  # text, textarea, money, int, date, month, select, bool
    required: bool = True
    choices: Optional[Callable] = None  # select: () -> [(id, label)]
    default: Optional[object] = None
    wide: bool = False  # ocupa a linha inteira no formulário de 2 colunas

    def parse(self, raw):
        if self.kind == "bool":
            return raw is not None
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
            if self.kind == "date":
                return date.fromisoformat(raw)
            if self.kind == "month":
                ano, mes = raw.split("-")
                return date(int(ano), int(mes), 1)
        except InvalidOperation:
            raise ValueError("valor inválido")
        except (TypeError, ValueError) as exc:
            raise ValueError(str(exc) if "negativo" in str(exc) else "valor inválido")
        return raw

    def to_input(self, value):
        """Converte o valor do objeto para string do <input>."""
        if value is None:
            return ""
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
