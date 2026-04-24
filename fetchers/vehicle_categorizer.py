"""
VehicleCategorizer - Classe centralizada para categorização de veículos.

Hierarquia de 3 etapas (aplicada em TODOS os parsers via normalize_vehicle):

  Etapa 1 — Da carga:
    Lê vehicle["body_style_carga"] (valor RAW do XML/JSON definido pelo parser).
    Traduz via MAPEAMENTO_BODY_STYLE. Se mapear → usa (confia inclusive em Hatch/Sedan).

  Etapa 2 — Por modelo:
    Busca por modelo e versão no MAPEAMENTO_CATEGORIAS com scoring.
    Foco restrito: modelo → versao → modelo+versao. Sem ruído de texto livre.

  Etapa 3 — Busca ampla:
    Varre todos os campos de texto (titulo, observacao, opcionais, modelo, versao).
    Primeiro por palavras-chave explícitas, depois por scoring no mapeamento.

Cada parser deve:
  - Definir vehicle["body_style_carga"] = valor raw do campo de carroceria/body_style
    se existir na carga. Caso contrário, deixar sem definir (ou None).
  - NÃO chamar definir_categoria_veiculo() – a categorização é feita aqui.
"""

from typing import Dict, Optional
from vehicle_mappings import MAPEAMENTO_CATEGORIAS, MAPEAMENTO_BODY_STYLE, OPCIONAL_CHAVE_HATCH
from unidecode import unidecode
import re


