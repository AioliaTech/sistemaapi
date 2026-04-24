"""
Fetchers package — Parsers individuais para cada fornecedor de dados de veículos.
"""

from typing import Any, Optional

from .base_parser import BaseParser
from .altimus_parser import AltimusParser
from .autocerto_parser import AutocertoParser
from .autoconf_parser import AutoconfParser
from .revendamais_parser import RevendamaisParser
from .fronteira_parser import FronteiraParser
from .revendapro_parser import RevendaproParser
from .clickgarage_parser import ClickGarageParser
from .simplesveiculo_parser import SimplesVeiculoParser
from .boom_parser import BoomParser
from .dsautoparser import DSAutoEstoqueParser
from .vitorioso_wordpress_parser import WordPressParser
from .bndv_parser import BndvParser
from .revendai_parser import RevendaiParser
from .comautoparser import ComautoParser1, ComautoParser2
from .revendaplus_parser import RevendaPlusParser
from .carburgo_parser import CarburgoParser
from .lojaconectada_parser import LojaConectadaParser
from .admycar_parser import AdmycarParser
from .autogestor_parser import AutogestorParser
from .netcar_parser import NetcarParser
from .revendai_telefones_parser import RevendaiTelefonesParser
from .itcar_parser import ItcarParser
from .diamond_parser import DiamondParser
from .covel_parser import CovelParser
from .ecosys_parser import EcosysParser
from .revendai_locadora_parser import RevendaiLocadoraParser
from .fordplus_parser import FordPlusParser

__all__ = [
    "BaseParser",
    "RevendaiParser",
    "RevendaiLocadoraParser",
    "RevendaiTelefonesParser",
    "AltimusParser",
    "AutocertoParser",
    "AutoconfParser",
    "RevendamaisParser",
    "FronteiraParser",
    "RevendaproParser",
    "ClickGarageParser",
    "SimplesVeiculoParser",
    "BoomParser",
    "DSAutoEstoqueParser",
    "BndvParser",
    "ComautoParser1",
    "ComautoParser2",
    "CarburgoParser",
    "WordPressParser",
    "RevendaPlusParser",
    "AdmycarParser",
    "AutogestorParser",
    "LojaConectadaParser",
    "NetcarParser",
    "ItcarParser",
    "DiamondParser",
    "CovelParser",
    "EcosysParser",
    "FordPlusParser",
    "get_parser_by_name",
]

# ─── Parser registry ──────────────────────────────────────────────────────────
# Mapa de nome de classe → classe do parser.
# Usado para recuperar a instância correta a partir do campo parser_used do cliente.

_PARSER_CLASSES = [
    RevendaiParser,
    RevendaiLocadoraParser,
    RevendaiTelefonesParser,
    AltimusParser,
    AutocertoParser,
    AutoconfParser,
    RevendamaisParser,
    FronteiraParser,
    RevendaproParser,
    ClickGarageParser,
    SimplesVeiculoParser,
    BoomParser,
    DSAutoEstoqueParser,
    BndvParser,
    ComautoParser1,
    ComautoParser2,
    RevendaPlusParser,
    CarburgoParser,
    WordPressParser,
    AdmycarParser,
    AutogestorParser,
    NetcarParser,
    LojaConectadaParser,
    ItcarParser,
    DiamondParser,
    CovelParser,
    EcosysParser,
    FordPlusParser,
]

PARSER_REGISTRY = {cls.__name__: cls for cls in _PARSER_CLASSES}


class _DefaultParser(BaseParser):
    """
    Parser de fallback retornado quando parser_used não está no registry.
    Usa todas as implementações padrão do BaseParser.
    """
    def can_parse(self, data: Any, url: str) -> bool:
        return False

    def parse(self, data: Any, url: str) -> list:
        return []


def get_parser_by_name(name: str) -> BaseParser:
    """
    Retorna uma instância do parser pelo nome da classe.
    Se o nome não for reconhecido, retorna _DefaultParser (implementações padrão).
    """
    cls = PARSER_REGISTRY.get(name or "")
    return cls() if cls else _DefaultParser()
