"""
Parser específico para FordPlus (fordplus)
"""

from .base_parser import BaseParser
from typing import Dict, List, Any


class FordPlusParser(BaseParser):
    """Parser para dados do FordPlus - agrupa veículos novos (km=0/null) por versão"""

    def can_parse(self, data: Any, url: str) -> bool:
        return "fordplus" in url.lower()

    def parse(self, data: Any, url: str) -> List[Dict]:
        if not isinstance(data, list):
            return []

        veiculos_seminovos = []
        veiculos_novos = []

        for v in data:
            km = v.get("Km")
            is_novo = km is None or km == 0

            if is_novo:
                veiculos_novos.append(v)
            else:
                veiculos_seminovos.append(v)

        parsed_vehicles = []

        for v in veiculos_seminovos:
            parsed_vehicles.append(self._parse_veiculo(v))

        grupos_novos = self._agrupar_novos_por_versao(veiculos_novos)
        for grupo in grupos_novos:
            parsed_vehicles.append(grupo)

        return parsed_vehicles

    def _parse_veiculo(self, v: Dict) -> Dict:
        opcionais_veiculo = v.get("Opcionais") or ""
        if not isinstance(opcionais_veiculo, str):
            opcionais_veiculo = str(opcionais_veiculo) if opcionais_veiculo else ""

        modelo_veiculo = v.get("Modelo")
        versao_veiculo = v.get("Versao")
        observacoes_veiculo = v.get("Observacao")

        tipo_veiculo = v.get("Tipo", "").lower() if v.get("Tipo") else ""
        is_moto = "moto" in tipo_veiculo or "motocicleta" in tipo_veiculo

        if is_moto:
            cilindrada_final, categoria_final = (
                self.inferir_cilindrada_e_categoria_moto(modelo_veiculo, versao_veiculo)
            )
        else:
            categoria_final = self.definir_categoria_veiculo(
                modelo_veiculo, opcionais_veiculo
            )
            cilindrada_final = None

        return self.normalize_vehicle(
            {
                "id": v.get("Id"),
                "tipo": "moto" if is_moto else v.get("Tipo", "").lower(),
                "titulo": None,
                "versao": versao_veiculo,
                "marca": v.get("Marca"),
                "modelo": modelo_veiculo,
                "ano": v.get("AnoModelo"),
                "ano_fabricacao": v.get("AnoFabricacao"),
                "km": v.get("Km") if v.get("Km") else None,
                "cor": v.get("Cor"),
                "combustivel": v.get("Combustivel"),
                "observacao": observacoes_veiculo,
                "cambio": v.get("Transmissao"),
                "motor": self._extract_motor_from_version(versao_veiculo),
                "portas": v.get("Portas"),
                "categoria": categoria_final,
                "cilindrada": cilindrada_final,
                "preco": self.converter_preco(v.get("Preco")),
                "opcionais": opcionais_veiculo,
                "fotos": v.get("Fotos") or [],
            }
        )

    def _agrupar_novos_por_versao(self, veiculos_novos: List[Dict]) -> List[Dict]:
        grupos: Dict[str, List[Dict]] = {}

        for v in veiculos_novos:
            versao_key = (v.get("Versao") or "").strip().lower()
            if not versao_key:
                versao_key = f"__semversao_{v.get('Id')}"

            if versao_key not in grupos:
                grupos[versao_key] = []
            grupos[versao_key].append(v)

        resultado = []
        for versao_key, grupo_veiculos in grupos.items():
            primeiro = grupo_veiculos[0]

            cores = []
            todos_opcionais = []
            todas_fotos = []
            ids = []
            menor_preco = None

            for v in grupo_veiculos:
                cor = v.get("Cor")
                if cor and cor not in cores:
                    cores.append(cor)

                opc = v.get("Opcionais") or ""
                if isinstance(opc, str) and opc and opc not in todos_opcionais:
                    todos_opcionais.append(opc)

                fotos_v = v.get("Fotos") or []
                if isinstance(fotos_v, list):
                    for f in fotos_v:
                        if isinstance(f, str) and f not in todas_fotos:
                            todas_fotos.append(f)

                ids.append(v.get("Id"))

                preco_v = self.converter_preco(v.get("Preco"))
                if menor_preco is None or (preco_v and preco_v < menor_preco):
                    menor_preco = preco_v

            cor_final = ", ".join(cores) if cores else None
            opcionais_final = ", ".join(todos_opcionais) if todos_opcionais else ""
            id_final = ids[0] if ids else None

            modelo_veiculo = primeiro.get("Modelo")
            versao_veiculo = primeiro.get("Versao")

            tipo_veiculo = (
                primeiro.get("Tipo", "").lower() if primeiro.get("Tipo") else ""
            )
            is_moto = "moto" in tipo_veiculo or "motocicleta" in tipo_veiculo

            if is_moto:
                cilindrada_final, categoria_final = (
                    self.inferir_cilindrada_e_categoria_moto(
                        modelo_veiculo, versao_veiculo
                    )
                )
            else:
                categoria_final = self.definir_categoria_veiculo(
                    modelo_veiculo, opcionais_final
                )
                cilindrada_final = None

            parsed = self.normalize_vehicle(
                {
                    "id": id_final,
                    "tipo": "moto" if is_moto else tipo_veiculo,
                    "titulo": None,
                    "versao": versao_veiculo,
                    "marca": primeiro.get("Marca"),
                    "modelo": modelo_veiculo,
                    "ano": primeiro.get("AnoModelo"),
                    "ano_fabricacao": primeiro.get("AnoFabricacao"),
                    "km": None,
                    "cor": cor_final,
                    "combustivel": primeiro.get("Combustivel"),
                    "observacao": primeiro.get("Observacao"),
                    "cambio": primeiro.get("Transmissao"),
                    "motor": self._extract_motor_from_version(versao_veiculo),
                    "portas": primeiro.get("Portas"),
                    "categoria": categoria_final,
                    "cilindrada": cilindrada_final,
                    "preco": menor_preco if menor_preco is not None else 0.0,
                    "opcionais": opcionais_final,
                    "fotos": todas_fotos,
                }
            )
            resultado.append(parsed)

        return resultado

    def _extract_motor_from_version(self, versao: str) -> str:
        if not versao:
            return None
        words = versao.strip().split()
        return words[0] if words else None
