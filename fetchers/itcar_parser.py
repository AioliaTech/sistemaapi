"""
Parser específico para ItCar
"""

from .base_parser import BaseParser
from typing import Dict, List, Any
from datetime import datetime

class ItcarParser(BaseParser):
    """Parser para dados do ItCar"""
    
    def can_parse(self, data: Any, url: str) -> bool:
        """Verifica se pode processar dados do ItCar"""
        # Verifica pela URL (it-car.com.br - cobre aws.it-car.com.br e outras variações)
        if url and "it-car.com.br" in url.lower():
            return True
        
        # Verifica pela estrutura do JSON (dict já parseado)
        if isinstance(data, dict) and "Veiculos" in data:
            return True
        
        # Verifica se data é string (JSON ainda não parseado)
        if isinstance(data, str) and '"Veiculos"' in data:
            return True
        
        return False
    
    def parse(self, data: Any, url: str) -> List[Dict]:
        """Processa dados do ItCar"""
        # Pega os veículos
        veiculos = data.get("Veiculos", [])
        
        # Se vier um único veículo como dict, transforma em lista
        if isinstance(veiculos, dict):
            veiculos = [veiculos]
        
        parsed_vehicles = []
        for veiculo in veiculos:
            marca = veiculo.get("Marca", "").strip()
            modelo = veiculo.get("Modelo", "").strip()
            versao = veiculo.get("Versao", "").strip()
            categoria_original = veiculo.get("Categoria", "").strip()
            
            # Determina se é moto baseado na categoria original
            is_moto = categoria_original.lower() in ["moto", "motocicleta"]
            
            # Processa opcionais
            opcionais_str = self._parse_opcionais(veiculo.get("Opcionais", []))
            
            if is_moto:
                # Para motos, infere cilindrada e categoria
                cilindrada_final, categoria_final = self.inferir_cilindrada_e_categoria_moto(
                    modelo, versao
                )
            else:
                # Para carros, usa a categoria do mapeamento
                categoria_final = self.definir_categoria_veiculo(modelo, opcionais_str, versao)
                cilindrada_final = None
            
            # Extrai ano de fabricação e modelo
            ano_fabricacao = veiculo.get("AnoFabricacao", "").strip()
            ano_modelo = veiculo.get("AnoModelo", "").strip()
            
            # Processa combustível
            combustivel = self._normalizar_combustivel(veiculo.get("Combustivel", ""))
            
            # Processa câmbio
            cambio = self._normalizar_cambio(veiculo.get("Cambio", ""))
            
            # Processa quilometragem
            km = self._parse_km(veiculo.get("Quilometragem"))
            
            # Processa motor
            motor = self._parse_motor(veiculo.get("Motor"))
            
            # Processa portas
            portas = self._parse_portas(veiculo.get("Portas"))
            
            # Monta título
            titulo = self._montar_titulo(marca, modelo, versao)
            
            # Processa observações
            observacao = veiculo.get("Observacoes", "").strip() or None
            
            parsed = self.normalize_vehicle({
                "id": veiculo.get("Codigo"),
                "tipo": "moto" if is_moto else "carro",
                "titulo": titulo,
                "versao": versao,
                "marca": marca,
                "modelo": modelo,
                "ano": ano_modelo,
                "ano_fabricacao": ano_fabricacao,
                "km": km,
                "cor": veiculo.get("Cor", "").strip() or None,
                "combustivel": combustivel,
                "observacao": observacao,
                "cambio": cambio,
                "motor": motor,
                "portas": portas,
                "categoria": categoria_final,
                "cilindrada": cilindrada_final,
                "preco": self.converter_preco(veiculo.get("Preco")),
                "opcionais": opcionais_str,
                "fotos": self._extract_photos(veiculo),
                "placa": veiculo.get("Placa", "").strip() or None,
                "loja": veiculo.get("Loja", "").strip() or None,
            })
            parsed_vehicles.append(parsed)
        
        return parsed_vehicles
    
    def _parse_opcionais(self, opcionais: List[str]) -> str:
        """Processa os opcionais do ItCar (vem como lista)"""
        if not opcionais:
            return ""
        
        # Se for string, retorna direto
        if isinstance(opcionais, str):
            return opcionais.strip()
        
        # Se for lista, junta os itens
        if isinstance(opcionais, list):
            # Remove itens vazios e "Nenhum opcional informado"
            items = [
                item.strip() 
                for item in opcionais 
                if item and item.strip() and item.strip().lower() != "nenhum opcional informado"
            ]
            return ", ".join(items) if items else ""
        
        return ""
    
    def _normalizar_combustivel(self, combustivel: str) -> str:
        """Normaliza o tipo de combustível"""
        if not combustivel:
            return None
        
        combustivel = combustivel.strip().lower()
        
        # Mapeamento de combustíveis
        mapa = {
            "gasolina": "Gasolina",
            "alcool": "Álcool",
            "álcool": "Álcool",
            "etanol": "Álcool",
            "flex": "Flex",
            "flexível": "Flex",
            "diesel": "Diesel",
            "gnv": "GNV",
            "eletrico": "Elétrico",
            "elétrico": "Elétrico",
            "hibrido": "Híbrido",
            "híbrido": "Híbrido",
        }
        
        return mapa.get(combustivel, combustivel.title())
    
    def _normalizar_cambio(self, cambio: str) -> str:
        """Normaliza o tipo de câmbio"""
        if not cambio:
            return None
        
        cambio = cambio.strip().lower()
        
        # Mapeamento de câmbios
        mapa = {
            "manual": "Manual",
            "automatico": "Automático",
            "automático": "Automático",
            "automatizado": "Automatizado",
            "cvt": "CVT",
            "sequencial": "Sequencial",
            "sequencial": "Sequencial",
        }
        
        return mapa.get(cambio, cambio.title())
    
    def _parse_km(self, km_value: Any) -> int:
        """Converte quilometragem para inteiro"""
        if not km_value:
            return None
        
        try:
            # Remove caracteres não numéricos
            if isinstance(km_value, str):
                km_value = km_value.replace(".", "").replace(",", "").strip()
            return int(km_value)
        except (ValueError, TypeError):
            return None
    
    def _parse_motor(self, motor_value: Any) -> str:
        """Processa informação do motor"""
        if not motor_value:
            return None
        
        motor_str = str(motor_value).strip()
        
        # Remove espaços extras e tabs
        motor_str = " ".join(motor_str.split())
        
        return motor_str if motor_str else None
    
    def _parse_portas(self, portas_value: Any) -> int:
        """Converte número de portas para inteiro"""
        if not portas_value:
            return None
        
        try:
            portas = int(portas_value)
            # Motos geralmente vêm com 0 portas
            return portas if portas > 0 else None
        except (ValueError, TypeError):
            return None
    
    def _montar_titulo(self, marca: str, modelo: str, versao: str) -> str:
        """Monta o título do veículo"""
        partes = []
        
        if marca:
            partes.append(marca)
        if modelo:
            partes.append(modelo)
        if versao:
            partes.append(versao)
        
        return " ".join(partes) if partes else "Veículo sem título"
    
    def _extract_photos(self, veiculo: Dict) -> List[str]:
        """Extrai fotos do veículo ItCar"""
        fotos = veiculo.get("Fotos", [])
        
        if not fotos:
            return []
        
        # Se for string, transforma em lista
        if isinstance(fotos, str):
            fotos = [fotos]
        
        # Filtra URLs válidas
        urls_validas = []
        for foto in fotos:
            if isinstance(foto, str) and foto.strip():
                url = foto.strip()
                # Verifica se é uma URL válida
                if url.startswith("http://") or url.startswith("https://"):
                    urls_validas.append(url)
        
        return urls_validas
