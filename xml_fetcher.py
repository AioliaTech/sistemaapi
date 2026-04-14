import ipaddress
import requests
import xmltodict
import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path
from urllib.parse import urlparse

# Hosts que exigem Web Unlocker (IPs de datacenter e proxies conhecidos são bloqueados)
_WEB_UNLOCKER_HOSTS = [
    "revendamais.com.br",
    "app.revendamais.com.br",
]


def _fetch_via_web_unlocker(url: str, headers: Dict[str, str]) -> Optional[bytes]:
    """
    Busca a URL usando o Bright Data Web Unlocker API.
    Retorna o conteúdo em bytes, ou None se não estiver configurado.
    Lança exceção em caso de erro na requisição.
    """
    api_key = os.environ.get("BRIGHTDATA_API_KEY", "").strip()
    zone = os.environ.get("BRIGHTDATA_ZONE", "web_unlocker1").strip()

    if not api_key:
        return None

    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not any(host == h or host.endswith("." + h) for h in _WEB_UNLOCKER_HOSTS):
        return None

    print(f"[INFO] Usando Bright Data Web Unlocker para host: {host}")
    response = requests.post(
        "https://api.brightdata.com/request",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json={"zone": zone, "url": url, "format": "raw"},
        timeout=60,
    )
    response.raise_for_status()
    return response.content


# Importa todos os parsers da pasta fetchers
from fetchers import (
    RevendaiTelefonesParser,
    AltimusParser,
    AutocertoParser,
    AutoconfParser,
    RevendamaisParser,
    FronteiraParser,
    RevendaproParser,
    ClickGarageParser,
    SimplesVeiculoParser,
    BoomParser,
    DSAutoEstoqueParser,
    BndvParser,
    RevendaiParser,
    ComautoParser1,
    ComautoParser2,
    RevendaPlusParser,
    CarburgoParser,
    LojaConectadaParser,
    AdmycarParser,
    AutogestorParser,
    NetcarParser,
    WordPressParser,
    ItcarParser,
    DiamondParser,
    CovelParser,
    EcosysParser,
    RevendaiLocadoraParser,
)


