"""
Parser específico para EcosysAuto (ecosysauto.com.br) — feed Atom/Google Base
"""

from .base_parser import BaseParser
from typing import Dict, List, Any


class EcosysParser(BaseParser):
    """Parser para dados do EcosysAuto (feed XML Atom com namespace Google Base)"""

    def can_parse(self, data: Any, url: str) -> bool:
        """Verifica se pode processar dados do EcosysAuto"""
        if url and "ecosysauto.com.br" in url.lower():
            return True

        # Detecta pela estrutura: dict com chave 'feed' contendo 'entry'
        if isinstance(data, dict):
            feed = data.get("feed", {})
            if isinstance(feed, dict) and "entry" in feed:
                return True

        return False

    def parse(self, data: Any, url: str) -> List[Dict]:
        """Processa dados do EcosysAuto"""
        feed = data.get("feed", {})
        entries = feed.get("entry", [])

        # Normaliza para lista se vier um único entry como dict
        if isinstance(entries, dict):
            entries = [entries]

        if not isinstance(entries, list):
            return []

        parsed_vehicles = []

        for entry in entries:
            if not isinstance(entry, dict):
                continue

            # ID: valor após o '_' em g:id (ex: "22170_30130" → "30130")
            id_raw = entry.get("g:id", "")
            id_final = self._extrair_id(id_raw)

            # Modelo: g:title
            modelo = (entry.get("g:title") or "").strip()

            # Descrição: g:description
            descricao = (entry.get("g:description") or "").strip() or None

            # Preço: g:price — remove ".00" no final
            preco = self._parse_preco(entry.get("g:price"))

            # Fotos: g:image_link + g:additional_image_link
            fotos = self._extrair_fotos(entry)

            parsed = self.normalize_vehicle({
                "id": id_final,
                "tipo": "carro",
                "titulo": modelo,
                "versao": None,
                "marca": (entry.get("g:brand") or "").strip() or None,
                "modelo": modelo,
                "observacao": descricao,
                "ano": None,
                "ano_fabricacao": None,
                "km": None,
                "cor": None,
                "combustivel": None,
                "cambio": None,
                "motor": None,
                "portas": None,
                "categoria": None,
                "cilindrada": None,
                "preco": preco,
                "opcionais": "",
                "fotos": fotos,
            })

            parsed_vehicles.append(parsed)

        return parsed_vehicles

    # ── Interface de formatação ───────────────────────────────────────────────

    def transform(self, vehicle: dict) -> dict:
        """Reduz o schema para campos relevantes do Ecosys."""
        return {
            "id": vehicle.get("id"),
            "modelo": vehicle.get("modelo"),
            "descricao": vehicle.get("observacao"),
            "preco": vehicle.get("preco"),
            "fotos": vehicle.get("fotos", []),
        }

    def format_vehicle_csv(self, vehicle: dict) -> str:
        """CSV mínimo Ecosys: id, modelo, preco."""
        def sv(v):
            return "" if v is None else str(v)
        return ",".join([
            sv(vehicle.get("id")),
            sv(vehicle.get("modelo")),
            sv(vehicle.get("preco")),
        ])

    def get_instructions(self) -> str:
        return (
            "### COMO LER O JSON de 'BuscaEstoque' — EcosysAuto\n"
            "Cada item contém os seguintes campos:\n"
            "id, modelo, preco\n"
            "- id: identificador único do veículo\n"
            "- modelo: nome do modelo do veículo\n"
            "- preco: preço de venda em reais\n"
        )

    # ── Métodos de parsing ────────────────────────────────────────────────────

    def _extrair_id(self, id_raw: str) -> str:
        """Extrai o ID após o '_' (ex: '22170_30130' → '30130')"""
        if not id_raw:
            return ""
        id_str = str(id_raw).strip()
        if "_" in id_str:
            return id_str.split("_")[-1]
        return id_str

    def _parse_preco(self, price_raw: Any) -> float:
        """Converte preço removendo '.00' e convertendo para float"""
        if not price_raw:
            return 0.0
        price_str = str(price_raw).strip()
        # Remove sufixo de moeda se houver (ex: "41000.00 BRL")
        price_str = price_str.split()[0]
        return self.converter_preco(price_str)

    def _extrair_fotos(self, entry: Dict) -> List[str]:
        """Extrai image_link e additional_image_link do entry"""
        fotos = []

        # Imagem principal
        img_principal = entry.get("g:image_link")
        if img_principal and isinstance(img_principal, str) and img_principal.strip():
            fotos.append(img_principal.strip())

        # Imagens adicionais (pode ser string única ou lista)
        adicionais = entry.get("g:additional_image_link", [])
        if isinstance(adicionais, str):
            adicionais = [adicionais]
        if isinstance(adicionais, list):
            for url in adicionais:
                if isinstance(url, str) and url.strip() and url.strip() not in fotos:
                    fotos.append(url.strip())

        return fotos
