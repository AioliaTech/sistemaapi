"""
Parser específico para Diamond Veículos (diamondveiculos.net)
"""

from .base_parser import BaseParser
from typing import Dict, List, Any, Optional


class DiamondParser(BaseParser):
    """Parser para dados do Diamond Veículos"""

    def can_parse(self, data: Any, url: str) -> bool:
        """Verifica se pode processar dados do Diamond Veículos"""
        if url and "diamondveiculos" in url.lower():
            return True

        # Detecta pela estrutura do JSON (lista com campo "coverImage" e "manufacturer")
        if isinstance(data, list) and len(data) > 0:
            primeiro = data[0]
            if isinstance(primeiro, dict) and "coverImage" in primeiro and "manufacturer" in primeiro:
                return True

        return False

    def parse(self, data: Any, url: str) -> List[Dict]:
        """Processa dados do Diamond Veículos"""
        # Normaliza para lista se vier como dict
        if isinstance(data, dict):
            data = [data]

        if not isinstance(data, list):
            return []

        parsed_vehicles = []

        for v in data:
            if not isinstance(v, dict):
                continue

            marca = (v.get("manufacturer") or "").strip()
            nome_completo = (v.get("name") or "").strip()

            # Extrai modelo base (primeira palavra do nome)
            modelo = self._extrair_modelo(nome_completo)

            # Processa opcionais
            opcionais_str = self._parse_opcionais(v.get("optionals", []))

            # Determina tipo (moto ou carro) pelo nome/marca
            is_moto = self._detectar_moto(marca, nome_completo)

            if is_moto:
                cilindrada_final, categoria_final = self.inferir_cilindrada_e_categoria_moto(
                    modelo, nome_completo
                )
                tipo_final = "moto"
            else:
                # Sem campo de carroceria na carga — VehicleCategorizer usa Etapas 2 e 3
                categoria_final = None
                cilindrada_final = None
                tipo_final = "carro"

            # Extrai ano de fabricação e modelo do campo "year" (formato "YYYY/YYYY")
            ano_fabricacao, ano_modelo = self._parse_year(v.get("year"))

            # Extrai motor do nome
            motor = self._extrair_motor(nome_completo)

            # Extrai câmbio dos opcionais
            cambio = self._extrair_cambio(opcionais_str)

            parsed = self.normalize_vehicle({
                "id": str(v.get("id")) if v.get("id") is not None else None,
                "tipo": tipo_final,
                "titulo": f"{marca} {nome_completo}".strip() if marca else nome_completo,
                "versao": nome_completo,
                "marca": marca,
                "modelo": modelo,
                "ano": ano_modelo,
                "ano_fabricacao": ano_fabricacao,
                "km": v.get("km") or None,
                "cor": v.get("color") or None,
                "combustivel": v.get("fuel") or None,
                "observacao": v.get("description") or None,
                "cambio": cambio,
                "motor": motor,
                "portas": v.get("doors") or None,
                "categoria": categoria_final,
                "cilindrada": cilindrada_final,
                "preco": self.converter_preco(v.get("price")),
                "opcionais": opcionais_str,
                "fotos": self._extract_photos(v),
            })

            parsed_vehicles.append(parsed)

        return parsed_vehicles

    def _extrair_modelo(self, nome_completo: str) -> str:
        """Extrai o modelo base do nome completo do veículo"""
        if not nome_completo:
            return ""
        # Pega a primeira palavra como modelo base
        partes = nome_completo.strip().split()
        return partes[0] if partes else nome_completo

    def _parse_opcionais(self, optionals: Any) -> str:
        """Processa os opcionais (lista de strings)"""
        if not optionals:
            return ""

        if isinstance(optionals, str):
            return optionals.strip()

        if isinstance(optionals, list):
            items = [item.strip() for item in optionals if isinstance(item, str) and item.strip()]
            return ", ".join(items)

        return ""

    def _detectar_moto(self, marca: str, nome: str) -> bool:
        """Detecta se o veículo é uma moto"""
        texto = f"{marca} {nome}".lower()
        keywords = ["moto", "motocicleta", "scooter", "trail", "enduro"]
        return any(kw in texto for kw in keywords)

    def _parse_year(self, year_str: Any) -> tuple:
        """
        Extrai ano de fabricação e ano modelo do formato 'YYYY/YYYY'
        Retorna: (ano_fabricacao, ano_modelo)
        """
        if not year_str:
            return None, None

        year_str = str(year_str).strip()
        parts = year_str.split("/")

        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()

        return None, year_str

    def _extrair_motor(self, nome_completo: str) -> Optional[str]:
        """Extrai informação do motor do nome do veículo (ex: '2.0', '1.4')"""
        import re
        if not nome_completo:
            return None
        match = re.search(r'\b(\d+\.\d+)\b', nome_completo)
        return match.group(1) if match else None

    def _extrair_cambio(self, opcionais_str: str) -> Optional[str]:
        """Infere câmbio a partir dos opcionais"""
        if not opcionais_str:
            return None
        opcionais_lower = opcionais_str.lower()
        if "câmbio automático" in opcionais_lower or "automatico" in opcionais_lower:
            return "Automático"
        if "câmbio manual" in opcionais_lower or "manual" in opcionais_lower:
            return "Manual"
        return None

    def _extract_photos(self, veiculo: Dict) -> List[str]:
        """Extrai fotos do veículo Diamond"""
        fotos = []

        # Imagem de capa
        cover = veiculo.get("coverImage")
        if cover and isinstance(cover, str) and cover.strip():
            fotos.append(cover.strip())

        # Galeria adicional (se existir)
        galeria = veiculo.get("gallery") or veiculo.get("images") or []
        if isinstance(galeria, list):
            for foto in galeria:
                if isinstance(foto, str) and foto.strip() and foto.strip() not in fotos:
                    fotos.append(foto.strip())

        return fotos