class UnifiedVehicleFetcher:
    def __init__(self):
        self.parsers = [
            RevendaiTelefonesParser(),
            AltimusParser(),
            NetcarParser(),
            AutogestorParser(),
            FronteiraParser(),
            ClickGarageParser(),
            AutocertoParser(),
            RevendamaisParser(),
            AutoconfParser(),
            SimplesVeiculoParser(),
            RevendaproParser(),
            BoomParser(),
            DSAutoEstoqueParser(),
            BndvParser(),
            RevendaiParser(),
            RevendaiLocadoraParser(),
            ComautoParser1(),
            ComautoParser2(),
            RevendaPlusParser(),
            CarburgoParser(),
            WordPressParser(),
            AdmycarParser(),
            LojaConectadaParser(),
            ItcarParser(),
            DiamondParser(),
            CovelParser(),
            EcosysParser(),
        ]
        self.last_parser_used: Optional[str] = None

    def detect_format(self, content: bytes, url: str) -> tuple[Any, str]:
        """Detecta se o conteúdo é JSON ou XML"""
        import re

        # Remove BOM se presente (UTF-8, UTF-16, UTF-32)
        if content.startswith(b"\xef\xbb\xbf"):
            content = content[3:]
        elif content.startswith(b"\xff\xfe") or content.startswith(b"\xfe\xff"):
            content = content[2:]
        elif content.startswith(b"\x00\x00\xfe\xff") or content.startswith(
            b"\xff\xfe\x00\x00"
        ):
            content = content[4:]

        # Tenta diferentes encodings
        content_str = None
        for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
            try:
                content_str = content.decode(encoding).strip()
                break
            except (UnicodeDecodeError, AttributeError):
                continue

        if not content_str:
            content_str = content.decode("utf-8", errors="ignore").strip()

        # Tenta parsear como JSON
        try:
            return json.loads(content_str), "json"
        except json.JSONDecodeError as e:
            print(f"[DEBUG] Erro ao parsear JSON: {e}")
            print(f"[DEBUG] Primeiros 500 caracteres: {content_str[:500]}")

            # Tenta corrigir problemas comuns no JSON
            try:
                # Remove trailing commas antes de ] ou }
                fixed_content = re.sub(r",\s*([}\]])", r"\1", content_str)

                # Remove caracteres de controle inválidos (tabs, newlines dentro de strings)
                # Mantém apenas espaços, mas remove \t, \n, \r dentro de valores de string
                fixed_content = re.sub(r"[\x00-\x1f\x7f]", " ", fixed_content)

                return json.loads(fixed_content), "json"
            except json.JSONDecodeError as e2:
                print(f"[DEBUG] Erro após correções: {e2}")

                # Tenta parsear como XML
                try:
                    return xmltodict.parse(content_str), "xml"
                except Exception as xml_error:
                    print(f"[DEBUG] Erro ao parsear XML: {xml_error}")
                    print(f"[DEBUG] Últimos 200 caracteres: {content_str[-200:]}")
                    raise ValueError(f"Formato não reconhecido para URL: {url}")

    def select_parser(self, data: Any, url: str) -> Optional[object]:
        """Seleciona o parser apropriado baseado na URL"""
        for parser in self.parsers:
            if parser.can_parse(data, url):
                print(f"[INFO] Parser selecionado: {parser.__class__.__name__}")
                self.last_parser_used = parser.__class__.__name__
                return parser

        print(f"[AVISO] Nenhum parser específico encontrado para URL: {url}")
        print(f"[INFO] Tentando BoomParser como fallback...")

        boom_parser = BoomParser()
        if boom_parser.can_parse(data, url):
            print(f"[INFO] Usando BoomParser como fallback")
            self.last_parser_used = "BoomParser"
            return boom_parser

        self.last_parser_used = None
        return None

    def process_url(self, url: str) -> List[Dict]:
        """Processa uma URL específica"""
        print(f"[INFO] Processando URL: {url}")

        # Lista de User-Agents para tentar bypass de bloqueios
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]

        last_error = None
        for i, ua in enumerate(user_agents):
            try:
                headers = {
                    "User-Agent": ua,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Accept-Encoding": "gzip, deflate",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                    "Cache-Control": "max-age=0",
                    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120"',
                    "Sec-Ch-Ua-Mobile": "?0",
                    "Sec-Ch-Ua-Platform": '"Windows"',
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                }

                print(
                    f"[INFO] Tentativa {i + 1}/{len(user_agents)} com User-Agent: {ua[:50]}..."
                )

                # Tenta Web Unlocker para hosts bloqueados (ex: revendamais)
                unlocker_content = _fetch_via_web_unlocker(url, headers)
                if unlocker_content is not None:
                    print(f"[INFO] Conteúdo obtido via Web Unlocker.")

                    class _FakeResponse:
                        def __init__(self, content):
                            self.content = content
                            self.text = content.decode("utf-8", errors="ignore")

                    response = _FakeResponse(unlocker_content)
                    break

                response = requests.get(
                    url,
                    headers=headers,
                    timeout=30,
                    allow_redirects=True,
                )
                response.raise_for_status()

                # Verifica se não foi bloqueado
                if (
                    "403" in response.text[:100]
                    or "forbidden" in response.text[:100].lower()
                ):
                    print(
                        f"[AVISO] Bloqueio detectado na resposta, tentando próximo User-Agent..."
                    )
                    continue

                print(f"[INFO] Requisição bem-sucedida com User-Agent: {ua[:50]}...")
                break

            except requests.RequestException as e:
                last_error = e
                print(f"[AVISO] Tentativa {i + 1} falhou: {e}")
                if i < len(user_agents) - 1:
                    continue
                else:
                    print(f"[ERRO] Erro de requisição para URL {url}: {e}")
                    raise
            except Exception as e:
                last_error = e
                print(f"[AVISO] Erro inesperado na tentativa {i + 1}: {e}")
                if i < len(user_agents) - 1:
                    continue
                else:
                    print(f"[ERRO] Erro crítico ao processar URL {url}: {e}")
                    raise
        else:
            # Se todas as tentativas falharam
            print(f"[ERRO] Todas as tentativas de User-Agent falharam para URL {url}")
            if last_error:
                raise last_error
            raise requests.RequestException(
                f"Não foi possível acessar a URL após {len(user_agents)} tentativas"
            )

        data, format_type = self.detect_format(response.content, url)
        print(f"[INFO] Formato detectado: {format_type}")

        parser = self.select_parser(data, url)
        if parser:
            return parser.parse(data, url)
        else:
            print(f"[ERRO] Nenhum parser adequado encontrado para URL: {url}")
            return []

    def _generate_stats(self, vehicles: List[Dict]) -> Dict:
        """Gera estatísticas dos veículos processados"""
        stats = {"por_tipo": {}, "top_marcas": {}, "parsers_utilizados": {}}

        for vehicle in vehicles:
            tipo = vehicle.get("tipo", "indefinido")
            stats["por_tipo"][tipo] = stats["por_tipo"].get(tipo, 0) + 1

            marca = vehicle.get("marca", "indefinido")
            stats["top_marcas"][marca] = stats["top_marcas"].get(marca, 0) + 1

        return stats


# ─── SSRF protection ─────────────────────────────────────────────────────────

_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / AWS metadata
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def validate_source_url(url: str) -> None:
    """
    Raises ValueError if the URL is not a safe public HTTP/HTTPS address.
    Blocks private/loopback/link-local IP ranges to prevent SSRF.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"URL scheme '{parsed.scheme}' is not allowed. Use http or https."
        )
    if not parsed.netloc:
        raise ValueError("URL must include a host.")

    host = parsed.hostname or ""
    try:
        addr = ipaddress.ip_address(host)
        for net in _PRIVATE_NETWORKS:
            if addr in net:
                raise ValueError(
                    f"URL resolves to a private/reserved address ({addr}), which is not allowed."
                )
    except ValueError as exc:
        # Re-raise only if it came from our network check; hostname strings are fine
        if "private/reserved" in str(exc) or "not allowed" in str(exc):
            raise


def fetch_for_client(source_url: str, output_path: Path) -> dict:
    """
    Faz o fetch e parse para um cliente específico.
    Salva o resultado em output_path/data.json.
    Retorna dict com resultado e metadados.
    """
    validate_source_url(source_url)
    fetcher = UnifiedVehicleFetcher()

    vehicles = fetcher.process_url(source_url)
    parser_name = fetcher.last_parser_used or "unknown"

    stats = fetcher._generate_stats(vehicles)

    result = {
        "veiculos": vehicles,
        "_updated_at": datetime.now().isoformat(),
        "_total_count": len(vehicles),
        "_sources_processed": 1,
        "_parser_used": parser_name,
        "_statistics": stats,
    }

    output_path.mkdir(parents=True, exist_ok=True)
    data_file = output_path / "data.json"

    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[OK] Arquivo {data_file} salvo com sucesso! ({len(vehicles)} veículos)")
    return result
