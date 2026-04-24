"""
Parser específico para Revendai (revendai.com.br)
"""

from .base_parser import BaseParser, opcionais_para_codigos
from typing import Dict, List, Any
import re


class RevendaiParser(BaseParser):
    """Parser para dados do Revendai"""

    def can_parse(self, data: Any, url: str) -> bool:
        """Verifica se pode processar dados do Revendai"""
        # Proteção contra url None ou vazia
        if not url:
            return False

        url = url.lower()
        return "integrador.revendai" in url and "locadora" not in url

    def parse(self, data: Any, url: str) -> List[Dict]:
        """Processa dados do Revendai"""
        # Validação de dados
        if not data or not isinstance(data, dict):
            return []

        veiculos = data.get("veiculos", [])

        # Validação de veículos
        if not veiculos or not isinstance(veiculos, list):
            return []

        parsed_vehicles = []
        for v in veiculos:
            # Validação de cada veículo
            if not isinstance(v, dict):
                continue

            # Ignora veículos inativos
            if v.get("ativo") == False:
                continue

            modelo_veiculo = v.get("modelo")
            versao_veiculo = v.get("versao")
            opcionais_veiculo = v.get("opcionais") or ""

            tipo_veiculo = (v.get("tipo") or "").lower()
            is_moto = tipo_veiculo == "moto" or "motocicleta" in tipo_veiculo

            body_style_carga = None
            if is_moto:
                cilindrada_final, categoria_final = (
                    self.inferir_cilindrada_e_categoria_moto(
                        modelo_veiculo, versao_veiculo
                    )
                )
                tipo_final = "moto"
            else:
                # Etapa 1: passa categoria raw da carga para o VehicleCategorizer
                body_style_carga = v.get("categoria", "") or ""
                categoria_final  = None
                cilindrada_final = v.get("cilindrada")
                tipo_final = tipo_veiculo

            id_original = v.get("id", "")
            numeros = re.findall(
                r"\d", str(id_original)
            )  # Converte para string por segurança
            id_final = "".join(numeros[:5]) if len(numeros) >= 5 else "".join(numeros)

            parsed = self.normalize_vehicle(
                {
                    "id": id_final,
                    "tipo": tipo_final,
                    "versao": versao_veiculo,
                    "marca": v.get("marca"),
                    "modelo": modelo_veiculo,
                    "observacao": v.get("observacao"),
                    "ano": v.get("ano"),
                    "ano_fabricacao": v.get("ano_fabricacao"),
                    "km": v.get("km"),
                    "cor": v.get("cor"),
                    "combustivel": v.get("combustivel"),
                    "cambio": v.get("cambio"),
                    "motor": v.get("motor"),
                    "portas": v.get("portas"),
                    "categoria": categoria_final,
                    "body_style_carga": body_style_carga,
                    "cilindrada": cilindrada_final,
                    "preco": v.get("preco"),
                    "valor_troca": v.get("valor_troca"),
                    "opcionais": opcionais_veiculo,
                    "fotos": v.get("fotos", []),
                    "repasse": self._normalize_repasse(v.get("repasse")),
                }
            )
            parsed_vehicles.append(parsed)

        return parsed_vehicles

    # ── Interface de formatação ───────────────────────────────────────────────

    def format_vehicle_csv(self, vehicle: dict) -> str:
        """CSV padrão Revendai — opcionais mapeados para códigos numéricos."""
        tipo = (vehicle.get("tipo") or "").lower()

        def sv(v):
            return "" if v is None else str(v)

        codigos = opcionais_para_codigos(vehicle.get("opcionais", ""))
        codigos_fmt = f"[{','.join(map(str, codigos))}]" if codigos else "[]"

        if "moto" in tipo:
            return ",".join([
                sv(vehicle.get("id")), sv(vehicle.get("tipo")),
                sv(vehicle.get("marca")), sv(vehicle.get("modelo")),
                sv(vehicle.get("versao")), sv(vehicle.get("cor")),
                sv(vehicle.get("ano")), sv(vehicle.get("km")),
                sv(vehicle.get("combustivel")), sv(vehicle.get("cilindrada")),
                sv(vehicle.get("preco")),
            ])
        else:
            return ",".join([
                sv(vehicle.get("id")), sv(vehicle.get("tipo")),
                sv(vehicle.get("marca")), sv(vehicle.get("modelo")),
                sv(vehicle.get("versao")), sv(vehicle.get("cor")),
                sv(vehicle.get("ano")), sv(vehicle.get("km")),
                sv(vehicle.get("combustivel")), sv(vehicle.get("cambio")),
                sv(vehicle.get("motor")), sv(vehicle.get("portas")),
                sv(vehicle.get("preco")), codigos_fmt,
            ])

    def format_list(self, vehicles: list) -> dict:
        """Separa veículos em ESTOQUE (próprios) e REPASSE, cada um por categoria."""
        veiculos_normais = [v for v in vehicles if not v.get("repasse")]
        veiculos_repasse = [v for v in vehicles if v.get("repasse") is True]

        result = {"ESTOQUE": self._format_grupo(veiculos_normais)}
        if veiculos_repasse:
            result["REPASSE"] = self._format_grupo(veiculos_repasse)
        return result

    def _format_grupo(self, vehicles: list) -> dict:
        categorized: dict = {}
        nao_mapeados: list = []
        for v in vehicles:
            categoria = v.get("categoria")
            csv_line = self.format_vehicle_csv(v)
            if not categoria or categoria in ["", "None", None]:
                nao_mapeados.append(csv_line)
            else:
                key = categoria.strip().title()
                categorized.setdefault(key, []).append(csv_line)
        result = {k: categorized[k] for k in sorted(categorized)}
        if nao_mapeados:
            result["NÃO MAPEADOS"] = nao_mapeados
        return result

    def get_instructions(self) -> str:
        return (
            "### COMO LER O JSON de 'BuscaEstoque' — Revendai (CRUCIAL — leia cada linha com atenção)\n"
            "- Para motocicletas (se o segundo valor no JSON for 'moto'):\n"
            "Código ID, tipo (moto), marca, modelo, versão, cor, ano, quilometragem, combustível, cilindrada, preço\n"
            "- Para carros (se o segundo valor no JSON for 'carro'):\n"
            "Código ID, tipo (carro), marca, modelo, versão, cor, ano, quilometragem, combustível, câmbio, motor, portas, preço, [opcionais]\n\n"
            "- Para os opcionais dos carros, alguns números podem aparecer. Aqui está o significado de cada número:\n"
            "1 - ar-condicionado\n2 - airbag\n3 - vidros elétricos\n4 - freios ABS\n5 - direção hidráulica\n6 - direção elétrica\n7 - sete lugares\n"
            "- IMPORTANTE: Os veículos estão separados em dois grupos principais: 'ESTOQUE' (veículos próprios) e 'REPASSE' (veículos de repasse). "
            "Dentro de cada grupo, os veículos estão organizados por categoria (Hatch, Sedan, Suv, etc).\n"
        )

    # ── Métodos de parsing ────────────────────────────────────────────────────

    def _normalize_repasse(self, repasse: Any) -> bool:
        """Normaliza o campo repasse para boolean (true/false).

        A carga original pode vir como boolean (True/False) ou string ('true'/'false'/'sim'/'nao').
        """
        if isinstance(repasse, bool):
            return repasse
        if not repasse:
            return False
        repasse_str = str(repasse).strip().lower()
        if repasse_str in ("true", "sim", "1", "yes", "s"):
            return True
        return False
