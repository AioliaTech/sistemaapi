"""
Parser específico para Loja Conectada
"""

from .base_parser import BaseParser
from typing import Dict, List, Any
class LojaConectadaParser(BaseParser):
    """Parser para dados da Loja Conectada"""

    def can_parse(self, data: Any, url: str) -> bool:
        """Verifica se pode processar dados da Loja Conectada"""
        url = url.lower()
        return "lojaconectada" in url or "loja conectada" in url

    def parse(self, data: Any, url: str) -> List[Dict]:
        """Processa dados da Loja Conectada"""
        results = data.get("results", [])
        if not isinstance(results, list):
            results = [results] if results else []

        parsed_vehicles = []
        for v in results:
            # Extrair opcionais
            opcionais_list = v.get("optionals", [])
            opcionais_veiculo = ", ".join([opt.get("name", "") for opt in opcionais_list if opt.get("name")])

            # Extrair fotos
            fotos = [photo.get("photo") for photo in v.get("photos", []) if photo.get("photo")]

            # Localização
            address = v.get("address", {})
            city = address.get("city", {}).get("name", "")
            state = address.get("state", {}).get("name", "")
            localizacao = f"{city}, {state}".strip(", ")

            # Determinar categoria e tipo
            categoria_veiculo = v.get("category", {}).get("name", "").lower()
            is_moto = categoria_veiculo == "motocicleta" or "moto" in categoria_veiculo

            # Extrair motor da versão
            versao_name = v.get("version", {}).get("name", "")
            motor_veiculo = self._extract_motor_from_version(versao_name)

            body_style_carga = None
            if is_moto:
                modelo_veiculo = v.get("model", {}).get("name", "")
                versao_veiculo = versao_name
                cilindrada_final, categoria_final = self.inferir_cilindrada_e_categoria_moto(
                    modelo_veiculo, versao_veiculo
                )
                tipo_final = "moto"
            else:
                modelo_veiculo = v.get("model", {}).get("name", "")
                versao_veiculo = versao_name

                # Etapa 1: passa valor raw da carga para o VehicleCategorizer
                body_style_carga = v.get("bodywork", {}).get("name", "")
                categoria_final  = None
                cilindrada_final = None
                categoria_name = v.get("category", {}).get("name", "")
                tipo_final = "carro" if categoria_name.lower() == "car" else categoria_name

            parsed = self.normalize_vehicle({
                "id": v.get("ad_id"),
                "tipo": tipo_final,
                "titulo": v.get("title"),
                "versao": v.get("version", {}).get("name") or v.get("version_site"),
                "marca": v.get("manufacturer", {}).get("name"),
                "modelo": modelo_veiculo,
                "observacao": v.get("description"),
                "ano": v.get("model_year"),
                "ano_fabricacao": v.get("make_year"),
                "km": v.get("km"),
                "cor": v.get("color", {}).get("name"),
                "combustivel": v.get("fuel", {}).get("name"),
                "cambio": v.get("transmission", {}).get("name"),
                "motor": motor_veiculo,
                "portas": v.get("doors"),
                "categoria": categoria_final,
                "body_style_carga": body_style_carga,
                "cilindrada": cilindrada_final,
                "preco": self.converter_preco(v.get("price")),
                "opcionais": opcionais_veiculo,
                "localizacao": localizacao,
                "fotos": fotos
            })
            parsed_vehicles.append(parsed)

        return parsed_vehicles


