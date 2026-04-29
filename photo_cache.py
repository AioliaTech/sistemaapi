"""
photo_cache.py — Sistema de cache de fotos para redução de tokens da IA.

Substitui URLs longas de fotos (~84 chars) por URLs curtas servidas via
FastAPI StaticFiles no próprio domínio (~42 chars). Redução de ~50% nos
tokens gastos com URLs de fotos.

Armazenamento: Volume Hetzner montado em PHOTO_DIR (default: /mnt/api-estoque-carmillion)
Serving:       FastAPI StaticFiles em /f (montado em main.py)
Persistência:  SQLite em PHOTO_DB_PATH (default: /app/data/photo_cache.db)

Uso:
    from photo_cache import photo_cache

    # No ciclo global (scheduler._fetch_all_clients):
    photo_cache.cycle_start()
    try:
        ...processar clientes...
    finally:
        removed = photo_cache.cycle_end()

    # Por cliente (scheduler._fetch_client), após montar all_vehicles:
    if photo_cache.is_enabled():
        all_vehicles = photo_cache.resolve_all_vehicles_sync(all_vehicles)
"""

import asyncio
import hashlib
import os
import sqlite3
import time
from pathlib import Path
from typing import List, Optional, Tuple

import aiofiles
import httpx


# ─── Helpers ──────────────────────────────────────────────────────────────────

_BASE62_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def _to_base62(n: int) -> str:
    """Converte inteiro para string base62."""
    if n == 0:
        return "0"
    parts = []
    while n:
        parts.append(_BASE62_CHARS[n % 62])
        n //= 62
    return "".join(reversed(parts))


def _short_name_for_url(url: str) -> str:
    """
    Gera nome curto determinístico para uma URL.
    MD5(url) → primeiros 6 bytes → int big-endian → base62 → 8 chars + extensão original.
    Exemplo: 'a9Xe83kL.jpg'
    """
    clean_url = url.split("?")[0]
    ext = os.path.splitext(clean_url)[1].lower()
    if not ext or len(ext) > 5:
        ext = ".jpg"

    digest = hashlib.md5(url.encode("utf-8")).digest()[:6]  # 6 bytes = 48 bits
    num = int.from_bytes(digest, "big")
    name = _to_base62(num).ljust(8, "0")[:8]
    return f"{name}{ext}"


# ─── PhotoCache ───────────────────────────────────────────────────────────────


