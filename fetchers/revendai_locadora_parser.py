"""
Parser específico para Revendai Locadora (integrador.revendai.com.br/api/client/.../locadora)
"""

from .base_parser import BaseParser, opcionais_para_codigos
from typing import Dict, List, Any
import re


class RevendaiLocadoraParser(BaseParser):
    """Parser para dados do Revendai Locadora"""

    def can_parse(self, data: Any, url: str) -> bool:
        """Verifica se pode processar dados do Revendai Locadora"""
        if not url:
            return False

        url = url.lower()
        return "integrador.revendai" in url and "locadora" in url

    def parse(self, data: Any, url: str) -> List[Dict]:
        """Processa dados do Revendai Locadora"""
        if not data or not isinstance(data, dict):
            return []

        veiculos = data.get("veiculos", [])

        if not veiculos or not isinstance(veiculos, list):
            return []

        parsed_vehicles = []
        for v in veiculos:
            if not isinstance(v, dict):
                continue

            if v.get("ativo") == False:
                continue

            modelo_veiculo = v.get("modelo")
            versao_veiculo = v.get("versao")
            opcionais_veiculo = v.get("opcionais") or ""

            tipo_veiculo = (v.get("tipo") or "").lower()
            is_moto = tipo_veiculo == "moto" or "motocicleta" in tipo_veiculo

            if is_moto:
                cilindrada_final, categoria_final = (
                    self.inferir_cilindrada_e_categoria_moto(
                        modelo_veiculo, versao_veiculo
                    )
                )
                tipo_final = "moto"
            else:
                categoria_final = self.definir_categoria_veiculo(
                    modelo_veiculo, opcionais_veiculo
                )
                cilindrada_final = v.get("cilindrada")
                tipo_final = tipo_veiculo

            id_original = v.get("id", "")
            numeros = re.findall(r"\d", str(id_original))
            id_final = "".join(numeros[:5]) if len(numeros) >= 5 else "".join(numeros)

            # Para locadora, extrai valores dos planos e ignora diaria/semanal/quinzenal/mensal
            plano_start = v.get("plano_start")
            plano_drive = v.get("plano_drive")
            plano_km_livre = v.get("plano_km_livre")

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
                    "categoria": v.get("categoria") or categoria_final,
                    "cilindrada": cilindrada_final,
                    "preco": v.get("preco"),
                    "valor_troca": v.get("valor_troca"),
                    "opcionais": opcionais_veiculo,
                    "fotos": v.get("fotos", []),
                    "plano_start": plano_start,
                    "plano_drive": plano_drive,
                    "plano_km_livre": plano_km_livre,
                }
            )
            parsed_vehicles.append(parsed)

        return parsed_vehicles

    # ── Interface de formatação ───────────────────────────────────────────────

    def format_vehicle_csv(self, vehicle: dict) -> str:
        """CSV padrão carro/moto com campos de planos de locação no final."""
        tipo = (vehicle.get("tipo") or "").lower()

        def sv(v):
            return "" if v is None else str(v)

        codigos = opcionais_para_codigos(vehicle.get("opcionais", ""))
        codigos_fmt = f"[{','.join(map(str, codigos))}]" if codigos else "[]"
        planos = ",".join([
            sv(vehicle.get("plano_start")),
            sv(vehicle.get("plano_drive")),
            sv(vehicle.get("plano_km_livre")),
        ])

        if "moto" in tipo:
            return ",".join([
                sv(vehicle.get("id")), sv(vehicle.get("tipo")),
                sv(vehicle.get("marca")), sv(vehicle.get("modelo")),
                sv(vehicle.get("versao")), sv(vehicle.get("cor")),
                sv(vehicle.get("ano")), sv(vehicle.get("km")),
                sv(vehicle.get("combustivel")), sv(vehicle.get("cilindrada")),
                sv(vehicle.get("preco")), planos,
            ])
        else:
            return ",".join([
                sv(vehicle.get("id")), sv(vehicle.get("tipo")),
                sv(vehicle.get("marca")), sv(vehicle.get("modelo")),
                sv(vehicle.get("versao")), sv(vehicle.get("cor")),
                sv(vehicle.get("ano")), sv(vehicle.get("km")),
                sv(vehicle.get("combustivel")), sv(vehicle.get("cambio")),
                sv(vehicle.get("motor")), sv(vehicle.get("portas")),
                sv(vehicle.get("preco")), codigos_fmt, planos,
            ])

    def get_instructions(self) -> str:
        return (
            "### COMO LER O JSON de 'BuscaEstoque' — Revendai Locadora (CRUCIAL — leia cada linha com atenção)\n"
            "- Para motocicletas (se o segundo valor no JSON for 'moto'):\n"
            "Código ID, tipo (moto), marca, modelo, versão, cor, ano, quilometragem, combustível, cilindrada, preço, plano_start, plano_drive, plano_km_livre\n"
            "- Para carros (se o segundo valor no JSON for 'carro'):\n"
            "Código ID, tipo (carro), marca, modelo, versão, cor, ano, quilometragem, combustível, câmbio, motor, portas, preço, [opcionais], plano_start, plano_drive, plano_km_livre\n\n"
            "- Para os opcionais dos carros, alguns números podem aparecer. Aqui está o significado de cada número:\n"
            "1 - ar-condicionado\n2 - airbag\n3 - vidros elétricos\n4 - freios ABS\n5 - direção hidráulica\n6 - direção elétrica\n7 - sete lugares\n"
            "- plano_start: valor do plano Start em reais\n"
            "- plano_drive: valor do plano Drive em reais\n"
            "- plano_km_livre: valor do plano Km Livre em reais\n"
        )
