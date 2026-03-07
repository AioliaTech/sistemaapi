"""
ClientManager — Gerencia o registro de clientes e seus dados no sistema multi-tenant.
"""

import json
import threading
import uuid
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field, asdict

from slugify import slugify

# Diretório base de dados
DATA_DIR = Path("data")
CLIENTS_REGISTRY = DATA_DIR / "clients.json"
CLIENTS_DIR = DATA_DIR / "clients"


@dataclass
class ClientConfig:
    id: str
    name: str
    slug: str
    source_url: str
    parser_used: str = "unknown"
    status: str = "pending"   # pending | running | error
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_updated_at: Optional[str] = None
    last_error: Optional[str] = None
    vehicle_count: int = 0
    custom_urls: Optional[str] = None  # Custom environment variables

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClientConfig":
        return cls(
            id=data["id"],
            name=data["name"],
            slug=data["slug"],
            source_url=data["source_url"],
            parser_used=data.get("parser_used", "unknown"),
            status=data.get("status", "pending"),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            last_updated_at=data.get("last_updated_at"),
            last_error=data.get("last_error"),
            vehicle_count=data.get("vehicle_count", 0),
            custom_urls=data.get("custom_urls"),
        )


class ClientManager:
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CLIENTS_DIR.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()   # Protects _clients list and registry file
        self._clients: List[ClientConfig] = []
        self._load_registry()

    # ─── Registry I/O ────────────────────────────────────────────────────────

    def _load_registry(self) -> None:
        with self._lock:
            if CLIENTS_REGISTRY.exists():
                try:
                    with open(CLIENTS_REGISTRY, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                    self._clients = [ClientConfig.from_dict(c) for c in raw]
                except Exception as e:
                    print(f"[WARN] Erro ao carregar registry: {e}")
                    self._clients = []
            else:
                self._clients = []
                self._save_registry_locked()

    def _save_registry(self) -> None:
        with self._lock:
            self._save_registry_locked()

    def _save_registry_locked(self) -> None:
        """Internal save — must be called with self._lock already held."""
        try:
            with open(CLIENTS_REGISTRY, "w", encoding="utf-8") as f:
                json.dump([c.to_dict() for c in self._clients], f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ERRO] Erro ao salvar registry: {e}")

    # ─── Slug helpers ─────────────────────────────────────────────────────────

    def _generate_slug(self, name: str, exclude_id: Optional[str] = None) -> str:
        base = slugify(name, allow_unicode=False, separator="-")
        if not base:
            base = "cliente"

        existing_slugs = {
            c.slug for c in self._clients
            if c.id != exclude_id
        }

        if base not in existing_slugs:
            return base

        counter = 2
        while f"{base}-{counter}" in existing_slugs:
            counter += 1
        return f"{base}-{counter}"

    # ─── CRUD ─────────────────────────────────────────────────────────────────

    def list_clients(self) -> List[ClientConfig]:
        with self._lock:
            return list(self._clients)

    def get_client(self, client_id: str) -> Optional[ClientConfig]:
        with self._lock:
            for c in self._clients:
                if c.id == client_id:
                    return c
            return None

    def get_client_by_slug(self, slug: str) -> Optional[ClientConfig]:
        with self._lock:
            for c in self._clients:
                if c.slug == slug:
                    return c
            return None

    def create_client(self, name: str, source_url: str, custom_urls: Optional[str] = None) -> ClientConfig:
        with self._lock:
            slug = self._generate_slug(name)
            client = ClientConfig(
                id=str(uuid.uuid4()),
                name=name,
                slug=slug,
                source_url=source_url,
                status="pending",
                custom_urls=custom_urls,
            )
            self._clients.append(client)
            self._save_registry_locked()
        # Cria diretório do cliente (outside lock — filesystem op)
        self.get_client_data_path(slug).mkdir(parents=True, exist_ok=True)
        return client

    def update_client(self, client_id: str, name: str, source_url: str, custom_urls: Optional[str] = None) -> Optional[ClientConfig]:
        with self._lock:
            client = None
            for c in self._clients:
                if c.id == client_id:
                    client = c
                    break
            if not client:
                return None

            old_slug = client.slug
            new_slug = self._generate_slug(name, exclude_id=client_id)

            client.name = name
            client.slug = new_slug
            client.source_url = source_url
            client.custom_urls = custom_urls
            self._save_registry_locked()

        # Renomeia diretório se o slug mudou (outside lock — filesystem op)
        if old_slug != new_slug:
            old_path = self.get_client_data_path(old_slug)
            new_path = self.get_client_data_path(new_slug)
            if old_path.exists():
                old_path.rename(new_path)

        return client

    def delete_client(self, client_id: str) -> bool:
        with self._lock:
            client = None
            for c in self._clients:
                if c.id == client_id:
                    client = c
                    break
            if not client:
                return False
            self._clients = [c for c in self._clients if c.id != client_id]
            self._save_registry_locked()
            slug = client.slug

        # Remove diretório de dados (outside lock — filesystem op)
        client_path = self.get_client_data_path(slug)
        if client_path.exists():
            shutil.rmtree(client_path)
        return True

    # ─── Status updates ───────────────────────────────────────────────────────

    def update_client_status(
        self,
        client_id: str,
        status: str,
        parser_used: Optional[str] = None,
        vehicle_count: int = 0,
        error: Optional[str] = None,
    ) -> None:
        with self._lock:
            client = None
            for c in self._clients:
                if c.id == client_id:
                    client = c
                    break
            if not client:
                return
            client.status = status
            client.last_updated_at = datetime.now(timezone.utc).isoformat()
            if parser_used:
                client.parser_used = parser_used
            if status == "running":
                client.vehicle_count = vehicle_count
                client.last_error = None
            elif status == "error":
                client.last_error = error
            self._save_registry_locked()

    # ─── Path helpers ─────────────────────────────────────────────────────────

    def get_client_data_path(self, slug: str) -> Path:
        return CLIENTS_DIR / slug

    def get_client_data_file(self, slug: str) -> Path:
        return CLIENTS_DIR / slug / "data.json"

    def load_client_vehicles(self, slug: str) -> Optional[Dict]:
        data_file = self.get_client_data_file(slug)
        if not data_file.exists():
            return None
        try:
            with open(data_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERRO] Erro ao carregar dados do cliente {slug}: {e}")
            return None
