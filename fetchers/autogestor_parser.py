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
            anunciar_value = v.get("anunciar") or ""
            if anunciar_value.lower() == "nao":
                continue
            
            # Função auxiliar para garantir que None vire string vazia antes do strip
            def safe_strip(value):
                return (value or "").strip()
            
            marca = safe_strip(v.get("marca"))
            modelo = safe_strip(v.get("modelo"))
            versao = safe_strip(v.get("versao"))
            titulo = safe_strip(v.get("titulo"))
            carroceria = safe_strip(v.get("carroceria"))
            acessorios_list = v.get("acessorios", [])
            opcionais_str = self._parse_acessorios(acessorios_list)
            
            # Determina se é moto baseado na categoria
            categoria_veiculo = v.get("categoria", "").lower()
            is_moto = "moto" in categoria_veiculo
            
            body_style_carga = None
            if is_moto:
                cilindrada_final, categoria_final = self.inferir_cilindrada_e_categoria_moto(
                    modelo, versao
                )
            else:
                # Etapa 1: passa carroceria raw da carga para o VehicleCategorizer
                body_style_carga = carroceria or ""
                categoria_final  = None
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
                "body_style_carga": body_style_carga,
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
        
        # Filtra itens vazios e junta com vírgula, garantindo que None não cause erro
        items = [(item or "").strip() for item in acessorios if item and (item or "").strip()]
        return ", ".join(items)
    

