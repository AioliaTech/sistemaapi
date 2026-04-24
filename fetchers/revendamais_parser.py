"""
Parser específico para Revendamais (revendamais.com.br)
"""

from .base_parser import BaseParser, opcionais_para_codigos
from typing import Dict, List, Any
from vehicle_mappings import MAPEAMENTO_BODY_STYLE


class RevendamaisParser(BaseParser):
    """Parser para dados do Revendamais"""

    CATEGORIA_MAPPING = MAPEAMENTO_BODY_STYLE
    
    def can_parse(self, data: Any, url: str) -> bool:
        """Verifica se pode processar dados do Revendamais, Hey Veículos ou Piccoli Automóveis"""
        url = url.lower()
        return "revendamais.com.br" in url or "heyveiculos" in url or "piccoliautomoveis.com.br" in url or "grupomichelin" in url


    def parse(self, data: Any, url: str) -> List[Dict]:
        """Processa dados do Revendamais"""
        ads = data["ADS"]["AD"]
        if isinstance(ads, dict): 
            ads = [ads]
        
        parsed_vehicles = []
        for v in ads:
            modelo_veiculo = v.get("MODEL")
            versao_veiculo = v.get("VERSION")
            opcionais_veiculo = v.get("ACCESSORIES") or ""
            
            # Determina se é moto ou carro
            categoria_veiculo = v.get("CATEGORY", "").lower()
            is_moto = categoria_veiculo == "motocicleta" or "moto" in categoria_veiculo
            
            if is_moto:
                cilindrada_final, categoria_final = self.inferir_cilindrada_e_categoria_moto(
                    modelo_veiculo, versao_veiculo
                )
                tipo_final = "moto"
            else:
                # HIERARQUIA DE CATEGORIZAÇÃO:
                # 1. Usa campo BODY_TYPE do XML se disponível
                body_type = v.get("BODY_TYPE", "")
                body_type_lower = body_type.lower().strip() if body_type else ""
                categoria_body = self.CATEGORIA_MAPPING.get(body_type_lower, None)
                
                if categoria_body:
                    categoria_final = categoria_body
                elif body_type:
                    # Se BODY_TYPE existe mas não está no mapeamento, usa direto
                    categoria_final = body_type
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
                tipo_final = v.get("CATEGORY")

            # Campo blindado: vem como "true"/"false" ou ausente
            armored_raw = v.get("ARMORED") or v.get("armored")
            if armored_raw is not None:
                blindado = str(armored_raw).strip().lower() == "true"
            else:
                blindado = None

            parsed = self.normalize_vehicle({
                "id": v.get("ID"),
                "tipo": tipo_final,
                "versao": v.get("TITLE"),
                "marca": v.get("MAKE"),
                "modelo": modelo_veiculo,
                "ano": v.get("YEAR"),
                "ano_fabricacao": v.get("FABRIC_YEAR"),
                "km": v.get("MILEAGE"),
                "cor": v.get("COLOR"),
                "combustivel": v.get("FUEL"),
                "cambio": v.get("GEAR"),
                "observacao": v.get("DESCRIPTION"),
                "motor": v.get("MOTOR"),
                "portas": v.get("DOORS"),
                "categoria": categoria_final,
                "cilindrada": cilindrada_final,
                "preco": self.converter_preco(v.get("PRICE")),
                "blindado": blindado,
                "opcionais": opcionais_veiculo,
                "fotos": self._extract_photos(v)
            })
            parsed_vehicles.append(parsed)
        
        return parsed_vehicles
    
    def _extract_photos(self, v: Dict) -> List[str]:
        """Extrai fotos do veículo Revendamais"""
        images = v.get("IMAGES", [])
        if not images: 
            return []
        
        if isinstance(images, list):
            return [
                img.get("IMAGE_URL") 
                for img in images 
                if isinstance(img, dict) and img.get("IMAGE_URL")
            ]
        elif isinstance(images, dict) and images.get("IMAGE_URL"):
            return [images["IMAGE_URL"]]

        return []

    # ── Interface de formatação ───────────────────────────────────────────────

    def format_vehicle_csv(self, vehicle: dict) -> str:
        """CSV padrão carro/moto com campo 'blindado' no final."""
        tipo = (vehicle.get("tipo") or "").lower()

        def sv(v):
            return "" if v is None else str(v)

        codigos = opcionais_para_codigos(vehicle.get("opcionais", ""))
        codigos_fmt = f"[{','.join(map(str, codigos))}]" if codigos else "[]"

        blindado_val = vehicle.get("blindado")
        if blindado_val is True:
            blindado_str = "true"
        elif blindado_val is False:
            blindado_str = "false"
        else:
            blindado_str = ""

        if "moto" in tipo:
            return ",".join([
                sv(vehicle.get("id")), sv(vehicle.get("tipo")),
                sv(vehicle.get("marca")), sv(vehicle.get("modelo")),
                sv(vehicle.get("versao")), sv(vehicle.get("cor")),
                sv(vehicle.get("ano")), sv(vehicle.get("km")),
                sv(vehicle.get("combustivel")), sv(vehicle.get("cilindrada")),
                sv(vehicle.get("preco")), blindado_str,
            ])
        else:
            return ",".join([
                sv(vehicle.get("id")), sv(vehicle.get("tipo")),
                sv(vehicle.get("marca")), sv(vehicle.get("modelo")),
                sv(vehicle.get("versao")), sv(vehicle.get("cor")),
                sv(vehicle.get("ano")), sv(vehicle.get("km")),
                sv(vehicle.get("combustivel")), sv(vehicle.get("cambio")),
                sv(vehicle.get("motor")), sv(vehicle.get("portas")),
                sv(vehicle.get("preco")), codigos_fmt, blindado_str,
            ])

    def get_instructions(self) -> str:
        return (
            "### COMO LER O JSON de 'BuscaEstoque' (CRUCIAL — leia cada linha com atenção)\n"
            "- Para motocicletas (se o segundo valor no JSON for 'moto'):\n"
            "Código ID, tipo (moto), marca, modelo, versão, cor, ano, quilometragem, combustível, cilindrada, preço, blindado\n"
            "- Para carros (se o segundo valor no JSON for 'carro'):\n"
            "Código ID, tipo (carro), marca, modelo, versão, cor, ano, quilometragem, combustível, câmbio, motor, portas, preço, [opcionais], blindado\n\n"
            "- Para os opcionais dos carros, alguns números podem aparecer. Aqui está o significado de cada número:\n"
            "1 - ar-condicionado\n2 - airbag\n3 - vidros elétricos\n4 - freios ABS\n5 - direção hidráulica\n6 - direção elétrica\n7 - sete lugares\n"
            "- blindado: 'true' se o veículo é blindado, 'false' se não é, vazio se não informado\n"
        )
