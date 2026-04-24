"""
route_admin.py — Rotas JSON autenticadas para gerenciamento de clientes.
"""

import threading
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import require_api_auth
from core import client_manager, scheduler, BASE_URL

router = APIRouter(prefix="/admin", tags=["admin"])


# ─── Pydantic models ──────────────────────────────────────────────────────────


class CreateClientRequest(BaseModel):
    name: str
    source_url: Optional[str] = None
    custom_urls: Optional[str] = None


class UpdateClientRequest(BaseModel):
    name: str
    source_url: Optional[str] = None
    custom_urls: Optional[str] = None


# ─── Routes ───────────────────────────────────────────────────────────────────


@router.get("/clients")
def admin_list_clients(_auth=Depends(require_api_auth)):
    clients = client_manager.list_clients()
    clients_data = []
    for c in clients:
        status = c.status
        if c.status == "running" and c.vehicle_count == 0:
            status = "error"
        clients_data.append(
            {**c.to_dict(), "status": status, "base_url": f"{BASE_URL}/{c.slug}"}
        )

    status_priority = {"error": 0, "pending": 1, "running": 2}
    clients_data.sort(
        key=lambda x: (status_priority.get(x["status"], 3), x["name"].lower())
    )
    return clients_data


@router.post("/clients", status_code=201)
def admin_create_client(body: CreateClientRequest, _auth=Depends(require_api_auth)):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Nome é obrigatório")

    source_url = body.source_url.strip() if body.source_url else ""
    custom_urls = body.custom_urls.strip() if body.custom_urls else None

    if not source_url and not custom_urls:
        raise HTTPException(
            status_code=400, detail="URL da fonte ou Custom URLs é obrigatório"
        )

    client = client_manager.create_client(
        name=body.name.strip(),
        source_url=source_url,
        custom_urls=custom_urls,
    )
    scheduler.add_client_job(client.id, run_now=True)
    return {**client.to_dict(), "base_url": f"{BASE_URL}/{client.slug}"}


@router.put("/clients/{client_id}")
def admin_update_client(
    client_id: str,
    body: UpdateClientRequest,
    _auth=Depends(require_api_auth),
):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Nome é obrigatório")

    source_url = body.source_url.strip() if body.source_url else ""
    custom_urls = body.custom_urls.strip() if body.custom_urls else None

    if not source_url and not custom_urls:
        raise HTTPException(
            status_code=400, detail="URL da fonte ou Custom URLs é obrigatório"
        )

    client = client_manager.update_client(
        client_id=client_id,
        name=body.name.strip(),
        source_url=source_url,
        custom_urls=custom_urls,
    )
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    return {**client.to_dict(), "base_url": f"{BASE_URL}/{client.slug}"}


@router.delete("/clients/{client_id}", status_code=204)
def admin_delete_client(client_id: str, _auth=Depends(require_api_auth)):
    scheduler.remove_client_job(client_id)
    deleted = client_manager.delete_client(client_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")


@router.post("/clients/{client_id}/redeploy")
def admin_redeploy_client(client_id: str, _auth=Depends(require_api_auth)):
    client = client_manager.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    scheduler.trigger_now(client_id)
    return {
        "message": f"Redeploy iniciado para '{client.name}'",
        "client_id": client_id,
    }


@router.post("/clients/redeploy-all")
def admin_redeploy_all(_auth=Depends(require_api_auth)):
    """Força atualização imediata de todos os clientes em background."""
    clients = client_manager.list_clients()

    def _run():
        scheduler._fetch_all_clients()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return {
        "message": f"Redeploy global iniciado para {len(clients)} cliente(s)",
        "total": len(clients),
    }
