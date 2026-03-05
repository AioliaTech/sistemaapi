"""
Parser específico para Admycar (admycar.com.br)
"""

from .base_parser import BaseParser
from typing import Dict, List, Any
import re

class AdmycarParser(BaseParser):
    """Parser para dados do Admycar"""
    
    def can_parse(self, data: Any, url: str) -> bool:
        """Verifica se pode processar dados do Admycar"""
        return "admycar.com" in url.lower()
    
    def _detectar_categoria_em_texto(self, modelo: str, versao: str, title: str) -> str:
        """
        Detecta categoria HATCH ou SEDAN nos campos modelo, versao e title.
        Retorna a categoria encontrada ou None se não encontrar.
        """
        # Concatena modelo, versão e título para buscar
        texto_completo = f"{modelo or ''} {versao or ''} {title or ''}".upper()
        
        # Busca por HATCH primeiro
        if "HATCH" in texto_completo:
            return "Hatch"
        
        # Busca por SEDAN
        if "SEDAN" in texto_completo:
            return "Sedan"
        
        return None
    
    def parse(self, data: Any, url: str) -> List[Dict]:
        """Processa dados do Admycar"""
        # Pega os anúncios
        ads = data.get("admycar", {}).get("ad", [])
        
        # Se vier um único anúncio como dict, transforma em lista
        if isinstance(ads, dict):
            ads = [ads]
        
        parsed_vehicles = []
        for ad in ads:
            marca = ad.get("make", "").strip()
            modelo = ad.get("model", "").strip()
            versao = ad.get("version", "").strip()
            title = ad.get("title", "").strip()
            opcionais_str = self._parse_opcionais(ad.get("opcionais"))
            
            # Determina se é moto baseado no modelo ou título
            tipo_lower = f"{marca} {modelo} {title}".lower()
            is_moto = any(keyword in tipo_lower for keyword in ["moto", "motocicleta", "scooter"])
            
            if is_moto:
                cilindrada_final, categoria_final = self.inferir_cilindrada_e_categoria_moto(
                    modelo, versao
                )
            else:
                # Tenta detectar categoria em modelo, versão e título
                categoria_detectada = self._detectar_categoria_em_texto(
                    modelo, versao, title
                )
                
                if categoria_detectada:
                    categoria_final = categoria_detectada
                else:
                    # Se não encontrou, usa a função existente com o modelo completo
                    categoria_final = self.definir_categoria_veiculo(modelo, opcionais_str)
                
                cilindrada_final = None
            
            # Extrai ano modelo e ano fabricação do campo year (formato: "YYYY/YYYY")
            ano_fabricacao, ano_modelo = self._parse_year(ad.get("year"))
            
            parsed = self.normalize_vehicle({
                "id": ad.get("id"),
                "tipo": "moto" if is_moto else "carro",
                "titulo": title,
                "versao": versao,
                "marca": marca,
                "modelo": modelo,
                "ano": ano_modelo,
                "ano_fabricacao": ano_fabricacao,
                "km": ad.get("km"),
                "cor": ad.get("color"),
                "combustivel": ad.get("fuel"),
                "observacao": None,  # Admycar não tem campo observação no XML
                "cambio": None,  # Não vem no XML, mas pode estar nos opcionais
                "motor": self._extract_motor_from_version(versao),
                "portas": ad.get("doors"),
                "categoria": categoria_final,
                "cilindrada": cilindrada_final,
                "preco": self.converter_preco(ad.get("price")),
                "opcionais": opcionais_str,
                "fotos": self._extract_photos(ad),
                "placa": ad.get("placa"),  # Campo extra do Admycar
            })
            parsed_vehicles.append(parsed)
        
        return parsed_vehicles
    
    def _parse_opcionais(self, opcionais: str) -> str:
        """Processa os opcionais do Admycar (vem separado por ponto e vírgula)"""
        if not opcionais:
            return ""
        
        # Remove espaços extras e ponto e vírgula final
        items = [item.strip() for item in opcionais.split(";") if item.strip()]
        return ", ".join(items)
    
    def _parse_year(self, year_str: str) -> tuple:
        """
        Extrai ano de fabricação e ano modelo do formato 'YYYY/YYYY'
        Retorna: (ano_fabricacao, ano_modelo)
        """
        if not year_str:
            return None, None
        
        years = year_str.split("/")
        if len(years) == 2:
            ano_fabricacao = years[0].strip()
            ano_modelo = years[1].strip()
            return ano_fabricacao, ano_modelo
        
        # Se só tiver um ano, usa como modelo
        return None, year_str.strip()
    
    def _extract_motor_from_version(self, versao: str) -> str:
        """Extrai informações do motor da versão"""
        if not versao:
            return None
        
        # Pega a primeira palavra da versão que geralmente é o motor
        words = versao.strip().split()
        return words[0] if words else None
    
    def _extract_photos(self, ad: Dict) -> List[str]:
        """Extrai fotos do veículo Admycar"""
        pictures = ad.get("pictures")
        if not pictures:
            return []
        
        picture_list = pictures.get("picture", [])
        
        # Se vier um único picture como dict, transforma em lista
        if isinstance(picture_list, dict):
            picture_list = [picture_list]
        
        # Monta a URL completa das fotos
        base_url = "https://admycar.com.br/3.4_Ajx/fotos/"
        
        return [
            f"{base_url}{pic['picture_url']}"
            for pic in picture_list
            if isinstance(pic, dict) and "picture_url" in pic
        ]