class VehicleCategorizer:
    """
    Classe centralizada para categorização de veículos.
    Usa 3 etapas em ordem de prioridade e confiança.
    """

    def __init__(self):
        self.mapeamento = MAPEAMENTO_CATEGORIAS
        self.opcional_hatch = OPCIONAL_CHAVE_HATCH

    # ──────────────────────────────────────────────────────────────────────────
    # Método principal
    # ──────────────────────────────────────────────────────────────────────────

    def categorize(self, vehicle_data: Dict) -> Optional[str]:
        """
        Categoriza um veículo usando hierarquia de 3 etapas.

        Args:
            vehicle_data: Dicionário com dados do veículo. Campos relevantes:
                - body_style_carga: str  (valor RAW da fonte, para Etapa 1)
                - modelo:           str
                - versao:           str
                - titulo:           str
                - observacao:       str
                - opcionais:        str
                - portas:           int  (para resolver ambiguidade hatch/sedan)

        Returns:
            Categoria canônica (Hatch, Sedan, SUV, Caminhonete...) ou None.
        """

        # ── Etapa 1: valor direto da carga ────────────────────────────────────
        categoria = self._etapa1_da_carga(vehicle_data)
        if categoria:
            return categoria

        # ── Etapa 2: busca focada por modelo/versão ───────────────────────────
        categoria = self._etapa2_por_modelo(vehicle_data)
        if categoria:
            if categoria == "hatch,sedan":
                return self._resolve_ambiguous(vehicle_data)
            return categoria

        # ── Etapa 3: busca ampla em todos os campos de texto ──────────────────
        categoria = self._etapa3_busca_ampla(vehicle_data)
        if categoria:
            if categoria == "hatch,sedan":
                return self._resolve_ambiguous(vehicle_data)
            return categoria

        return None

    # ──────────────────────────────────────────────────────────────────────────
    # Etapa 1 — Da carga
    # ──────────────────────────────────────────────────────────────────────────

    def _etapa1_da_carga(self, vehicle_data: Dict) -> Optional[str]:
        """
        Usa o campo body_style_carga (definido pelo parser a partir do XML/JSON).
        Traduz via MAPEAMENTO_BODY_STYLE. Confia em todas as categorias, inclusive
        Hatch e Sedan, pois vieram explicitamente da fonte.
        """
        raw = vehicle_data.get("body_style_carga") or ""
        if not raw:
            return None

        raw_norm = self._normalize_text(raw)

        # Busca exata no mapeamento
        resultado = MAPEAMENTO_BODY_STYLE.get(raw_norm)
        if resultado:
            return resultado

        # Busca por substring (tolera variações menores)
        for chave, categoria in MAPEAMENTO_BODY_STYLE.items():
            if chave in raw_norm or raw_norm in chave:
                return categoria

        return None

    # ──────────────────────────────────────────────────────────────────────────
    # Etapa 2 — Por modelo/versão
    # ──────────────────────────────────────────────────────────────────────────

    def _etapa2_por_modelo(self, vehicle_data: Dict) -> Optional[str]:
        """
        Busca focada: modelo → versao → modelo+versao.
        Não inclui titulo nem observacao para evitar ruído de texto livre.
        """
        modelo = vehicle_data.get("modelo", "") or ""
        versao  = vehicle_data.get("versao",  "") or ""

        candidatos = [
            modelo,
            versao,
            f"{modelo} {versao}".strip(),
        ]

        for texto in candidatos:
            resultado = self._buscar_no_mapeamento(texto)
            if resultado:
                return resultado

        return None

    # ──────────────────────────────────────────────────────────────────────────
    # Etapa 3 — Busca ampla
    # ──────────────────────────────────────────────────────────────────────────

    def _etapa3_busca_ampla(self, vehicle_data: Dict) -> Optional[str]:
        """
        Varre todos os campos de texto:
          3a) Palavras-chave explícitas (HATCH, SUV, PICKUP, etc.)
          3b) Scoring no mapeamento usando titulo, observacao e texto completo.
        """
        titulo     = vehicle_data.get("titulo",     "") or ""
        modelo     = vehicle_data.get("modelo",     "") or ""
        versao     = vehicle_data.get("versao",     "") or ""
        observacao = vehicle_data.get("observacao", "") or ""
        opcionais  = vehicle_data.get("opcionais",  "") or ""

        texto_completo = " ".join([titulo, modelo, versao, observacao, opcionais]).upper()

        # ── 3a: palavras-chave (da mais específica para a mais genérica) ──────
        if "STATION WAGON" in texto_completo or " SW " in texto_completo:
            return "Station Wagon"
        if "PICK-UP" in texto_completo or "PICKUP" in texto_completo:
            return "Caminhonete"
        if "CONVERSIVEL" in texto_completo or "CABRIOLET" in texto_completo or "CABRIO" in texto_completo:
            return "Conversível"
        if "COUPE" in texto_completo or "COUPÉ" in texto_completo:
            return "Coupe"
        if "MINIVAN" in texto_completo:
            return "Minivan"
        if "FURGAO" in texto_completo or "FURGÃO" in texto_completo:
            return "Furgão"
        if "OFF-ROAD" in texto_completo or "OFFROAD" in texto_completo:
            return "Off-road"
        if "UTILITARIO" in texto_completo or "UTILITÁRIO" in texto_completo:
            return "Utilitário"
        if any(p in texto_completo for p in ["SUV", "SPORT UTILITY", "CROSSOVER"]):
            return "SUV"
        if "HATCHBACK" in texto_completo or "HATCH" in texto_completo:
            return "Hatch"
        if "SEDAN" in texto_completo:
            return "Sedan"

        # ── 3b: scoring no mapeamento com campos mais ricos ───────────────────
        candidatos_amplos = [
            titulo,
            observacao,
            f"{modelo} {versao} {titulo}".strip(),
        ]

        for texto in candidatos_amplos:
            resultado = self._buscar_no_mapeamento(texto)
            if resultado:
                return resultado

        return None

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers internos
    # ──────────────────────────────────────────────────────────────────────────

    def _buscar_no_mapeamento(self, texto: str) -> Optional[str]:
        """
        Busca no MAPEAMENTO_CATEGORIAS com scoring por palavras.
        Retorna a categoria de maior score, ou None.
        """
        if not texto:
            return None

        texto_norm = self._normalize_text(texto)
        if not texto_norm:
            return None

        matches = []
        for modelo_mapeado, categoria_result in self.mapeamento.items():
            modelo_mapeado_norm = self._normalize_text(modelo_mapeado)
            if modelo_mapeado_norm in texto_norm:
                palavras_mapeado = modelo_mapeado_norm.split()
                palavras_texto   = texto_norm.split()
                palavras_match   = sum(1 for p in palavras_mapeado if p in palavras_texto)
                score = (palavras_match * 100) + len(modelo_mapeado_norm)
                matches.append({"categoria": categoria_result, "score": score})

        if not matches:
            return None

        melhor = max(matches, key=lambda x: x["score"])
        return melhor["categoria"]

    def _resolve_ambiguous(self, vehicle_data: Dict) -> str:
        """
        Resolve a ambiguidade hatch/sedan quando o mapeamento retorna 'hatch,sedan'.
        Ordem de prioridade:
          1. Número de portas (5 → Hatch, 4 → Sedan)
          2. Presença do opcional-chave (limpador traseiro → Hatch)
          3. Palavra "SPORT" no modelo/titulo → Hatch
          4. Padrão → Sedan
        """
        portas    = vehicle_data.get("portas")
        opcionais = vehicle_data.get("opcionais", "") or ""
        modelo    = vehicle_data.get("modelo",    "") or ""
        titulo    = vehicle_data.get("titulo",    "") or ""

        if portas == 5:
            return "Hatch"
        if portas == 4:
            return "Sedan"

        if self.opcional_hatch and self.opcional_hatch.lower() in opcionais.lower():
            return "Hatch"

        texto_upper = f"{modelo} {titulo}".upper()
        if "SPORT" in texto_upper:
            return "Hatch"

        return "Sedan"

    def _normalize_text(self, texto: str) -> str:
        """Normaliza texto para comparação: remove acentos, separadores, lowercase."""
        if not texto:
            return ""
        texto_norm = unidecode(str(texto)).lower()
        texto_norm = re.sub(r'[-_./]', ' ', texto_norm)
        texto_norm = re.sub(r'[^a-z0-9\s]', '', texto_norm)
        texto_norm = re.sub(r'\s+', ' ', texto_norm).strip()
        return texto_norm