class PhotoCache:
    """
    Serviço de cache de fotos com ciclo de vida alinhado ao scheduler global.

    Thread-safety: cada operação SQLite abre/fecha sua própria conexão.
    Async: resolve_all_vehicles_sync cria um event loop dedicado por chamada
    (seguro nas threads do BackgroundScheduler que não têm event loop ativo).
    """

    def __init__(self) -> None:
        self._enabled: bool = (
            os.getenv("PHOTO_CACHE_ENABLED", "false").strip().lower() == "true"
        )
        self._photo_dir: str = os.getenv(
            "PHOTO_DIR", "/mnt/api-estoque-carmillion"
        ).rstrip("/")
        self._short_domain: str = os.getenv(
            "SHORT_DOMAIN", "https://api.revendai.com/f"
        ).rstrip("/")
        self._db_path: str = os.getenv(
            "PHOTO_DB_PATH", "/app/data/photo_cache.db"
        )
        # Anon key para buckets Supabase que exigem apikey mesmo sendo públicos
        self._supabase_anon_key: str = os.getenv("SUPABASE_ANON_KEY", "")

        if self._enabled:
            if Path(self._photo_dir).is_dir():
                self._init_db()
                print(
                    f"[photo_cache] ✓ Ativo | dir={self._photo_dir} | "
                    f"db={self._db_path} | domain={self._short_domain}"
                )
            else:
                print(
                    f"[photo_cache] ⚠️  PHOTO_CACHE_ENABLED=true mas "
                    f"'{self._photo_dir}' não existe — cache desativado"
                )
                self._enabled = False

    # ── Interface pública ─────────────────────────────────────────────────────

    def is_enabled(self) -> bool:
        """Retorna True se o cache está ativo e o diretório de fotos existe."""
        return self._enabled

    def cycle_start(self) -> None:
        """
        Marca todas as entradas no SQLite como seen=0.
        Chamado UMA VEZ antes do loop global de atualização (_fetch_all_clients).
        """
        if not self._enabled:
            return
        conn = self._get_conn()
        try:
            conn.execute("UPDATE photos SET seen=0")
            conn.commit()
            count = conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
            print(f"[photo_cache] cycle_start: {count} entradas marcadas como não-vistas")
        finally:
            conn.close()

    def cycle_end(self) -> int:
        """
        Remove do disco e do SQLite todas as fotos com seen=0 (órfãs —
        veículos que saíram do estoque). Chamado no finally do loop global,
        garantindo execução mesmo se o parse explodir.
        Retorna contagem de fotos removidas.
        """
        if not self._enabled:
            return 0

        conn = self._get_conn()
        try:
            orphans: List[Tuple[str, ...]] = conn.execute(
                "SELECT short_name FROM photos WHERE seen=0"
            ).fetchall()

            removed = 0
            for (short_name,) in orphans:
                path = Path(self._photo_dir) / short_name
                try:
                    if path.exists():
                        path.unlink()
                        removed += 1
                    # Se já não existia no disco, apenas remove do SQLite (sem incrementar)
                except Exception as exc:
                    print(f"[photo_cache] Erro ao deletar '{path}': {exc}")

            if orphans:
                conn.execute("DELETE FROM photos WHERE seen=0")
                conn.commit()

            return removed
        finally:
            conn.close()

    def mark_existing_photos_seen(self, vehicles: List[dict]) -> None:
        """
        Protege as fotos do último parse bem-sucedido quando o parse atual falha.
        Marca seen=1 para todas as URLs já em cache, impedindo que cycle_end()
        as delete do disco — preserva o estoque desatualizado em vez de ficar sem fotos.
        """
        if not self._enabled:
            return
        for vehicle in vehicles:
            fotos = vehicle.get("fotos")
            if fotos and isinstance(fotos, list):
                for url in fotos:
                    if isinstance(url, str) and url.startswith("http"):
                        if self._db_get(url) is not None:
                            self._db_mark_seen(url)

    def resolve_all_vehicles_sync(self, vehicles: List[dict]) -> List[dict]:
        """
        Wrapper síncrono para uso no BackgroundScheduler (thread sem event loop).
        Cria um novo event loop dedicado, processa todas as fotos em paralelo
        (Semaphore(20)), fecha o loop e retorna os veículos com URLs atualizadas.
        Em caso de falha total, retorna os veículos intactos (URLs originais).
        """
        if not self._enabled:
            return vehicles

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self._resolve_all_vehicles_async(vehicles)
            )
        except Exception as exc:
            print(f"[photo_cache] Erro fatal em resolve_all_vehicles_sync: {exc}")
            return vehicles
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    # ── Internos async ────────────────────────────────────────────────────────

    async def _resolve_all_vehicles_async(
        self, vehicles: List[dict]
    ) -> List[dict]:
        """
        Um único httpx.AsyncClient compartilhado (connection pool) para todo
        o ciclo de um cliente. asyncio.Semaphore(20) limita downloads simultâneos.
        """
        semaphore = asyncio.Semaphore(20)

        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "RevendAI-PhotoCache/1.0"},
        ) as http:
            result = []
            for vehicle in vehicles:
                fotos = vehicle.get("fotos")
                if fotos and isinstance(fotos, list):
                    # Separa índices de URLs válidas para processar apenas elas
                    valid_indices = [
                        i for i, u in enumerate(fotos)
                        if isinstance(u, str) and u.startswith("http")
                    ]
                    if valid_indices:
                        tasks = [
                            self._resolve_with_sem(fotos[i], semaphore, http)
                            for i in valid_indices
                        ]
                        resolved = await asyncio.gather(*tasks)

                        # Reconstrói a lista preservando entradas não-URL intactas
                        new_fotos = list(fotos)
                        for idx, resolved_url in zip(valid_indices, resolved):
                            new_fotos[idx] = resolved_url
                        vehicle = {**vehicle, "fotos": new_fotos}
                result.append(vehicle)

        return result

    async def _resolve_with_sem(
        self,
        url: str,
        semaphore: asyncio.Semaphore,
        http: httpx.AsyncClient,
    ) -> str:
        """
        Resolve uma URL de foto para URL curta.
        - Cache hit (downloaded=1): marca seen=1, retorna URL curta sem I/O de rede.
        - Cache miss: aguarda semáforo, baixa a foto, salva em disco, upsert SQLite.
        - Falha: retorna URL original (degradação graceful — não quebra o ciclo).
        """
        short_name = _short_name_for_url(url)
        row = self._db_get(url)

        if row is not None and row["downloaded"] == 1:
            # Cache hit — atualiza seen e retorna sem download
            self._db_mark_seen(url)
            return f"{self._short_domain}/{short_name}"

        # Cache miss — precisa baixar
        async with semaphore:
            dest_path = Path(self._photo_dir) / short_name
            success = await self._do_download_and_save(url, dest_path, http)

        self._db_upsert(url, short_name, success)

        if success:
            return f"{self._short_domain}/{short_name}"
        # Falha: URL original mantida, downloaded=0 → tentará novamente no próximo ciclo
        return url

    async def _do_download_and_save(
        self,
        url: str,
        dest_path: Path,
        http: httpx.AsyncClient,
    ) -> bool:
        """
        Baixa a foto via httpx e salva em disco via aiofiles.
        Retorna True em sucesso, False em qualquer exceção (erro logado, sem raise).
        """
        try:
            # Supabase Storage exige o header apikey mesmo em buckets públicos
            extra_headers = {}
            if "supabase.co" in url and self._supabase_anon_key:
                extra_headers["apikey"] = self._supabase_anon_key

            resp = await http.get(url, headers=extra_headers)
            resp.raise_for_status()
            content = resp.content

            if not content:
                print(f"[photo_cache] Resposta vazia para {url}")
                return False

            async with aiofiles.open(dest_path, "wb") as f:
                await f.write(content)

            return True

        except httpx.HTTPStatusError as exc:
            print(f"[photo_cache] HTTP {exc.response.status_code} ao baixar {url}")
            return False
        except httpx.RequestError as exc:
            print(f"[photo_cache] Erro de rede ao baixar {url}: {exc}")
            return False
        except OSError as exc:
            print(f"[photo_cache] Erro ao salvar {dest_path}: {exc}")
            return False
        except Exception as exc:
            print(f"[photo_cache] Erro inesperado ao processar {url}: {exc}")
            return False

    # ── Helpers SQLite (conexão por chamada — thread-safe) ────────────────────

    def _init_db(self) -> None:
        """Cria a tabela e índice de mapeamento se não existirem."""
        db_dir = os.path.dirname(self._db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS photos (
                    original_url TEXT PRIMARY KEY,
                    short_name   TEXT NOT NULL,
                    downloaded   INTEGER NOT NULL DEFAULT 0,
                    seen         INTEGER NOT NULL DEFAULT 0,
                    created_at   REAL NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_photos_seen ON photos (seen)"
            )
            conn.commit()
        finally:
            conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        """Abre uma nova conexão SQLite com row_factory configurado. Deve ser fechada pelo caller."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _db_get(self, url: str) -> Optional[sqlite3.Row]:
        """Retorna a linha para a URL original ou None se não existir."""
        conn = self._get_conn()
        try:
            return conn.execute(
                "SELECT downloaded, seen FROM photos WHERE original_url=?",
                (url,),
            ).fetchone()
        finally:
            conn.close()

    def _db_mark_seen(self, url: str) -> None:
        """Marca uma entrada existente como seen=1 (cache hit neste ciclo)."""
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE photos SET seen=1 WHERE original_url=?", (url,)
            )
            conn.commit()
        finally:
            conn.close()

    def _db_upsert(self, url: str, short_name: str, success: bool) -> None:
        """
        INSERT OR REPLACE do mapeamento url → short_name com resultado do download.
        downloaded=1 = arquivo existe em disco.
        seen=1 apenas se download bem-sucedido (foto visível neste ciclo).
        """
        downloaded = 1 if success else 0
        seen = 1 if success else 0
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO photos (original_url, short_name, downloaded, seen, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(original_url) DO UPDATE SET
                    downloaded = excluded.downloaded,
                    seen       = excluded.seen
                """,
                (url, short_name, downloaded, seen, time.time()),
            )
            conn.commit()
        finally:
            conn.close()


# ─── Singleton ────────────────────────────────────────────────────────────────
# Instanciado na importação do módulo. Lê env vars uma única vez no startup.
# is_enabled() retorna False se PHOTO_CACHE_ENABLED != "true" ou PHOTO_DIR não existir.

photo_cache = PhotoCache()
