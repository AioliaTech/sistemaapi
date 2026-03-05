"""
Parser específico para Loja Conectada
"""

from .base_parser import BaseParser
from typing import Dict, List, Any

class LojaConectadaParser(BaseParser):
    """Parser para dados da Loja Conectada"""
    
    # Mapeamento de categorias específico da Loja Conectada
    CATEGORIA_MAPPING = {
        "conversivel/cupe": "Conversível",
        "conversível/cupê": "Conversível",
        "conversivel": "Conversível",
        "picapes": "Caminhonete",
        "picape": "Caminhonete",
        "suv / utilitario esportivo": "SUV",
        "suv / utilitário esportivo": "SUV",
        "suv": "SUV",
        "van/utilitario": "Utilitário",
        "van/utilitário": "Utilitário",
        "utilitario": "Utilitário",
        "wagon/perua": "Minivan",
        "perua": "Minivan",
        "minivan": "Minivan",
        "hatch": "Hatch",
        "sedan": "Sedan",
        "caminhonete": "Caminhonete",
        "off-road": "Off-road"
    }

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
                
                # HIERARQUIA DE CATEGORIZAÇÃO:
                # 1. Usa campo bodywork.name do JSON se disponível
                bodywork_name = v.get("bodywork", {}).get("name", "")
                bodywork_lower = bodywork_name.lower().strip() if bodywork_name else ""
                categoria_bodywork = self.CATEGORIA_MAPPING.get(bodywork_lower, None)
                
                if categoria_bodywork:
                    categoria_final = categoria_bodywork
                elif bodywork_name:
                    # Se bodywork existe mas não está no mapeamento, usa direto
                    categoria_final = bodywork_name
                else:
                    # 2. Busca "hatch" ou "sedan" no modelo e versão
                    texto_busca = f"{modelo_veiculo or ''} {versao_veiculo or ''}".upper()
                    if "HATCH" in texto_busca:
                        categoria_final = "Hatch"
                    elif "SEDAN" in texto_busca:
                        categoria_final = "Sedan"
                    else:
                        # 3. Infere do nosso mapeamento com sistema de scoring
                        categoria_final = self.definir_categoria_veiculo(modelo_veiculo, opcionais_veiculo)
                
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
                "cilindrada": cilindrada_final,
                "preco": self.converter_preco(v.get("price")),
                "opcionais": opcionais_veiculo,
                "localizacao": localizacao,
                "fotos": fotos
            })
            parsed_vehicles.append(parsed)

        return parsed_vehicles

    def _extract_motor_from_version(self, version_name: str) -> str:
        """Extrai o motor da string da versão (ex: '2.0 TFSI ROADSTER 211CV' -> '2.0')"""
        if not version_name:
            return None

        import re
        # Procura por padrão de motor no início: dígitos.pontodígitos
        match = re.match(r'^(\d+\.\d+)', version_name.strip())
        if match:
            return match.group(1)
        return None
