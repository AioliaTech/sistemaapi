"""
Parser específico para AutoGestor (agsistema.net)
"""

from .base_parser import BaseParser
from typing import Dict, List, Any
import re

class AutogestorParser(BaseParser):
    """Parser para dados do AutoGestor"""
    
    def can_parse(self, data: Any, url: str) -> bool:
        """Verifica se pode processar dados do AutoGestor"""
        return "agsistema.net" in url.lower()
    
    def _detectar_categoria_em_texto(self, modelo: str, versao: str, carroceria: str, titulo: str) -> str:
        """
        Detecta categoria HATCH ou SEDAN nos campos modelo, versao, carroceria e titulo.
        Retorna a categoria encontrada ou None se não encontrar.
        """
        # Concatena modelo, versão, carroceria e título para buscar
        texto_completo = f"{modelo or ''} {versao or ''} {carroceria or ''} {titulo or ''}".upper()
        
        # Busca por HATCH primeiro
        if "HATCH" in texto_completo:
            return "Hatch"
        
        # Busca por SEDAN
        if "SEDAN" in texto_completo:
            return "Sedan"
        
        return None
    
    def parse(self, data: Any, url: str) -> List[Dict]:
        """Processa dados do AutoGestor"""
        # Pega os veículos
        veiculos = data.get("veiculos", [])
        
        # Se vier um único veículo como dict, transforma em lista
        if isinstance(veiculos, dict):
            veiculos = [veiculos]
        
        parsed_vehicles = []
        for v in veiculos:
            # Filtra veículos que não devem ser anunciados
            if v.get("anunciar", "").lower() == "nao":
                continue
            
            marca = v.get("marca", "").strip()
            modelo = v.get("modelo", "").strip()
            versao = v.get("versao", "").strip()
            titulo = v.get("titulo", "").strip()
            carroceria = v.get("carroceria", "").strip()
            acessorios_list = v.get("acessorios", [])
            opcionais_str = self._parse_acessorios(acessorios_list)
            
            # Determina se é moto baseado na categoria
            categoria_veiculo = v.get("categoria", "").lower()
            is_moto = "moto" in categoria_veiculo
            
            if is_moto:
                cilindrada_final, categoria_final = self.inferir_cilindrada_e_categoria_moto(
                    modelo, versao
                )
            else:
                # Tenta detectar categoria em modelo, versão, carroceria e título
                categoria_detectada = self._detectar_categoria_em_texto(
                    modelo, versao, carroceria, titulo
                )
                
                if categoria_detectada:
                    categoria_final = categoria_detectada
                else:
                    # Se não encontrou, usa a função existente com o modelo completo
                    categoria_final = self.definir_categoria_veiculo(modelo, opcionais_str)
                
                # Usa cilindradas do JSON se for carro
                cilindrada_final = v.get("cilindradas")
            
            # Extrai preço do objeto preco.venda
            preco_obj = v.get("preco", {})
            preco_venda = preco_obj.get("venda") if isinstance(preco_obj, dict) else None
            
            parsed = self.normalize_vehicle({
                "id": v.get("codigo"),
                "tipo": "moto" if is_moto else "carro",
                "titulo": titulo,
                "versao": versao,
                "marca": marca,
                "modelo": modelo,
                "ano": v.get("ano_modelo"),
                "ano_fabricacao": v.get("ano_fabricacao"),
                "km": v.get("km"),
                "cor": v.get("cor"),
                "combustivel": v.get("combustivel"),
                "observacao": v.get("descricao"),
                "cambio": v.get("cambio"),
                "motor": self._extract_motor_from_version(versao),
                "portas": v.get("portas"),
                "categoria": categoria_final,
                "cilindrada": cilindrada_final,
                "preco": self.converter_preco(preco_venda),
                "opcionais": opcionais_str,
                "fotos": v.get("fotos", []),
                "placa": v.get("placa"),
                "chassi": v.get("chassi"),
                "renavam": v.get("renavam"),
            })
            parsed_vehicles.append(parsed)
        
        return parsed_vehicles
    
    def _parse_acessorios(self, acessorios: List[str]) -> str:
        """Processa os acessórios do AutoGestor (vem como lista)"""
        if not acessorios or not isinstance(acessorios, list):
            return ""
        
        # Filtra itens vazios e junta com vírgula
        items = [item.strip() for item in acessorios if item and item.strip()]
        return ", ".join(items)
    
    def _extract_motor_from_version(self, versao: str) -> str:
        """Extrai informações do motor da versão"""
        if not versao:
            return None
        
        # Pega a primeira palavra da versão que geralmente é o motor
        words = versao.strip().split()
        return words[0] if words else None
