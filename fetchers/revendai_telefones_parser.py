"""
Parser específico para Revendai Telefones (revendai.com.br - tipo_negocio: telefone)
"""
from .base_parser import BaseParser
from typing import Dict, List, Any
import re


class RevendaiTelefonesParser(BaseParser):
    """Parser para dados de telefones do Revendai"""
    
    def can_parse(self, data: Any, url: str) -> bool:
        """Verifica se pode processar dados de telefones do Revendai"""
        # Proteção contra url None ou vazia
        if not url:
            return False
        
        url = url.lower()
        
        # Verifica se é endpoint do Revendai
        if "telefones" not in url:
            return False
        
        # Verifica se tem dados de telefones
        if isinstance(data, dict):
            cliente = data.get("cliente", {})
            if isinstance(cliente, dict):
                tipo_negocio = cliente.get("tipo_negocio", "").lower()
                return tipo_negocio == "telefone" and "telefones" in data
        
        return False
    
    def parse(self, data: Any, url: str) -> List[Dict]:
        """Processa dados de telefones do Revendai"""
        # Validação de dados
        if not data or not isinstance(data, dict):
            return []
        
        telefones = data.get("telefones", [])
        
        # Validação de telefones
        if not telefones or not isinstance(telefones, list):
            return []
        
        parsed_phones = []
        for t in telefones:
            # Validação de cada telefone
            if not isinstance(t, dict):
                continue
            
            # Ignora telefones inativos
            if t.get("ativo") == False:
                continue
            
            # Extrai ID (primeiros 5 dígitos)
            id_original = t.get("id", "")
            numeros = re.findall(r'\d', str(id_original))
            id_final = ''.join(numeros[:5]) if len(numeros) >= 5 else ''.join(numeros)
            
            # Monta o título do anúncio (Marca Modelo Versão)
            marca = t.get("marca", "").strip()
            modelo = t.get("modelo", "").strip()
            versao = t.get("versao", "").strip()
            titulo = f"{marca} {modelo} {versao}".strip()
            
            # Processa preços
            preco_cartao = t.get("cartao_12x")
            preco_dinheiro = t.get("dinheiro")
            preco_nota = t.get("notafiscal")
            
            # Define preço principal (usa dinheiro ou cartão)
            preco_principal = preco_dinheiro or preco_cartao
            
            # Monta observação com informações de preço e garantia
            obs_parts = []
            
            if preco_dinheiro:
                obs_parts.append(f"💵 À vista: R$ {preco_dinheiro}")
            
            if preco_cartao:
                obs_parts.append(f"💳 12x no cartão: R$ {preco_cartao}")
            
            if preco_nota:
                obs_parts.append(f"📄 Nota fiscal: R$ {preco_nota}")
            
            garantia = t.get("garantia")
            if garantia:
                obs_parts.append(f"✅ Garantia: {garantia}")
            
            quantidade = t.get("quantidade")
            if quantidade and quantidade > 1:
                obs_parts.append(f"📦 Quantidade disponível: {quantidade}")
            
            descricao = t.get("descricao", "").strip()
            if descricao:
                obs_parts.append(f"\n{descricao}")
            
            observacao_final = "\n".join(obs_parts)
            
            # Armazenamento (GB)
            gb = t.get("gb")
            
            parsed = self.normalize_vehicle({
                "id": id_final,
                "tipo": "telefone",
                "marca": marca,
                "modelo": modelo,
                "versao": versao,
                "titulo": titulo,
                "cor": t.get("cor", "").strip(),
                "gb": gb,
                "armazenamento": f"{gb}GB" if gb else None,
                "preco": preco_principal,
                "preco_cartao": preco_cartao,
                "preco_dinheiro": preco_dinheiro,
                "preco_nota_fiscal": preco_nota,
                "garantia": garantia,
                "quantidade": quantidade,
                "saude_bateria": t.get("saude_bateria"),
                "observacao": observacao_final,
                "descricao": descricao,
                "fotos": t.get("fotos", []),
                "videos": t.get("videos", []),
                "destaque": t.get("destaque", False)
            })
            
            parsed_phones.append(parsed)
        
        return parsed_phones
