"""
base_parser.py — Classe base para todos os parsers de veículos.
Define a interface de parsing E a interface de formatação de endpoints.
"""

import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from unidecode import unidecode

from vehicle_mappings import (
    MAPEAMENTO_CATEGORIAS,
    MAPEAMENTO_MOTOS,
    OPCIONAL_CHAVE_HATCH,
)
from .vehicle_categorizer import VehicleCategorizer


# ─── Opcionais helpers ────────────────────────────────────────────────────────
# Usados pelos formatadores CSV dos parsers.

OPCIONAIS_MAP = {
    1: ["ar-condicionado", "ar condicionado", "arcondicionado", "ar-condiciona", "ar condiciona"],
    2: ["airbag", "air bag", "air-bag"],
    3: ["vidros eletricos", "vidros elétricos", "vidro eletrico", "vidro elétrico", "vidros eletrico"],
    4: ["abs"],
    5: ["direcao hidraulica", "direção hidráulica", "direcao hidraulica", "dir hidraulica", "dir. hidraulica"],
    6: ["direcao eletrica", "direção elétrica", "direcao eletrica", "dir eletrica", "dir. eletrica"],
    7: ["7 lugar", "7 lugares", "sete lugar", "sete lugares"],
}


def _normalizar_opcional(texto: str) -> str:
    if not texto:
        return ""
    texto = unidecode(str(texto)).lower()
    texto = texto.replace("-", " ").replace(".", "")
    return " ".join(texto.split()).strip()


def opcionais_para_codigos(opcionais_str: str) -> List[int]:
    """Converte string de opcionais para lista de códigos numéricos."""
    if not opcionais_str:
        return []
    codigos = set()
    for opcional in [op.strip() for op in str(opcionais_str).split(",")]:
        opcional_norm = _normalizar_opcional(opcional)
        if not opcional_norm:
            continue
        for codigo, variacoes in OPCIONAIS_MAP.items():
            for variacao in variacoes:
                if opcional_norm == _normalizar_opcional(variacao) or _normalizar_opcional(variacao) in opcional_norm:
                    codigos.add(codigo)
                    break
    return sorted(codigos)


# ─── Instrução padrão ─────────────────────────────────────────────────────────

_DEFAULT_INSTRUCTION = (
    "### COMO LER O JSON de 'BuscaEstoque' (CRUCIAL — leia cada linha com atenção)\n"
    "- Para motocicletas (se o segundo valor no JSON for 'moto'):\n"
    "Código ID, tipo (moto), marca, modelo, versão, cor, ano, quilometragem, combustível, cilindrada, preço\n"
    "- Para carros (se o segundo valor no JSON for 'carro'):\n"
    "Código ID, tipo (carro), marca, modelo, versão, cor, ano, quilometragem, combustível, câmbio, motor, portas, preço, [opcionais]\n\n"
    "- Para os opcionais dos carros, alguns números podem aparecer. Aqui está o significado de cada número:\n"
    "1 - ar-condicionado\n2 - airbag\n3 - vidros elétricos\n4 - freios ABS\n"
    "5 - direção hidráulica\n6 - direção elétrica\n7 - sete lugares\n"
)


# ─── Base parser ──────────────────────────────────────────────────────────────


