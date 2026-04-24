"""
Parser específico para SimplesVeiculo (simplesveiculo.com.br)
"""

from .base_parser import BaseParser
from typing import Dict, List, Any, Optional
import requests
import os
from vehicle_mappings import MAPEAMENTO_BODY_STYLE


class SimplesVeiculoParser(BaseParser):
    """Parser para dados do SimplesVeiculo"""

    CATEGORIA_MAPPING = MAPEAMENTO_BODY_STYLE
    
    def can_parse(self, data: Any, url: str) -> bool:
        """Verifica se pode processar dados do SimplesVeiculo"""
        return "simplesveiculo.com.br" in url.lower()
    
    def parse(self, data: Any, url: str) -> List[Dict]:
        """Processa dados do SimplesVeiculo"""
        listings = data.get("listings", {})
        veiculos = listings.get("listing", [])

        if isinstance(veiculos, dict):
            veiculos = [veiculos]

        # Carrega preços da fonte secundária UMA VEZ (não por veículo)
        secondary_prices = self._load_secondary_prices()

        parsed_vehicles = []

        for v in veiculos:
            if not isinstance(v, dict):
                continue
            
            vehicle_id = v.get("vehicle_id")
            titulo = v.get("title", "")
            modelo_completo = v.get("model", "")
            marca = v.get("make", "")
            
            # Extrai modelo base da string completa
            modelo_final = self._extract_modelo_base(modelo_completo, marca)
            
            # Processa quilometragem
            km_final = self._extract_mileage(v.get("mileage", {}))
            
            # Determina se é moto ou carro
            vehicle_type = v.get("vehicle_type", "").lower()
            
            # SimplesVeiculo usa 'car_truck' para carros e 'motorcycle' para motos
            is_moto = vehicle_type == "motorcycle" or "moto" in vehicle_type
            
            if is_moto:
                # Para motos: usa o sistema com modelo E versão
                cilindrada_final, categoria_final = self.inferir_cilindrada_e_categoria_moto(
                    modelo_final, modelo_completo
                )
                tipo_final = "moto"
            else:
                # HIERARQUIA DE CATEGORIZAÇÃO:
                # 1. Usa campo body_style do XML se disponível
                body_style = v.get("body_style", "")
                body_style_lower = body_style.lower().strip() if body_style else ""
                categoria_body = self.CATEGORIA_MAPPING.get(body_style_lower, None)
                
                description = v.get("description", "")
                
                if categoria_body:
                    categoria_final = categoria_body
                elif body_style:
                    # Se body_style existe mas não está no mapeamento, usa direto
                    categoria_final = body_style
                else:
                    # 2. Busca "hatch" ou "sedan" em model e description
                    texto_busca = f"{modelo_completo or ''} {description or ''}".upper()
                    if "HATCH" in texto_busca:
                        categoria_final = "Hatch"
                    elif "SEDAN" in texto_busca:
                        categoria_final = "Sedan"
                    else:
                        # 3. Infere do nosso mapeamento com sistema de scoring
                        categoria_final = self.definir_categoria_veiculo(modelo_final, "")
                
                cilindrada_final = None
                tipo_final = "carro"
            
            # Extrai informações do motor da descrição/modelo
            motor_info = self._extract_motor_info(modelo_completo)
            
            # Processa combustível
            combustivel_final = self._map_fuel_type(v.get("fuel_type", ""))
            
            # Processa câmbio
            cambio_final = self._map_transmission(v.get("transmission", ""))
            
            # Usa preço da fonte secundária se disponível
            preco_final = secondary_prices.get(str(vehicle_id)) if secondary_prices else None
            if preco_final is None:
                preco_final = self.converter_preco(v.get("price"))
            
            parsed = self.normalize_vehicle({
                "id": vehicle_id,
                "tipo": tipo_final,
                "titulo": titulo,
                "versao": self._clean_version(modelo_completo, marca),
                "marca": marca,
                "modelo": modelo_final,
                "ano": self._safe_int(v.get("year")),
                "ano_fabricacao": None,  # SimplesVeiculo não fornece separadamente
                "km": km_final,
                "cor": self._normalize_color(v.get("exterior_color", "")),
                "combustivel": combustivel_final,
                "cambio": cambio_final,
                "motor": motor_info,
                "portas": None,  # Não fornecido explicitamente
                "categoria": categoria_final,
                "cilindrada": cilindrada_final,
                "preco": preco_final,
                "opcionais": v.get("description"),  # SimplesVeiculo não fornece opcionais neste formato
                "fotos": self._extract_photos_simples(v)
            })
            
            parsed_vehicles.append(parsed)
        
        return parsed_vehicles
    
    def _load_secondary_prices(self) -> dict:
        """
        Carrega todos os preços da fonte secundária (XML_URL_2) UMA VEZ por ciclo de parse.
        Retorna dict {str(id): float(preco)} ou dict vazio se indisponível.
        Antes: fazia 1 request HTTP por veículo. Agora: 1 request por parse.
        """
        try:
            xml_url_2 = os.environ.get('XML_URL_2')
            if not xml_url_2:
                return {}
            response = requests.get(xml_url_2, timeout=30)
            response.raise_for_status()
            price_data = response.json()
            return {
                str(item.get("id")): self.converter_preco(item.get("valor"))
                for item in price_data
                if item.get("id") and item.get("valor")
            }
        except Exception as e:
            print(f"[WARN] SimplesVeiculoParser: erro ao carregar preços secundários: {e}")
            return {}
    
    def _extract_modelo_base(self, modelo_completo: str, marca: str) -> str:
        """Extrai o modelo base da string completa - Exemplo: "QQ 1.0 ACT 12V 69cv 5p" -> "QQ" """
        if not modelo_completo:
            return ""
        
        # Remove a marca se estiver no início
        modelo_sem_marca = modelo_completo
        if marca and modelo_completo.upper().startswith(marca.upper()):
            modelo_sem_marca = modelo_completo[len(marca):].strip()
        
        # Pega a primeira palavra que geralmente é o modelo
        palavras = modelo_sem_marca.strip().split()
        if palavras:
            return palavras[0]
        
        return modelo_completo.strip()
    
    def _extract_mileage(self, mileage_data: Dict) -> Optional[int]:
        """Extrai quilometragem do objeto mileage - Exemplo: {"value": "95528", "unit": "KM"} -> 95528"""
        if not isinstance(mileage_data, dict):
            return None
        
        value = mileage_data.get("value")
        if value:
            try:
                return int(float(str(value).replace(",", "").replace(".", "")))
            except (ValueError, TypeError):
                return None
        
        return None
    
    def _map_fuel_type(self, fuel_type: str) -> Optional[str]:
        """Mapeia fuel_type do SimplesVeiculo para nosso padrão"""
        if not fuel_type:
            return None
        
        fuel_lower = fuel_type.lower()
        
        mapping = {
            "gasoline": "gasolina",
            "ethanol": "etanol", 
            "flex": "flex",
            "diesel": "diesel",
            "electric": "elétrico",
            "hybrid": "híbrido"
        }
        
        return mapping.get(fuel_lower, fuel_type.lower())
    
    def _map_transmission(self, transmission: str) -> Optional[str]:
        """Mapeia transmission do SimplesVeiculo para nosso padrão"""
        if not transmission:
            return None
        
        trans_lower = transmission.lower()
        
        if "manual" in trans_lower:
            return "manual"
        elif "automatic" in trans_lower or "auto" in trans_lower:
            return "automatico"
        
        return transmission.lower()
    
    def _extract_photos_simples(self, veiculo: Dict) -> List[str]:
        """Extrai todas as fotos do veículo SimplesVeiculo"""
        fotos = []
        
        # Verifica se há um campo 'image' 
        image_data = veiculo.get("image")
        
        if not image_data:
            return fotos
        
        # Se é uma lista de imagens (caso mais comum com múltiplas tags <image>)
        if isinstance(image_data, list):
            for img in image_data:
                if isinstance(img, dict) and "url" in img:
                    url = str(img["url"]).strip()
                    if url and url != "https://app.simplesveiculo.com.br/":  # Ignora URLs vazias/placeholder
                        fotos.append(url)
                elif isinstance(img, str) and img.strip():
                    if img.strip() != "https://app.simplesveiculo.com.br/":
                        fotos.append(img.strip())
        
        # Se é um objeto único de imagem
        elif isinstance(image_data, dict):
            if "url" in image_data:
                url = str(image_data["url"]).strip()
                if url and url != "https://app.simplesveiculo.com.br/":
                    fotos.append(url)
        
        # Se é uma string única
        elif isinstance(image_data, str) and image_data.strip():
            if image_data.strip() != "https://app.simplesveiculo.com.br/":
                fotos.append(image_data.strip())
        
        return fotos
    
    def _clean_version(self, modelo_completo: str, marca: str) -> Optional[str]:
        """Limpa a versão removendo a marca e mantendo informações relevantes"""
        if not modelo_completo:
            return None
        
        versao = modelo_completo
        
        # Remove a marca se estiver no início
        if marca and versao.upper().startswith(marca.upper()):
            versao = versao[len(marca):].strip()
        
        # Remove o modelo base (primeira palavra)
        palavras = versao.split()
        if len(palavras) > 1:
            versao = " ".join(palavras[1:])
        else:
            return None  # Se só sobrou uma palavra, não há versão
        
        return versao.strip() if versao.strip() else None
    

    
    def _normalize_color(self, color: str) -> Optional[str]:
        """Normaliza a cor removendo formatação estranha"""
        if not color:
            return None
        
        return color.strip().lower().capitalize()
    
    def _safe_int(self, value: Any) -> Optional[int]:
        """Converte valor para int de forma segura"""
        if value is None:
            return None
        
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
