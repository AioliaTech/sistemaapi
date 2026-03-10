"""
VehicleCategorizer - Classe centralizada para categorização de veículos.
Usa múltiplos critérios em ordem de prioridade para determinar a categoria.
"""

from typing import Dict, Optional
from vehicle_mappings import MAPEAMENTO_CATEGORIAS, OPCIONAL_CHAVE_HATCH
from unidecode import unidecode
import re


class VehicleCategorizer:
    """
    Classe centralizada para categorização de veículos.
    Usa múltiplos critérios em ordem de prioridade.
    """
    
    def __init__(self):
        self.mapeamento = MAPEAMENTO_CATEGORIAS
        self.opcional_hatch = OPCIONAL_CHAVE_HATCH
    
    def categorize(self, vehicle_data: Dict) -> Optional[str]:
        """
        Categoriza um veículo usando hierarquia de critérios.
        
        Args:
            vehicle_data: Dicionário com dados do veículo:
                - categoria: str (do XML, pode estar vazio)
                - modelo: str
                - titulo: str
                - versao: str
                - portas: int
                - opcionais: str
                - observacao: str
                - tipo: str (carro/moto)
        
        Returns:
            Categoria do veículo (Hatch, Sedan, SUV, etc.) ou None
        """
        # 1. Categoria do XML (se confiável)
        categoria = self._detect_from_xml_category(vehicle_data)
        if categoria:
            return categoria
        
        # 2. Palavra-chave em TODOS os campos de texto
        categoria = self._detect_from_keywords(vehicle_data)
        if categoria:
            return categoria
        
        # 3. Mapeamento por modelo (mais específico)
        categoria = self._detect_from_mapping(vehicle_data)
        if categoria:
            # Se for ambíguo (hatch,sedan), usa critérios adicionais
            if categoria == "hatch,sedan":
                return self._resolve_ambiguous(vehicle_data)
            return categoria
        
        # 4. Fallback: retorna None
        return None
    
    def _detect_from_xml_category(self, vehicle_data: Dict) -> Optional[str]:
        """
        Usa categoria do XML se for confiável.
        
        Categorias confiáveis:
        - SUV, Caminhonete, Furgão, Coupe, Conversível, etc.
        
        Categorias NÃO confiáveis (podem estar erradas):
        - Hatch, Sedan (muitos XMLs erram)
        """
        categoria_xml = vehicle_data.get("categoria", "").strip()
        if not categoria_xml:
            return None
        
        # Normaliza
        categoria_norm = self._normalize_text(categoria_xml)
        
        # Lista de categorias confiáveis (não ambíguas)
        categorias_confiaveis = [
            "suv", "caminhonete", "furgao", "coupe", "conversivel",
            "station wagon", "minivan", "off-road", "utilitario"
        ]
        
        for cat in categorias_confiaveis:
            if cat in categoria_norm:
                return categoria_xml.title()  # Retorna com capitalização
        
        # Hatch/Sedan do XML não são confiáveis, ignora
        return None
    
    def _detect_from_keywords(self, vehicle_data: Dict) -> Optional[str]:
        """
        Detecta categoria por palavras-chave em TODOS os campos de texto.
        Varre: título, modelo, versão, observação, opcionais, etc.
        """
        # Concatena TODOS os campos de texto disponíveis
        campos_texto = [
            vehicle_data.get('titulo', ''),
            vehicle_data.get('modelo', ''),
            vehicle_data.get('versao', ''),
            vehicle_data.get('observacao', ''),
            vehicle_data.get('opcionais', ''),
            vehicle_data.get('categoria', ''),  # Categoria do XML também
        ]
        
        # Junta tudo em um único texto para busca
        texto_completo = ' '.join(campos_texto).upper()
        
        # Busca por palavras-chave (ordem de especificidade)
        # Mais específicas primeiro para evitar falsos positivos
        
        # Categorias específicas
        if "STATION WAGON" in texto_completo or " SW " in texto_completo:
            return "Station Wagon"
        if "PICK-UP" in texto_completo or "PICKUP" in texto_completo:
            return "Caminhonete"
        if "CONVERSIVEL" in texto_completo or "CABRIOLET" in texto_completo or "CABRIO" in texto_completo:
            return "Conversível"
        if "COUPE" in texto_completo or "COUPÉ" in texto_completo:
            return "Coupe"
        if "MINIVAN" in texto_completo:
            return "Minivan"
        if "FURGAO" in texto_completo or "FURGÃO" in texto_completo:
            return "Furgão"
        if "OFF-ROAD" in texto_completo or "OFFROAD" in texto_completo:
            return "Off-road"
        if "UTILITARIO" in texto_completo or "UTILITÁRIO" in texto_completo:
            return "Utilitário"
        
        # SUV (várias variações)
        if any(palavra in texto_completo for palavra in ["SUV", "SPORT UTILITY", "CROSSOVER"]):
            return "SUV"
        
        # Hatch e Sedan (mais genéricas, por último)
        if "HATCHBACK" in texto_completo or "HATCH" in texto_completo:
            return "Hatch"
        if "SEDAN" in texto_completo:
            return "Sedan"
        
        return None
    
    def _detect_from_mapping(self, vehicle_data: Dict) -> Optional[str]:
        """
        Usa mapeamento de modelos com sistema de scoring.
        """
        modelo = vehicle_data.get("modelo", "")
        if not modelo:
            return None
        
        modelo_norm = self._normalize_text(modelo)
        
        # Busca no mapeamento pelo MELHOR match
        matches = []
        
        for modelo_mapeado, categoria_result in self.mapeamento.items():
            modelo_mapeado_norm = self._normalize_text(modelo_mapeado)
            
            if modelo_mapeado_norm in modelo_norm:
                # Score: número de palavras + comprimento
                palavras_mapeado = modelo_mapeado_norm.split()
                palavras_modelo = modelo_norm.split()
                palavras_match = sum(1 for p in palavras_mapeado if p in palavras_modelo)
                score = (palavras_match * 100) + len(modelo_mapeado_norm)
                
                matches.append({
                    'categoria': categoria_result,
                    'score': score
                })
        
        if matches:
            matches.sort(key=lambda x: x['score'], reverse=True)
            return matches[0]['categoria']
        
        return None
    
    def _resolve_ambiguous(self, vehicle_data: Dict) -> str:
        """
        Resolve categorias ambíguas (hatch,sedan) usando múltiplos critérios.
        
        Critérios em ordem:
        1. Número de portas (5=hatch, 4=sedan)
        2. Opcionais (limpador traseiro = hatch)
        3. Palavra "Sport" no nome (geralmente hatch)
        4. Default: Sedan
        """
        # 1. Número de portas
        portas = vehicle_data.get("portas")
        if portas:
            try:
                portas_int = int(portas)
                if portas_int == 5:
                    return "Hatch"
                elif portas_int == 4:
                    return "Sedan"
            except (ValueError, TypeError):
                pass
        
        # 2. Opcionais (limpador traseiro)
        opcionais = vehicle_data.get("opcionais", "")
        if opcionais:
            opcionais_norm = self._normalize_text(opcionais)
            opcional_chave_norm = self._normalize_text(self.opcional_hatch)
            if opcional_chave_norm in opcionais_norm:
                return "Hatch"
        
        # 3. Palavra "Sport" no modelo/título
        texto = f"{vehicle_data.get('modelo', '')} {vehicle_data.get('titulo', '')}".upper()
        if "SPORT" in texto:
            return "Hatch"
        
        # 4. Default: Sedan (mais comum quando não há informação)
        return "Sedan"
    
    def _normalize_text(self, texto: str) -> str:
        """Normaliza texto para comparação."""
        if not texto:
            return ""
        texto_norm = unidecode(str(texto)).lower()
        texto_norm = re.sub(r'[-_./]', ' ', texto_norm)
        texto_norm = re.sub(r'[^a-z0-9\s]', '', texto_norm)
        texto_norm = re.sub(r'\s+', ' ', texto_norm).strip()
        return texto_norm