class BaseParser(ABC):
    """Classe base abstrata para todos os parsers de veículos."""

    # ── Interface obrigatória ─────────────────────────────────────────────────

    @abstractmethod
    def can_parse(self, data: Any, url: str) -> bool:
        """Retorna True se este parser reconhece os dados da URL."""
        pass

    @abstractmethod
    def parse(self, data: Any, url: str) -> List[Dict]:
        """Processa os dados e retorna lista de veículos normalizados."""
        pass

    # ── Interface de formatação de endpoints ──────────────────────────────────
    # Todos os parsers herdam as implementações padrão abaixo.
    # Sobrescreva apenas o que for diferente para o seu parser.

    def transform(self, vehicle: dict) -> dict:
        """
        Transformação aplicada a cada veículo antes de ser servido pela API.
        Padrão: sem alteração (retorna o veículo como está).
        Sobrescreva para remapear campos, reduzir schema, etc.
        """
        return vehicle

    def format_vehicle_csv(self, vehicle: dict) -> str:
        """
        Serializa um veículo para linha CSV usada no endpoint /list.
        Padrão: schema completo carro/moto com opcionais como códigos.
        Sobrescreva para adicionar/remover campos específicos do parser.
        """
        tipo = (vehicle.get("tipo") or "").lower()

        def sv(v):
            return "" if v is None else str(v)

        codigos = opcionais_para_codigos(vehicle.get("opcionais", ""))
        codigos_fmt = f"[{','.join(map(str, codigos))}]" if codigos else "[]"

        if "moto" in tipo:
            return ",".join([
                sv(vehicle.get("id")),
                sv(vehicle.get("tipo")),
                sv(vehicle.get("marca")),
                sv(vehicle.get("modelo")),
                sv(vehicle.get("versao")),
                sv(vehicle.get("cor")),
                sv(vehicle.get("ano")),
                sv(vehicle.get("km")),
                sv(vehicle.get("combustivel")),
                sv(vehicle.get("cilindrada")),
                sv(vehicle.get("preco")),
            ])
        else:
            return ",".join([
                sv(vehicle.get("id")),
                sv(vehicle.get("tipo")),
                sv(vehicle.get("marca")),
                sv(vehicle.get("modelo")),
                sv(vehicle.get("versao")),
                sv(vehicle.get("cor")),
                sv(vehicle.get("ano")),
                sv(vehicle.get("km")),
                sv(vehicle.get("combustivel")),
                sv(vehicle.get("cambio")),
                sv(vehicle.get("motor")),
                sv(vehicle.get("portas")),
                sv(vehicle.get("preco")),
                codigos_fmt,
            ])

    def format_list(self, vehicles: list) -> dict:
        """
        Constrói a estrutura do endpoint /list para a lista de veículos.
        Padrão:
          - Se algum veículo tiver 'localizacao': agrupa por localização → categoria.
          - Caso contrário: agrupa por categoria.
          - Veículos sem categoria vão para 'NÃO MAPEADOS'.
        Sobrescreva para agrupamentos especiais (ex: ESTOQUE/REPASSE).
        """
        has_localizacao = any(
            v.get("localizacao") and v.get("localizacao") not in ["", "None", None]
            for v in vehicles
        )

        if has_localizacao:
            return self._format_by_localizacao(vehicles)
        else:
            return self._format_by_categoria(vehicles)

    def get_instructions(self) -> str:
        """
        Texto de instrução para a chave 'instruction' no endpoint /list.
        Destinado a consumidores de IA. Padrão: instrução genérica carro/moto.
        Sobrescreva para personalizar por parser.
        """
        return _DEFAULT_INSTRUCTION

    # ── Helpers de formatação (usados por format_list e subclasses) ───────────

    def _format_by_categoria(self, vehicles: list) -> dict:
        """Agrupa veículos por categoria em CSV."""
        categorized: dict = {}
        nao_mapeados: list = []
        for v in vehicles:
            categoria = v.get("categoria")
            csv_line = self.format_vehicle_csv(v)
            if not categoria or categoria in ["", "None", None]:
                nao_mapeados.append(csv_line)
            else:
                key = categoria.strip().title()
                categorized.setdefault(key, []).append(csv_line)
        result = {k: categorized[k] for k in sorted(categorized)}
        if nao_mapeados:
            result["NÃO MAPEADOS"] = nao_mapeados
        return result

    def _format_by_localizacao(self, vehicles: list) -> dict:
        """Agrupa veículos por localização, depois por categoria."""
        loc_dict: dict = {}
        for v in vehicles:
            loc = v.get("localizacao") or "SEM LOCALIZAÇÃO"
            if loc in ["", "None"]:
                loc = "SEM LOCALIZAÇÃO"
            loc_dict.setdefault(loc, {"categorias": {}, "nao_mapeados": []})

            categoria = v.get("categoria")
            csv_line = self.format_vehicle_csv(v)
            if not categoria or categoria in ["", "None", None]:
                loc_dict[loc]["nao_mapeados"].append(csv_line)
            else:
                key = categoria.strip().title()
                loc_dict[loc]["categorias"].setdefault(key, []).append(csv_line)

        result = {}
        for loc in sorted(loc_dict):
            result[loc] = {
                k: loc_dict[loc]["categorias"][k]
                for k in sorted(loc_dict[loc]["categorias"])
            }
            if loc_dict[loc]["nao_mapeados"]:
                result[loc]["NÃO MAPEADOS"] = loc_dict[loc]["nao_mapeados"]
        return result

    # ── Utilitários compartilhados por todos os parsers ───────────────────────

    @staticmethod
    def extract_motor_from_version(versao: str) -> Optional[str]:
        """
        Extrai o motor da string de versão via regex numérica (ex: '1.0', '2.0T').
        Único lugar para esta lógica — substitui as ~13 cópias espalhadas nos parsers.
        """
        if not versao:
            return None
        match = re.search(r'\b(\d+\.\d+)\b', str(versao))
        return match.group(1) if match else None

    def _extract_motor_from_version(self, versao: str) -> Optional[str]:
        """Alias para extract_motor_from_version — mantém compatibilidade com call sites existentes."""
        return self.extract_motor_from_version(versao)

    def _extract_motor_info(self, versao: str) -> Optional[str]:
        """Alias para extract_motor_from_version — variante usada em alguns parsers."""
        return self.extract_motor_from_version(versao)

    def normalize_vehicle(self, vehicle: Dict) -> Dict:
        """Normaliza um veículo para o schema padrão de 25 campos."""
        fotos = vehicle.get("fotos", [])
        vehicle["fotos"] = self.normalize_fotos(fotos)

        tipo = vehicle.get("tipo", "")

        # ── Categorização de carros: 3 etapas via VehicleCategorizer ────────
        # Parsers atualizados definem vehicle["body_style_carga"] com o valor
        #   raw da fonte → VehicleCategorizer sempre roda (Etapa 1 disponível).
        # Parsers legados (sem body_style_carga) que já setaram categoria:
        #   respeitamos o que definiram durante a transição.
        # Parsers legados com categoria vazia/None: VehicleCategorizer roda
        #   pelas Etapas 2 e 3.
        if tipo != "moto":
            categoria_atual = vehicle.get("categoria")
            tem_body_style  = bool(vehicle.get("body_style_carga"))

            if tem_body_style or not categoria_atual or categoria_atual in ["", "Não informado"]:
                try:
                    if not hasattr(self, "categorizer"):
                        self.categorizer = VehicleCategorizer()
                    categoria_inferida = self.categorizer.categorize(vehicle)
                    if categoria_inferida:
                        vehicle["categoria"] = categoria_inferida
                except Exception as e:
                    print(f"[WARN] Erro ao categorizar veículo {vehicle.get('id')}: {e}")

        return {
            "id": vehicle.get("id"),
            "tipo": vehicle.get("tipo"),
            "titulo": vehicle.get("titulo"),
            "versao": vehicle.get("versao"),
            "marca": vehicle.get("marca"),
            "modelo": vehicle.get("modelo"),
            "observacao": vehicle.get("observacao"),
            "ano": vehicle.get("ano"),
            "ano_fabricacao": vehicle.get("ano_fabricacao"),
            "km": vehicle.get("km"),
            "cor": vehicle.get("cor"),
            "combustivel": vehicle.get("combustivel"),
            "cambio": vehicle.get("cambio"),
            "motor": vehicle.get("motor"),
            "portas": vehicle.get("portas"),
            "categoria": vehicle.get("categoria"),
            "cilindrada": vehicle.get("cilindrada"),
            "preco": vehicle.get("preco", 0.0),
            "valor_troca": vehicle.get("valor_troca"),
            "blindado": vehicle.get("blindado"),
            "opcionais": vehicle.get("opcionais", ""),
            "localizacao": vehicle.get("localizacao"),
            "fotos": vehicle.get("fotos", []),
            "plano_start": vehicle.get("plano_start"),
            "plano_drive": vehicle.get("plano_drive"),
            "plano_km_livre": vehicle.get("plano_km_livre"),
            "repasse": vehicle.get("repasse"),
        }

    def normalize_fotos(self, fotos_data: Any) -> List[str]:
        """Normaliza diferentes estruturas de fotos para lista simples de URLs."""
        if not fotos_data:
            return []

        result = []

        def extract_url(item):
            if isinstance(item, str):
                return item.strip()
            if isinstance(item, dict):
                for key in ["url", "URL", "src", "IMAGE_URL", "path", "link", "href"]:
                    if key in item and item[key]:
                        url = str(item[key]).strip()
                        return url.split("?")[0] if "?" in url else url
            return None

        def process_item(item):
            if isinstance(item, str):
                url = extract_url(item)
                if url:
                    result.append(url)
            elif isinstance(item, list):
                for subitem in item:
                    process_item(subitem)
            elif isinstance(item, dict):
                url = extract_url(item)
                if url:
                    result.append(url)

        if isinstance(fotos_data, list):
            for item in fotos_data:
                process_item(item)
        else:
            process_item(fotos_data)

        seen = set()
        normalized = []
        for url in result:
            if url and url not in seen:
                seen.add(url)
                normalized.append(url)
        return normalized

    def normalizar_texto(self, texto: str) -> str:
        """Normaliza texto para comparação: remove acentos, especiais, lowercase."""
        if not texto:
            return ""
        texto_norm = unidecode(str(texto)).lower()
        texto_norm = re.sub(r"[-_./]", " ", texto_norm)
        texto_norm = re.sub(r"[^a-z0-9\s]", "", texto_norm)
        return re.sub(r"\s+", " ", texto_norm).strip()

    def definir_categoria_veiculo(
        self, modelo: str, opcionais: str = "", version: str = ""
    ) -> Optional[str]:
        """
        [DEPRECATED] Não chamar diretamente nos parsers.
        A categorização agora é feita pelo VehicleCategorizer via normalize_vehicle().
        Parsers devem definir vehicle["body_style_carga"] com o valor raw da fonte.

        Define categoria por modelo usando scoring de palavras.
        Hierarquia: 'hatch'/'sedan' no modelo → mapeamento por score → None.
        """
        if not modelo:
            return None

        modelo_norm = self.normalizar_texto(modelo)

        if "hatch" in modelo_norm:
            return "Hatch"
        if "sedan" in modelo_norm:
            return "Sedan"

        matches = []
        for modelo_mapeado, categoria_result in MAPEAMENTO_CATEGORIAS.items():
            modelo_mapeado_norm = self.normalizar_texto(modelo_mapeado)
            if modelo_mapeado_norm in modelo_norm:
                palavras_match = sum(
                    1 for p in modelo_mapeado_norm.split() if p in modelo_norm.split()
                )
                score = (palavras_match * 100) + len(modelo_mapeado_norm)
                matches.append({"categoria": categoria_result, "score": score})

        if matches:
            matches.sort(key=lambda x: x["score"], reverse=True)
            categoria = matches[0]["categoria"]
            if categoria == "hatch,sedan":
                opcionais_norm = self.normalizar_texto(opcionais)
                opcional_chave_norm = self.normalizar_texto(OPCIONAL_CHAVE_HATCH)
                return "Hatch" if opcional_chave_norm in opcionais_norm else "Sedan"
            return categoria

        return None

    def inferir_cilindrada_e_categoria_moto(
        self, modelo: str, versao: str = ""
    ):
        """
        Infere cilindrada e categoria para motos pelo modelo e versão.
        Retorna tupla (cilindrada, categoria).
        """
        def buscar_no_texto(texto: str):
            if not texto:
                return None, None
            texto_norm = self.normalizar_texto(texto)

            if texto_norm in MAPEAMENTO_MOTOS:
                return MAPEAMENTO_MOTOS[texto_norm]

            matches = []
            for modelo_mapeado, (cilindrada, categoria) in MAPEAMENTO_MOTOS.items():
                modelo_mapeado_norm = self.normalizar_texto(modelo_mapeado)
                if modelo_mapeado_norm in texto_norm:
                    matches.append((modelo_mapeado_norm, cilindrada, categoria, len(modelo_mapeado_norm)))
                modelo_sem_espaco = modelo_mapeado_norm.replace(" ", "")
                if modelo_sem_espaco in texto_norm:
                    matches.append((modelo_sem_espaco, cilindrada, categoria, len(modelo_sem_espaco)))
            if matches:
                matches.sort(key=lambda x: x[3], reverse=True)
                return matches[0][1], matches[0][2]
            return None, None

        cilindrada, categoria = buscar_no_texto(modelo)
        if not cilindrada and versao:
            cilindrada, categoria = buscar_no_texto(versao)
        if not cilindrada and versao:
            cilindrada, categoria = buscar_no_texto(f"{modelo} {versao}")
        return cilindrada, categoria

    def converter_preco(self, valor: Any) -> float:
        """Converte string de preço para float."""
        if not valor:
            return 0.0
        try:
            if isinstance(valor, (int, float)):
                return float(valor)
            valor_str = re.sub(r"[^\d,.]", "", str(valor)).replace(",", ".")
            parts = valor_str.split(".")
            if len(parts) > 2:
                valor_str = "".join(parts[:-1]) + "." + parts[-1]
            return float(valor_str) if valor_str else 0.0
        except (ValueError, TypeError):
            return 0.0
