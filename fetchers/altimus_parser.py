"""
Parser específico para Altimus (altimus.com.br)
"""

from .base_parser import BaseParser
from typing import Dict, List, Any
import re
import xml.etree.ElementTree as ET


class AltimusParser(BaseParser):
    """Parser para dados do Altimus"""

    def can_parse(self, data: Any, url: str) -> bool:
        """Verifica se pode processar dados do Altimus"""
        return "altimus.com.br" in url.lower()

    def parse(self, data: Any, url: str) -> List[Dict]:
        """Processa dados do Altimus (JSON ou XML)"""
        print(f"[DEBUG AltimusParser] Tipo do data recebido: {type(data)}")
        print(f"[DEBUG AltimusParser] Primeiros 300 chars: {str(data)[:300]}")

        # Detecta se é XML string, XML parseado ou JSON
        if isinstance(data, str):
            print("[DEBUG AltimusParser] Detectado como STRING (XML)")
            try:
                veiculos_data = self._parse_xml_string(data)
                print(
                    f"[DEBUG AltimusParser] XML string parseado! {len(veiculos_data)} veículos"
                )
            except Exception as e:
                print(f"[ERROR AltimusParser] Erro ao parsear XML string: {e}")
                import traceback

                traceback.print_exc()
                return []

        elif isinstance(data, dict):
            # JSON tradicional com chave "veiculos" (API estoquejson da Altimus)
            if "veiculos" in data:
                print("[DEBUG AltimusParser] Detectado como DICT (JSON estoquejson)")
                veiculos_raw = data.get("veiculos", [])
                if isinstance(veiculos_raw, dict):
                    veiculos_raw = [veiculos_raw]
                veiculos_data = self._normalize_json_vehicles(veiculos_raw)
                print(
                    f"[DEBUG AltimusParser] JSON processado. {len(veiculos_data)} veículos"
                )

            # XML parseado - estrutura {'estoque': {'veiculo': [...]}}
            elif "estoque" in data:
                print(
                    "[DEBUG AltimusParser] Detectado como DICT de XML parseado (estoque)"
                )
                estoque = data.get("estoque", {})
                veiculos_list = estoque.get("veiculo", [])

                # Garante que é uma lista
                if isinstance(veiculos_list, dict):
                    veiculos_list = [veiculos_list]

                print(
                    f"[DEBUG AltimusParser] Encontrados {len(veiculos_list)} veículos em estoque"
                )
                veiculos_data = self._parse_xml_dict_vehicles(veiculos_list)

            # XML parseado - estrutura {'CargaVeiculos': {'Veiculo': [...]}}
            elif "CargaVeiculos" in data or "Veiculo" in data:
                print(
                    "[DEBUG AltimusParser] Detectado como DICT de XML parseado (CargaVeiculos)"
                )
                veiculos_data = self._parse_xml_dict(data)
                print(
                    f"[DEBUG AltimusParser] XML dict parseado! {len(veiculos_data)} veículos"
                )

            else:
                print("[ERROR AltimusParser] Estrutura de dict não reconhecida")
                print(f"[DEBUG AltimusParser] Keys disponíveis: {list(data.keys())}")
                return []

        else:
            print(f"[ERROR AltimusParser] Tipo não suportado: {type(data)}")
            return []

        resultado = self._process_vehicles(veiculos_data)
        print(f"[DEBUG AltimusParser] Retornando {len(resultado)} veículos processados")
        return resultado

    def _normalize_json_vehicles(self, veiculos_raw: List[Dict]) -> List[Dict]:
        """Normaliza veículos do formato JSON (API estoquejson) para o formato interno.

        O JSON da Altimus retorna campos como:
        - id, anoFabricacao, anoModelo, km, portas, valorVenda, tipo, marca, modelo,
          versao, cidade, cor, combustivel, motor, observacao, placa, potencia,
          cilindrada, cambio, categoria, opcionais (lista de strings),
          fotos (lista de URLs), informacoesAdicionais, destaque, chassi, etc.
        """
        print(
            f"[DEBUG _normalize_json_vehicles] Processando {len(veiculos_raw)} veículos JSON"
        )

        veiculos = []
        for v in veiculos_raw:
            # Opcionais: pode ser lista de strings ou string
            opcionais = v.get("opcionais", [])
            if isinstance(opcionais, list):
                opcionais_str = ", ".join(str(o).strip() for o in opcionais if o)
            elif isinstance(opcionais, str):
                opcionais_str = opcionais
            else:
                opcionais_str = ""

            # Fotos: pode ser lista de URLs ou string separada por ;
            fotos = v.get("fotos", [])
            if isinstance(fotos, list):
                fotos_list = [
                    f.strip() for f in fotos if isinstance(f, str) and f.strip()
                ]
            elif isinstance(fotos, str):
                fotos_list = [f.strip() for f in fotos.split(";") if f.strip()]
            else:
                fotos_list = []

            veiculo = {
                "id": v.get("id"),
                "tipo": v.get("tipo"),
                "marca": v.get("marca"),
                "modelo": v.get("modelo"),
                "versao": v.get("versao"),
                "anoFabricacao": v.get("anoFabricacao"),
                "anoModelo": v.get("anoModelo"),
                "ano": v.get("anoModelo"),
                "combustivel": v.get("combustivel"),
                "cambio": v.get("cambio"),
                "portas": v.get("portas"),
                "cor": v.get("cor"),
                "km": v.get("km"),
                "preco": v.get("valorVenda"),
                "valorVenda": v.get("valorVenda"),
                "opcionais": opcionais_str,
                "fotos": fotos_list,
                "observacao": v.get("observacao"),
                "motor": v.get("motor"),
                "cilindrada": v.get("cilindrada"),
                "cidade": v.get("cidade"),
            }

            veiculos.append(veiculo)

        return veiculos

    def _parse_xml_dict_vehicles(self, veiculos_list: List[Dict]) -> List[Dict]:
        """Processa lista de veículos de XML parseado (estrutura minúscula)"""
        print(
            f"[DEBUG _parse_xml_dict_vehicles] Processando {len(veiculos_list)} veículos"
        )

        veiculos = []
        for v in veiculos_list:
            # Opcionais
            opcionais_parts = []
            opcionais_obj = v.get("opcionais", {})
            if isinstance(opcionais_obj, dict):
                opcional_list = opcionais_obj.get("opcional", [])
                if isinstance(opcional_list, list):
                    opcionais_parts = opcional_list
                elif isinstance(opcional_list, str):
                    opcionais_parts = [opcional_list]

            # Fotos - usar 'imagem' ao invés de 'foto'
            fotos = []
            fotos_obj = v.get("fotos", {})
            if isinstance(fotos_obj, dict):
                imagem_list = fotos_obj.get("imagem", [])
                if isinstance(imagem_list, list):
                    fotos = imagem_list
                elif isinstance(imagem_list, str):
                    fotos = [imagem_list]

            veiculo = {
                "id": v.get("id"),
                "tipo": self._map_tipo_id(v.get("tipo")),
                "marca": v.get("marca"),
                "modelo": v.get("modelo"),
                "versao": v.get("versao"),
                "anoFabricacao": None,
                "anoModelo": v.get("ano"),
                "ano": v.get("ano"),
                "combustivel": v.get("combustivel"),
                "cambio": v.get("cambio"),
                "portas": v.get("portas"),
                "cor": v.get("cor"),
                "km": v.get("km"),
                "preco": v.get("valor"),
                "valorVenda": v.get("valor"),
                "opcionais": ", ".join(opcionais_parts) if opcionais_parts else "",
                "fotos": fotos,
                "observacao": v.get("observacao"),
            }

            print(
                f"[DEBUG _parse_xml_dict_vehicles] Veículo: ID={veiculo.get('id')} - Ano: {veiculo.get('ano')} - {len(fotos)} fotos"
            )
            veiculos.append(veiculo)

        return veiculos

    def _map_tipo_id(self, tipo_id: str) -> str:
        """Mapeia ID de tipo para nome"""
        if not tipo_id:
            return "carro"

        # Mapeamento comum (ajustar conforme necessário)
        tipo_map = {
            "1": "carro",
            "2": "moto",
            "3": "caminhao",
            "4": "utilitario",
        }

        return tipo_map.get(str(tipo_id), "carro")

    def _parse_xml_dict(self, data: Dict) -> List[Dict]:
        """Processa XML que já foi parseado para dict (estrutura CargaVeiculos)"""
        print("[DEBUG _parse_xml_dict] Processando dict de XML")

        if "CargaVeiculos" in data:
            carga = data["CargaVeiculos"]
            if isinstance(carga, dict) and "Veiculo" in carga:
                veiculos_list = carga["Veiculo"]
            else:
                veiculos_list = []
        elif "Veiculo" in data:
            veiculos_list = data["Veiculo"]
        else:
            print("[ERROR _parse_xml_dict] Não encontrou veículos no dict")
            return []

        if isinstance(veiculos_list, dict):
            veiculos_list = [veiculos_list]

        print(
            f"[DEBUG _parse_xml_dict] Encontrados {len(veiculos_list)} veículos no dict"
        )

        veiculos = []
        for v_dict in veiculos_list:
            veiculo = self._normalize_xml_dict_vehicle(v_dict)
            veiculos.append(veiculo)

        return veiculos

    def _normalize_xml_dict_vehicle(self, v: Dict) -> Dict:
        """Normaliza um veículo de XML dict (estrutura CargaVeiculos) para o formato padrão"""
        opcionais_parts = []
        equipamentos = v.get("Equipamentos", "")
        if equipamentos:
            opcionais_parts.append(equipamentos)

        if v.get("Ar_condicionado") == "sim":
            opcionais_parts.append("Ar condicionado")
        if v.get("Vidros_eletricos") == "sim":
            opcionais_parts.append("Vidros elétricos")
        if v.get("Travas_eletricas") == "sim":
            opcionais_parts.append("Travas elétricas")
        if v.get("Desembacador_traseiro") == "sim":
            opcionais_parts.append("Desembaçador traseiro")
        if v.get("Direcao_hidraulica") == "sim":
            opcionais_parts.append("Direção hidráulica")

        fotos_text = v.get("Fotos", "")
        if fotos_text:
            fotos = [f.strip() for f in fotos_text.split(";") if f.strip()]
        else:
            fotos = []

        return {
            "id": v.get("Codigo"),
            "tipo": v.get("Tipo"),
            "marca": v.get("Marca"),
            "modelo": v.get("Modelo"),
            "versao": v.get("ModeloVersao"),
            "anoFabricacao": v.get("AnoFabr"),
            "anoModelo": v.get("AnoModelo"),
            "ano": v.get("AnoModelo"),
            "combustivel": v.get("Combustivel"),
            "cambio": v.get("Cambio"),
            "portas": v.get("Portas"),
            "cor": v.get("Cor"),
            "km": v.get("Km"),
            "preco": v.get("Preco"),
            "valorVenda": v.get("Preco"),
            "opcionais": ", ".join(opcionais_parts) if opcionais_parts else "",
            "fotos": fotos,
            "observacao": v.get("Observacao"),
        }

    def _parse_xml_string(self, xml_string: str) -> List[Dict]:
        """Converte XML string para estrutura dict compatível"""
        xml_string = xml_string.strip()
        if xml_string.startswith("\ufeff"):
            xml_string = xml_string[1:]

        print(f"[DEBUG _parse_xml_string] Iniciando parse do XML")

        root = ET.fromstring(xml_string)
        print(f"[DEBUG _parse_xml_string] Root tag: {root.tag}")

        veiculos_elementos = root.findall("Veiculo")
        print(
            f"[DEBUG _parse_xml_string] Encontrados {len(veiculos_elementos)} elementos Veiculo"
        )

        veiculos = []
        for idx, veiculo_element in enumerate(veiculos_elementos):
            veiculo = {}

            veiculo["id"] = self._get_xml_text(veiculo_element, "Codigo")
            veiculo["tipo"] = self._get_xml_text(veiculo_element, "Tipo")
            veiculo["marca"] = self._get_xml_text(veiculo_element, "Marca")
            veiculo["modelo"] = self._get_xml_text(veiculo_element, "Modelo")
            veiculo["versao"] = self._get_xml_text(veiculo_element, "ModeloVersao")
            veiculo["anoFabricacao"] = self._get_xml_text(veiculo_element, "AnoFabr")
            veiculo["anoModelo"] = self._get_xml_text(veiculo_element, "AnoModelo")
            veiculo["ano"] = self._get_xml_text(veiculo_element, "AnoModelo")
            veiculo["combustivel"] = self._get_xml_text(veiculo_element, "Combustivel")
            veiculo["cambio"] = self._get_xml_text(veiculo_element, "Cambio")
            veiculo["portas"] = self._get_xml_text(veiculo_element, "Portas")
            veiculo["cor"] = self._get_xml_text(veiculo_element, "Cor")
            veiculo["km"] = self._get_xml_text(veiculo_element, "Km")
            veiculo["preco"] = self._get_xml_text(veiculo_element, "Preco")
            veiculo["valorVenda"] = self._get_xml_text(veiculo_element, "Preco")

            opcionais_parts = []
            equipamentos = self._get_xml_text(veiculo_element, "Equipamentos")
            if equipamentos:
                opcionais_parts.append(equipamentos)

            if self._get_xml_text(veiculo_element, "Ar_condicionado") == "sim":
                opcionais_parts.append("Ar condicionado")
            if self._get_xml_text(veiculo_element, "Vidros_eletricos") == "sim":
                opcionais_parts.append("Vidros elétricos")
            if self._get_xml_text(veiculo_element, "Travas_eletricas") == "sim":
                opcionais_parts.append("Travas elétricas")
            if self._get_xml_text(veiculo_element, "Desembacador_traseiro") == "sim":
                opcionais_parts.append("Desembaçador traseiro")
            if self._get_xml_text(veiculo_element, "Direcao_hidraulica") == "sim":
                opcionais_parts.append("Direção hidráulica")

            veiculo["opcionais"] = ", ".join(opcionais_parts) if opcionais_parts else ""

            fotos_text = self._get_xml_text(veiculo_element, "Fotos")
            if fotos_text:
                veiculo["fotos"] = [
                    f.strip() for f in fotos_text.split(";") if f.strip()
                ]
            else:
                veiculo["fotos"] = []

            veiculo["observacao"] = self._get_xml_text(veiculo_element, "Observacao")

            print(
                f"[DEBUG _parse_xml_string] Veículo {idx + 1}: {veiculo.get('marca')} {veiculo.get('modelo')}"
            )
            veiculos.append(veiculo)

        return veiculos

    def _get_xml_text(self, element: ET.Element, tag: str) -> str:
        """Extrai texto de um elemento XML de forma segura"""
        child = element.find(tag)
        return child.text.strip() if child is not None and child.text else None

    def _process_vehicles(self, veiculos: List[Dict]) -> List[Dict]:
        """Processa lista de veículos (comum para JSON e XML)"""
        print(f"[DEBUG _process_vehicles] Processando {len(veiculos)} veículos...")
        parsed_vehicles = []

        for v in veiculos:
            modelo_veiculo = v.get("modelo")
            versao_veiculo = v.get("versao")
            opcionais_veiculo = self._parse_opcionais(v.get("opcionais"))
            combustivel_veiculo = v.get("combustivel")

            tipo_veiculo = v.get("tipo", "")
            tipo_veiculo_lower = tipo_veiculo.lower() if tipo_veiculo else ""
            is_moto = (
                "moto" in tipo_veiculo_lower or "motocicleta" in tipo_veiculo_lower
            )

            if is_moto:
                cilindrada_final, categoria_final = (
                    self.inferir_cilindrada_e_categoria_moto(
                        modelo_veiculo, versao_veiculo
                    )
                )
            else:
                categoria_final = self.definir_categoria_veiculo(
                    modelo_veiculo, opcionais_veiculo
                )
                cilindrada_final = None

            tipo_final = self._determine_tipo(tipo_veiculo, is_moto)

            if (
                tipo_final in ["moto", "eletrico"]
                and combustivel_veiculo
                and str(combustivel_veiculo).lower() == "elétrico"
            ):
                categoria_final = "Scooter Eletrica"

            parsed = self.normalize_vehicle(
                {
                    "id": v.get("id"),
                    "tipo": tipo_final,
                    "titulo": None,
                    "versao": versao_veiculo,
                    "marca": v.get("marca"),
                    "modelo": modelo_veiculo,
                    "ano": v.get("anoModelo") or v.get("ano"),
                    "ano_fabricacao": v.get("anoFabricacao") or v.get("ano_fabricacao"),
                    "km": v.get("km"),
                    "cor": v.get("cor"),
                    "combustivel": combustivel_veiculo,
                    "cambio": self._normalize_cambio(v.get("cambio")),
                    "motor": self._extract_motor_from_version(versao_veiculo),
                    "portas": v.get("portas"),
                    "categoria": categoria_final,
                    "cilindrada": cilindrada_final,
                    "preco": self.converter_preco(
                        v.get("valorVenda") or v.get("preco")
                    ),
                    "opcionais": opcionais_veiculo,
                    "fotos": v.get("fotos", []),
                    "observacao": v.get("observacao"),
                }
            )
            parsed_vehicles.append(parsed)

        print(
            f"[DEBUG _process_vehicles] Total processado: {len(parsed_vehicles)} veículos"
        )
        return parsed_vehicles

    def _parse_opcionais(self, opcionais: Any) -> str:
        """Processa os opcionais do Altimus"""
        if isinstance(opcionais, list):
            return ", ".join(str(item) for item in opcionais if item)
        return str(opcionais) if opcionais else ""

    def _determine_tipo(self, tipo_original: str, is_moto: bool) -> str:
        """Determina o tipo final do veículo"""
        if not tipo_original:
            return "carro" if not is_moto else "moto"

        tipo_lower = tipo_original.lower()
        if "motos" in tipo_lower or "moto" in tipo_lower:
            return "moto"
        elif "carros" in tipo_lower or "carro" in tipo_lower:
            return "carro"
        elif tipo_original in ["Bicicleta", "Patinete Elétrico"]:
            return "eletrico"
        elif is_moto:
            return "moto"
        elif tipo_original == "Carro/Camioneta":
            return "carro"
        else:
            return tipo_lower

    def _normalize_cambio(self, cambio: str) -> str:
        """Normaliza informações de câmbio"""
        if not cambio:
            return cambio

        cambio_str = str(cambio).lower()
        if "manual" in cambio_str:
            return "manual"
        elif "automático" in cambio_str or "automatico" in cambio_str:
            return "automatico"
        else:
            return cambio

    def _extract_motor_from_version(self, versao: str) -> str:
        """Extrai informações do motor da versão"""
        if not versao:
            return None

        motor_match = re.search(r"\b(\d+\.\d+)\b", str(versao))
        return motor_match.group(1) if motor_match else None
