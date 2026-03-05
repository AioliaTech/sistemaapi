"""
Parser específico para BNDV (Sistema de Lojistas)
"""

from .base_parser import BaseParser
from typing import Dict, List, Any
import json
import re


class BndvParser(BaseParser):
    """Parser para dados do BNDV"""
    
    # Mapeamento de categorias específico do BNDV
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
        """Verifica se pode processar dados do BNDV"""
        # Verifica se é BNDV pela URL ou estrutura dos dados
        if "bndv" in url.lower() or "sistema.lojistas" in url.lower():
            return True
        
        # Verifica pela estrutura do JSON
        if isinstance(data, dict) and "vehiclesBy" in data:
            return True
        
        return False
    
    def parse(self, data: Any, url: str) -> List[Dict]:
        """Processa dados do BNDV"""
        veiculos = data.get("vehiclesBy", [])
        
        if not isinstance(veiculos, list):
            veiculos = [veiculos]
        
        parsed_vehicles = []
        for v in veiculos:
            # Extrai dados básicos
            marca = v.get("markName")
            modelo = v.get("modelName")
            versao = v.get("versionName")
            subcategory = v.get("subCategoryName")
            
            # Processa opcionais
            opcionais_veiculo = self._parse_opcionais(v.get("itemJs"))
            
            # HIERARQUIA DE CATEGORIZAÇÃO:
            # 1. Usa campo subCategoryName do JSON se disponível
            subcategory_lower = subcategory.lower().strip() if subcategory else ""
            categoria_subcategory = self.CATEGORIA_MAPPING.get(subcategory_lower, None)
            
            if categoria_subcategory:
                categoria_final = categoria_subcategory
            else:
                # 2. Busca "hatch" ou "sedan" no modelo e versão
                texto_busca = f"{modelo or ''} {versao or ''}".upper()
                if "HATCH" in texto_busca:
                    categoria_final = "Hatch"
                elif "SEDAN" in texto_busca:
                    categoria_final = "Sedan"
                else:
                    # 3. Infere do nosso mapeamento com sistema de scoring
                    categoria_final = self.definir_categoria_veiculo(modelo, opcionais_veiculo)
            
            # Usa a placa ao contrário como ID
            placa = v.get("plate")
            vehicle_id = placa[::-1] if placa else None
            
            parsed = self.normalize_vehicle({
                "id": vehicle_id,
                "tipo": "carro",
                "titulo": None,
                "versao": versao,
                "marca": marca,
                "modelo": modelo,
                "ano": v.get("year"),
                "ano_fabricacao": None,
                "km": v.get("km"),
                "cor": v.get("color"),
                "combustivel": v.get("fuelName"),
                "cambio": v.get("transmissionName"),
                "motor": self._extract_motor_from_version(versao),
                "portas": None,
                "categoria": categoria_final,
                "cilindrada": None,
                "preco": v.get("saleValue"),
                "opcionais": opcionais_veiculo,
                "fotos": self._parse_fotos(v.get("pictureJs"))
            })
            parsed_vehicles.append(parsed)
        
        return parsed_vehicles
    
    def _parse_opcionais(self, item_js: str) -> str:
        """Processa os opcionais do BNDV (vem como JSON string)"""
        if not item_js:
            return ""
        
        try:
            items = json.loads(item_js)
            if isinstance(items, list):
                return ", ".join(item.get("value", "") for item in items if item.get("value"))
            return ""
        except (json.JSONDecodeError, AttributeError):
            return ""
    
    def _parse_fotos(self, picture_js: str) -> List[str]:
        """Extrai fotos do veículo BNDV (vem como JSON string)"""
        if not picture_js:
            return []
        
        try:
            pictures = json.loads(picture_js)
            if isinstance(pictures, list):
                # Ordena colocando a foto principal primeiro
                pictures_sorted = sorted(
                    pictures, 
                    key=lambda x: x.get("Principal", "false") != "true"
                )
                return [pic.get("Link", "") for pic in pictures_sorted if pic.get("Link")]
            return []
        except (json.JSONDecodeError, AttributeError):
            return []
    
    def _extract_motor_from_version(self, versao: str) -> str:
        """Extrai informações do motor da versão"""
        if not versao:
            return None
        
        # Procura por padrões como "1.0", "1.5", "2.0", etc.
        match = re.search(r'\b(\d\.\d)\b', versao)
        if match:
            return match.group(1)
        
        return None
