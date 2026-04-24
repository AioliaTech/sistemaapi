"""
Parser específico para Covel (covel.eco.br) — motos elétricas
"""

import re
from html.parser import HTMLParser
from .base_parser import BaseParser
from typing import Dict, List, Any, Optional


class _HTMLStripper(HTMLParser):
    """Remove tags HTML e decodifica entidades, deixando texto limpo."""

    def __init__(self):
        super().__init__()
        self._parts: List[str] = []

    def handle_data(self, data: str):
        stripped = data.strip()
        if stripped:
            self._parts.append(stripped)

    def get_text(self) -> str:
        return " ".join(self._parts)


def _limpar_html(html: str) -> str:
    """Remove tags HTML e retorna texto limpo."""
    if not html:
        return ""
    stripper = _HTMLStripper()
    stripper.feed(html)
    texto = stripper.get_text()
    # Remove espaços múltiplos
    texto = re.sub(r"\s{2,}", " ", texto).strip()
    return texto


class CovelParser(BaseParser):
    """Parser para dados do Covel (WooCommerce / covel.eco.br)"""

    def can_parse(self, data: Any, url: str) -> bool:
        """Verifica se pode processar dados do Covel"""
        if url and "covel.eco.br" in url.lower():
            return True

        # Detecta pela estrutura: lista de produtos WooCommerce com campo 'brands'
        if isinstance(data, list) and len(data) > 0:
            primeiro = data[0]
            if isinstance(primeiro, dict) and "brands" in primeiro and "images" in primeiro:
                return True

        return False

    def parse(self, data: Any, url: str) -> List[Dict]:
        """Processa dados do Covel"""
        if isinstance(data, dict):
            data = [data]

        if not isinstance(data, list):
            return []

        parsed_vehicles = []

        for v in data:
            if not isinstance(v, dict):
                continue

            # Ignora produtos não publicados
            if v.get("status") not in ("publish", "pending", None):
                continue

            # Marca: brands[0].name
            marca = self._extrair_marca(v.get("brands", []))

            # Modelo: campo 'name'
            modelo = (v.get("name") or "").strip()

            # Descrição: limpa HTML
            descricao = _limpar_html(v.get("description") or "")

            # Preço: usa sale_price se disponível, senão price
            preco = self.converter_preco(v.get("sale_price") or v.get("price"))

            # Fotos: images[].src
            fotos = self._extrair_fotos(v.get("images", []))

            # Combustível fixo: Elétrico
            combustivel = "Elétrico"

            # Tipo fixo: moto (produto de motos elétricas)
            tipo_final = "moto"

            # Categoria: tenta inferir pelo modelo
            cilindrada_final, categoria_final = self.inferir_cilindrada_e_categoria_moto(
                modelo, ""
            )

            parsed = self.normalize_vehicle({
                "id": str(v.get("id")) if v.get("id") is not None else None,
                "tipo": tipo_final,
                "titulo": f"{marca} {modelo}".strip() if marca else modelo,
                "versao": modelo,
                "marca": marca,
                "modelo": modelo,
                "ano": None,
                "ano_fabricacao": None,
                "km": None,
                "cor": None,
                "combustivel": combustivel,
                "observacao": descricao or None,
                "cambio": None,
                "motor": None,
                "portas": None,
                "categoria": categoria_final,
                "cilindrada": cilindrada_final,
                "preco": preco,
                "opcionais": "",
                "fotos": fotos,
            })

            parsed_vehicles.append(parsed)

        return parsed_vehicles

    def _extrair_marca(self, brands: Any) -> str:
        """Extrai o nome da primeira marca da lista brands"""
        if not brands or not isinstance(brands, list):
            return ""
        primeira = brands[0]
        if isinstance(primeira, dict):
            return (primeira.get("name") or "").strip()
        return ""

    # ── Interface de formatação ───────────────────────────────────────────────

    def transform(self, vehicle: dict) -> dict:
        """Reduz o schema para campos relevantes do Covel (motos elétricas)."""
        fotos = vehicle.get("fotos") or []
        return {
            "id": vehicle.get("id"),
            "marca": vehicle.get("marca"),
            "modelo": vehicle.get("modelo"),
            "descricao": vehicle.get("observacao"),
            "preco": vehicle.get("preco"),
            "foto": fotos[0] if fotos else None,
        }

    def format_vehicle_csv(self, vehicle: dict) -> str:
        """CSV mínimo Covel: id, marca, modelo, preco."""
        def sv(v):
            return "" if v is None else str(v)
        return ",".join([
            sv(vehicle.get("id")),
            sv(vehicle.get("marca")),
            sv(vehicle.get("modelo")),
            sv(vehicle.get("preco")),
        ])

    def get_instructions(self) -> str:
        return (
            "### COMO LER O JSON de 'BuscaEstoque' — Covel (motos elétricas)\n"
            "Cada item contém os seguintes campos:\n"
            "id, marca, modelo, preco\n"
            "- id: identificador único do produto\n"
            "- marca: fabricante da moto elétrica\n"
            "- modelo: nome completo do modelo\n"
            "- preco: preço de venda em reais\n"
        )

    # ── Métodos de parsing ────────────────────────────────────────────────────

    def _extrair_fotos(self, images: Any) -> List[str]:
        """Extrai URLs das imagens (campo src de cada objeto)"""
        if not images or not isinstance(images, list):
            return []

        fotos = []
        for img in images:
            if isinstance(img, dict):
                src = (img.get("src") or "").strip()
                if src and src not in fotos:
                    fotos.append(src)
        return fotos
