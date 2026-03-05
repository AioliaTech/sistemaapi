"""
Parser específico para Netcar (netcarmultimarcas.com.br)
"""

from .base_parser import BaseParser
from typing import Dict, List, Any

class NetcarParser(BaseParser):
    """Parser para dados do Netcar"""
    
    # Mapeamento de nomes de opcionais para formato legível
    OPCIONAIS_MAPPING = {
        "air_bag": "Air Bag",
        "air_bag_cortina": "Air Bag Cortina",
        "air_bag_duplo": "Air Bag Duplo",
        "air_bag_lateral": "Air Bag Lateral",
        "alarme": "Alarme",
        "ar_condicionado": "Ar Condicionado",
        "ar_condicionado_digital": "Ar Condicionado Digital",
        "ar_condicionado_dual_zone": "Ar Condicionado Dual Zone",
        "ar_quente": "Ar Quente",
        "banco_com_aquecimento": "Banco com Aquecimento",
        "bancos_de_couro": "Bancos de Couro",
        "banco_eletrico": "Banco Elétrico",
        "bancos_com_regulagem_de_altura": "Bancos com Regulagem de Altura",
        "cabine_dupla": "Cabine Dupla",
        "cabine_estendida": "Cabine Estendida",
        "cambio_automatico": "Câmbio Automático",
        "cambio_automatico_6_marchas": "Câmbio Automático 6 Marchas",
        "cambio_manual_6_marchas": "Câmbio Manual 6 Marchas",
        "camera_de_re": "Câmera de Ré",
        "capota_maritima": "Capota Marítima",
        "chave_reserva": "Chave Reserva",
        "computador_de_bordo": "Computador de Bordo",
        "controle_de_tracao": "Controle de Tração",
        "desembacador_traseiro": "Desembaçador Traseiro",
        "direcao_eletrica": "Direção Elétrica",
        "direcao_hidraulica": "Direção Hidráulica",
        "estribo": "Estribo",
        "farois_auxiliares": "Faróis Auxiliares",
        "farolete": "Farolete",
        "freios_abs": "Freios ABS",
        "freios_abs_com_ebd": "Freios ABS com EBD",
        "gps": "GPS",
        "interface": "Interface",
        "lanternas_em_led": "Lanternas em LED",
        "limpador_traseiro": "Limpador Traseiro",
        "lona_maritima": "Lona Marítima",
        "manual": "Manual",
        "multimidia": "Multimídia",
        "paddle_shift": "Paddle Shift",
        "piloto_automatico": "Piloto Automático",
        "porta_malas_eletrico": "Porta Malas Elétrico",
        "protetor_de_cacamba": "Protetor de Caçamba",
        "retrovisor_eletrico": "Retrovisor Elétrico",
        "rodas_de_liga_leve": "Rodas de Liga Leve",
        "santo_antonio": "Santo Antônio",
        "sensor_de_chuva": "Sensor de Chuva",
        "sensor_de_estacionamento": "Sensor de Estacionamento",
        "sensor_de_luminosidade": "Sensor de Luminosidade",
        "som_no_volante": "Som no Volante",
        "som_radio_cd": "Som Rádio CD",
        "som_radio_dvd": "Som Rádio DVD",
        "som_radiomp3": "Som Rádio MP3",
        "som_radio_com_usb": "Som Rádio com USB",
        "gestauto": "Gest Auto",
        "teto_panoramico": "Teto Panorâmico",
        "teto_solar": "Teto Solar",
        "tracao_4x2": "Tração 4x2",
        "tracao_4x4": "Tração 4x4",
        "tracao_awd": "Tração AWD",
        "tracao_fwd": "Tração FWD",
        "travas_eletricas": "Travas Elétricas",
        "vidros_eletricos": "Vidros Elétricos",
        "vidros_verdes": "Vidros Verdes",
        "farois_de_xenon": "Faróis de Xenon",
        "volante_regulagem_de_altura": "Volante Regulagem de Altura",
        "chave_inteligente": "Chave Inteligente",
        "rebatimento_espelhos": "Rebatimento Espelhos",
        "unico_dono": "Único Dono",
        "revisados_concessionaria": "Revisados na Concessionária",
        "top_linha": "Top de Linha",
        "oleo_filtro": "Óleo e Filtro",
        "pneus_novos": "Pneus Novos",
        "lider_mercado": "Líder de Mercado",
        "eleito_melhor_compra": "Eleito Melhor Compra",
        "manual_chave_reserva": "Manual e Chave Reserva",
        "baixa_km": "Baixa KM",
        "estepe_novo": "Estepe Novo",
        "garantia_fabrica": "Garantia de Fábrica",
        "super_economico": "Super Econômico",
        "cambio_dupla_embreagem": "Câmbio Dupla Embreagem",
        "som_radio": "Som Rádio",
        "botao": "Botão",
        "kit_trail": "Kit Trail",
        "tv": "TV",
        "tilt_down": "Tilt Down",
        "cambio_dsg": "Câmbio DSG",
        "freio_disco": "Freio a Disco",
        "z360": "360",
        "media_nav": "Media Nav",
        "my_link": "My Link",
        "motor_turbo": "Motor Turbo",
        "on_star": "On Star",
        "isofix": "Isofix",
        "park_assist": "Park Assist",
        "sete_lugares": "7 Lugares",
        "oito_marchas": "8 Marchas",
        "um_ano": "1 Ano",
        "apple": "Apple CarPlay",
        "android": "Android Auto",
        "covid_19": "Covid-19",
        "assistencia_faixa": "Assistência de Faixa",
        "piloto_adaptativo": "Piloto Adaptativo",
        "alerta_colisao": "Alerta de Colisão",
        "freio_eletronico": "Freio Eletrônico",
        "sem_fio": "Sem Fio",
        "carregador_inducao": "Carregador por Indução",
        "cambio_cvt": "Câmbio CVT",
        "cambio_sete": "Câmbio 7 Marchas",
        "farol_negro": "Farol Negromask",
        "acionamento": "Acionamento",
        "cambio_nove": "Câmbio 9 Marchas",
        "franagem_emergencia": "Frenagem de Emergência",
        "indcador_fadiga": "Indicador de Fadiga",
        "monitor_pressao": "Monitor de Pressão",
        "cinto_tres": "Cinto de 3 Pontos",
        "escape_esportivo": "Escape Esportivo",
        "start_stop": "Start/Stop",
        "gnv": "GNV",
        "controle_velocidade": "Controle de Velocidade",
        "porta_mala": "Porta Mala",
        "auto_hold": "Auto Hold",
        "bonus_especial": "Bônus Especial",
        "km": "KM",
        "banco_misto": "Banco Misto",
        "botao_eco": "Botão Eco",
        "reg_altura": "Regulagem de Altura",
        "remap_carbase": "Remap Carbase",
        "porta_automatica": "Porta Automática"
    }
    
    def can_parse(self, data: Any, url: str) -> bool:
        """Verifica se pode processar dados do Netcar"""
        url = url.lower()
        # Verifica pela URL ou pela estrutura do XML
        if "netcar" in url:
            return True
        
        # Verifica pela estrutura (tag dataroot e veiculo)
        if isinstance(data, dict):
            return "dataroot" in data or "veiculo" in data
        
        return False

    def parse(self, data: Any, url: str) -> List[Dict]:
        """Processa dados do Netcar"""
        # Extrai veículos do XML
        if "dataroot" in data:
            veiculos = data["dataroot"].get("veiculo", [])
        else:
            veiculos = data.get("veiculo", [])
        
        # Garante que seja lista
        if isinstance(veiculos, dict):
            veiculos = [veiculos]
        
        parsed_vehicles = []
        
        for v in veiculos:
            # Converte o preço primeiro para validar
            preco = self.converter_preco(v.get("preco"))
            
            # Pula veículos sem preço ou preço zerado
            if not preco or preco == 0:
                continue
            
            modelo_veiculo = v.get("modelo")
            descricao = v.get("descricao")
            
            # Extrai opcionais
            opcionais_str = self._extract_opcionais(v.get("opcionais", {}))
            
            # Determina tipo do veículo
            tipo_veiculo = v.get("tipo_veiculo", "0")
            is_moto = tipo_veiculo == "1"  # Assumindo 1 = moto, 0 = carro
            
            if is_moto:
                cilindrada_final, categoria_final = self.inferir_cilindrada_e_categoria_moto(
                    modelo_veiculo, descricao
                )
                tipo_final = "moto"
            else:
                # Pega categoria direto do XML se disponível
                categoria_xml = v.get("categoria_veiculo", "")
                
                if categoria_xml:
                    categoria_final = categoria_xml
                else:
                    # Tenta inferir da descrição/modelo
                    texto_busca = f"{modelo_veiculo or ''} {descricao or ''}".upper()
                    if "HATCH" in texto_busca:
                        categoria_final = "Hatch"
                    elif "SEDAN" in texto_busca:
                        categoria_final = "Sedan"
                    else:
                        categoria_final = self.definir_categoria_veiculo(modelo_veiculo, opcionais_str)
                
                cilindrada_final = None
                tipo_final = "carro"
            
            # SAÍDA IDÊNTICA AO REVENDAMAIS
            parsed = self.normalize_vehicle({
                "id": v.get("codigo_anuncio_revenda"),
                "tipo": tipo_final,
                "versao": descricao,
                "marca": v.get("marca"),
                "modelo": modelo_veiculo,
                "ano": v.get("ano_modelo"),
                "ano_fabricacao": v.get("ano_fabricacao"),
                "km": v.get("quilometragem"),
                "cor": v.get("cor"),
                "combustivel": v.get("combustivel"),
                "cambio": v.get("cambio"),
                "motor": v.get("motor"),
                "portas": v.get("portas"),
                "categoria": categoria_final,
                "cilindrada": cilindrada_final,
                "preco": preco,
                "opcionais": opcionais_str,
                "fotos": self._extract_photos(v)
            })
            parsed_vehicles.append(parsed)
        
        return parsed_vehicles
    
    def _extract_opcionais(self, opcionais_dict: Dict) -> str:
        """Extrai opcionais que têm valor 1 e retorna string separada por vírgula"""
        if not opcionais_dict:
            return ""
        
        opcionais_ativos = []
        
        for key, value in opcionais_dict.items():
            # Verifica se o opcional está ativo (valor 1 ou "1")
            if str(value) == "1":
                # Pega nome legível do mapeamento ou formata o nome da tag
                nome_legivel = self.OPCIONAIS_MAPPING.get(key, self._formatar_nome_opcional(key))
                opcionais_ativos.append(nome_legivel)
        
        return ", ".join(opcionais_ativos)
    
    def _formatar_nome_opcional(self, key: str) -> str:
        """Formata nome do opcional caso não esteja no mapeamento"""
        # Remove underscores e capitaliza cada palavra
        return " ".join(word.capitalize() for word in key.split("_"))
    
    def _extract_photos(self, v: Dict) -> List[str]:
        """Extrai fotos do veículo Netcar (foto1 até foto14)"""
        fotos = []
        base_url = "https://www.netcarmultimarcas.com.br/imagens/veiculos_automacar/small/"
        
        # Itera de foto1 até foto14
        for i in range(1, 15):
            foto_key = f"foto{i}"
            foto_filename = v.get(foto_key)
            
            if foto_filename and foto_filename.strip():
                # Codifica apenas os espaços
                foto_filename_encoded = foto_filename.replace(" ", "%20")
                # Monta URL completa
                foto_url = base_url + foto_filename_encoded
                fotos.append(foto_url)
        
        return fotos
