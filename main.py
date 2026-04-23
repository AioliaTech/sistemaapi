"""
main.py — RevendAI Multi-Tenant API Platform
FastAPI application that hosts all client vehicle-stock APIs in a single container.
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

from fastapi import FastAPI, Request, Depends, HTTPException, Form, status
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from unidecode import unidecode
from rapidfuzz import fuzz

from client_manager import ClientManager
from auth import (
    authenticate_user,
    create_access_token,
    require_auth,
    require_api_auth,
    COOKIE_NAME,
)
from scheduler import MultiTenantScheduler
from vehicle_mappings import MAPEAMENTO_CATEGORIAS, MAPEAMENTO_MOTOS

# ─── App setup ────────────────────────────────────────────────────────────────

app = FastAPI(title="RevendAI Panel", docs_url=None, redoc_url=None)

BASE_URL = os.getenv("BASE_URL", "https://api.revendai.com")

# Static files & templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Global singletons
client_manager = ClientManager()
scheduler = MultiTenantScheduler(client_manager)

# ─── Startup / Shutdown ───────────────────────────────────────────────────────


@app.on_event("startup")
def on_startup():
    print("=" * 80)
    print(f"[APP] ⚡ STARTUP EVENT TRIGGERED em {datetime.now()}")
    print("=" * 80)
    scheduler.start()
    print("[APP] ✓ RevendAI Multi-Tenant Platform iniciado")
    print("=" * 80)


@app.on_event("shutdown")
def on_shutdown():
    print(f"[APP] 🛑 SHUTDOWN EVENT TRIGGERED em {datetime.now()}")
    scheduler.shutdown()
    print("[APP] ✓ Scheduler desligado")


# ─── Pydantic models ──────────────────────────────────────────────────────────


class CreateClientRequest(BaseModel):
    name: str
    source_url: Optional[str] = None
    custom_urls: Optional[str] = None


class UpdateClientRequest(BaseModel):
    name: str
    source_url: Optional[str] = None
    custom_urls: Optional[str] = None


# ─── Auth routes ──────────────────────────────────────────────────────────────


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="login.html", context={"error": None}
    )


@app.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    if not authenticate_user(email, password):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "E-mail ou senha incorretos"},
            status_code=401,
        )
    token = create_access_token({"sub": email})
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=86400,  # 24h
        samesite="lax",
    )
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


# ─── Dashboard ────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
def root_redirect():
    return RedirectResponse(url="/dashboard", status_code=302)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, _auth=Depends(require_auth)):
    clients = client_manager.list_clients()
    clients_data = []
    for c in clients:
        # Treat 0 vehicles as error
        status = c.status
        if c.status == "running" and c.vehicle_count == 0:
            status = "error"

        # Adiciona estatísticas de categorização
        cat_stats = client_manager.get_categorization_stats(c.slug)

        clients_data.append(
            {
                **c.to_dict(),
                "status": status,
                "base_url": f"{BASE_URL}/{c.slug}",
                "categorization_stats": cat_stats,
            }
        )

    # Sort: errors first, then by alphabetical order within each status
    status_priority = {"error": 0, "pending": 1, "running": 2}
    clients_data.sort(
        key=lambda x: (status_priority.get(x["status"], 3), x["name"].lower())
    )

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "clients": clients_data,
            "base_url": BASE_URL,
        },
    )


# ─── Admin API routes (JSON, JWT auth) ───────────────────────────────────────


@app.get("/admin/clients")
def admin_list_clients(_auth=Depends(require_api_auth)):
    clients = client_manager.list_clients()
    clients_data = []
    for c in clients:
        # Treat 0 vehicles as error
        status = c.status
        if c.status == "running" and c.vehicle_count == 0:
            status = "error"

        clients_data.append(
            {**c.to_dict(), "status": status, "base_url": f"{BASE_URL}/{c.slug}"}
        )

    # Sort: errors first, then by alphabetical order within each status
    status_priority = {"error": 0, "pending": 1, "running": 2}
    clients_data.sort(
        key=lambda x: (status_priority.get(x["status"], 3), x["name"].lower())
    )

    return clients_data


@app.post("/admin/clients", status_code=201)
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
        source_url=source_url,  # Empty string if using only custom URLs
        custom_urls=custom_urls,
    )
    # Schedule and trigger immediate fetch
    scheduler.add_client_job(client.id, run_now=True)

    return {**client.to_dict(), "base_url": f"{BASE_URL}/{client.slug}"}


@app.put("/admin/clients/{client_id}")
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
        source_url=source_url,  # Empty string if using only custom URLs
        custom_urls=custom_urls,
    )
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    return {**client.to_dict(), "base_url": f"{BASE_URL}/{client.slug}"}


@app.delete("/admin/clients/{client_id}", status_code=204)
def admin_delete_client(client_id: str, _auth=Depends(require_api_auth)):
    scheduler.remove_client_job(client_id)
    deleted = client_manager.delete_client(client_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")


@app.post("/admin/clients/{client_id}/redeploy")
def admin_redeploy_client(client_id: str, _auth=Depends(require_api_auth)):
    client = client_manager.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    scheduler.trigger_now(client_id)
    return {
        "message": f"Redeploy iniciado para '{client.name}'",
        "client_id": client_id,
    }


@app.post("/admin/clients/redeploy-all")
def admin_redeploy_all(_auth=Depends(require_api_auth)):
    """Força atualização imediata de todos os clientes em background."""
    import threading

    clients = client_manager.list_clients()

    def _run():
        scheduler._fetch_all_clients()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return {
        "message": f"Redeploy global iniciado para {len(clients)} cliente(s)",
        "total": len(clients),
    }


# ─── Vehicle search engine (reused from apiv4) ────────────────────────────────

FALLBACK_PRIORITY = [
    "motor",
    "portas",
    "cor",
    "combustivel",
    "opcionais",
    "cambio",
    "KmMax",
    "AnoMax",
    "modelo",
    "marca",
    "categoria",
]

OPCIONAIS_MAP = {
    1: [
        "ar-condicionado",
        "ar condicionado",
        "arcondicionado",
        "ar-condiciona",
        "ar condiciona",
    ],
    2: ["airbag", "air bag", "air-bag"],
    3: [
        "vidros eletricos",
        "vidros elétricos",
        "vidro eletrico",
        "vidro elétrico",
        "vidros eletrico",
    ],
    4: ["abs"],
    5: [
        "direcao hidraulica",
        "direção hidráulica",
        "direcao hidraulica",
        "dir hidraulica",
        "dir. hidraulica",
    ],
    6: [
        "direcao eletrica",
        "direção elétrica",
        "direcao eletrica",
        "dir eletrica",
        "dir. eletrica",
    ],
    7: ["7 lugar", "7 lugares", "sete lugar", "sete lugares"],
}


def normalizar_opcional(texto: str) -> str:
    if not texto:
        return ""
    texto = unidecode(str(texto)).lower()
    texto = texto.replace("-", " ").replace(".", "")
    texto = " ".join(texto.split())
    return texto.strip()


def opcionais_para_codigos(opcionais_str: str) -> List[int]:
    if not opcionais_str:
        return []
    codigos = set()
    opcionais_lista = [op.strip() for op in str(opcionais_str).split(",")]
    for opcional in opcionais_lista:
        opcional_norm = normalizar_opcional(opcional)
        if not opcional_norm:
            continue
        for codigo, variacoes in OPCIONAIS_MAP.items():
            for variacao in variacoes:
                variacao_norm = normalizar_opcional(variacao)
                if opcional_norm == variacao_norm or variacao_norm in opcional_norm:
                    codigos.add(codigo)
                    break
    return sorted(list(codigos))


from dataclasses import dataclass


@dataclass
class SearchResult:
    vehicles: List[Dict[str, Any]]
    total_found: int
    fallback_info: Dict[str, Any]
    removed_filters: List[str]


class VehicleSearchEngine:
    def __init__(self):
        self.exact_fields = ["tipo", "marca", "cambio", "motor", "portas"]

    def _any_csv_value_matches(self, raw_val, field_val, vehicle_type, word_matcher):
        if not raw_val:
            return False
        for val in self.split_multi_value(raw_val):
            words = val.split()
            ok, _ = word_matcher(words, field_val, vehicle_type)
            if ok:
                return True
        return False

    def normalize_text(self, text: str) -> str:
        if not text:
            return ""
        return unidecode(str(text)).lower().replace("-", "").replace(" ", "").strip()

    def convert_price(self, price_str: Any) -> Optional[float]:
        if not price_str:
            return None
        try:
            if isinstance(price_str, (int, float)):
                return float(price_str)
            cleaned = (
                str(price_str)
                .replace(",", "")
                .replace("R$", "")
                .replace(".", "")
                .strip()
            )
            return float(cleaned) / 100 if len(cleaned) > 2 else float(cleaned)
        except (ValueError, TypeError):
            return None

    def convert_year(self, year_str: Any) -> Optional[int]:
        if not year_str:
            return None
        try:
            cleaned = (
                str(year_str)
                .strip()
                .replace("\n", "")
                .replace("\r", "")
                .replace(" ", "")
            )
            return int(cleaned)
        except (ValueError, TypeError):
            return None

    def convert_km(self, km_str: Any) -> Optional[int]:
        if not km_str:
            return None
        try:
            cleaned = str(km_str).replace(".", "").replace(",", "").strip()
            return int(cleaned)
        except (ValueError, TypeError):
            return None

    def convert_cc(self, cc_str: Any) -> Optional[float]:
        if not cc_str:
            return None
        try:
            if isinstance(cc_str, (int, float)):
                return float(cc_str)
            cleaned = (
                str(cc_str).replace(",", ".").replace("L", "").replace("l", "").strip()
            )
            value = float(cleaned)
            if value < 10:
                return value * 1000
            return value
        except (ValueError, TypeError):
            return None

    def get_max_value_from_range_param(self, param_value: str) -> str:
        if not param_value:
            return param_value
        if "," in param_value:
            try:
                values = [float(v.strip()) for v in param_value.split(",") if v.strip()]
                if values:
                    return str(max(values))
            except (ValueError, TypeError):
                pass
        return param_value

    def find_category_by_model(self, model: str) -> Optional[str]:
        if not model:
            return None
        normalized_model = self.normalize_text(model)
        if normalized_model in MAPEAMENTO_MOTOS:
            _, category = MAPEAMENTO_MOTOS[normalized_model]
            return category
        model_words = normalized_model.split()
        for word in model_words:
            if len(word) >= 3 and word in MAPEAMENTO_MOTOS:
                _, category = MAPEAMENTO_MOTOS[word]
                return category
        for key, (_, category) in MAPEAMENTO_MOTOS.items():
            if key in normalized_model or normalized_model in key:
                return category
        if normalized_model in MAPEAMENTO_CATEGORIAS:
            return MAPEAMENTO_CATEGORIAS[normalized_model]
        for word in model_words:
            if len(word) >= 3 and word in MAPEAMENTO_CATEGORIAS:
                return MAPEAMENTO_CATEGORIAS[word]
        for key, category in MAPEAMENTO_CATEGORIAS.items():
            if key in normalized_model or normalized_model in key:
                return category
        return None

    def exact_match(self, query_words, field_content, *args) -> Tuple[bool, str]:
        if not query_words or not field_content:
            return False, "empty_input"
        normalized_content = self.normalize_text(field_content)
        for word in query_words:
            normalized_word = self.normalize_text(word)
            if len(normalized_word) < 2:
                continue
            if normalized_word not in normalized_content:
                return False, f"exact_miss: '{normalized_word}' não encontrado"
        return True, "exact_match: todas as palavras encontradas"

    def _fuzzy_match_all_words(
        self, query_words, field_content, fuzzy_threshold
    ) -> Tuple[bool, str]:
        normalized_content = self.normalize_text(field_content)
        matched_words = []
        match_details = []
        for word in query_words:
            normalized_word = self.normalize_text(word)
            if len(normalized_word) < 2:
                continue
            word_matched = False
            if normalized_word in normalized_content:
                matched_words.append(normalized_word)
                match_details.append(f"exact:{normalized_word}")
                word_matched = True
            if not word_matched:
                content_words = normalized_content.split()
                for content_word in content_words:
                    if content_word.startswith(normalized_word):
                        matched_words.append(normalized_word)
                        match_details.append(f"starts_with:{normalized_word}")
                        word_matched = True
                        break
            if not word_matched and len(normalized_word) >= 3:
                content_words = normalized_content.split()
                for content_word in content_words:
                    if normalized_word in content_word:
                        matched_words.append(normalized_word)
                        match_details.append(
                            f"substring:{normalized_word}>{content_word}"
                        )
                        word_matched = True
                        break
            if not word_matched and len(normalized_word) >= 3:
                partial_score = fuzz.partial_ratio(normalized_content, normalized_word)
                ratio_score = fuzz.ratio(normalized_content, normalized_word)
                max_score = max(partial_score, ratio_score)
                if max_score >= fuzzy_threshold:
                    matched_words.append(normalized_word)
                    match_details.append(f"fuzzy:{normalized_word}({max_score})")
                    word_matched = True
            if not word_matched:
                return False, f"moto_strict: palavra '{normalized_word}' não encontrada"
        if len(matched_words) >= len(
            [w for w in query_words if len(self.normalize_text(w)) >= 2]
        ):
            return True, f"moto_all_match: {', '.join(match_details)}"
        return False, "moto_strict: nem todas as palavras encontradas"

    def _fuzzy_match_any_word(
        self, query_words, field_content, fuzzy_threshold
    ) -> Tuple[bool, str]:
        normalized_content = self.normalize_text(field_content)
        for word in query_words:
            normalized_word = self.normalize_text(word)
            if len(normalized_word) < 2:
                continue
            if normalized_word in normalized_content:
                return True, f"exact_match: {normalized_word}"
            content_words = normalized_content.split()
            for content_word in content_words:
                if content_word.startswith(normalized_word):
                    return True, f"starts_with_match: {normalized_word}"
            if len(normalized_word) >= 3:
                for content_word in content_words:
                    if normalized_word in content_word:
                        return (
                            True,
                            f"substring_match: {normalized_word} in {content_word}",
                        )
                partial_score = fuzz.partial_ratio(normalized_content, normalized_word)
                ratio_score = fuzz.ratio(normalized_content, normalized_word)
                max_score = max(partial_score, ratio_score)
                if max_score >= fuzzy_threshold:
                    return True, f"fuzzy_match: {max_score}"
        return False, "no_match"

    def fuzzy_match(
        self, query_words, field_content, vehicle_type=None
    ) -> Tuple[bool, str]:
        if not query_words or not field_content:
            return False, "empty_input"
        fuzzy_threshold = 98 if vehicle_type == "moto" else 90
        if vehicle_type == "moto":
            return self._fuzzy_match_all_words(
                query_words, field_content, fuzzy_threshold
            )
        else:
            return self._fuzzy_match_any_word(
                query_words, field_content, fuzzy_threshold
            )

    def model_match(
        self, query_words, field_content, vehicle_type=None
    ) -> Tuple[bool, str]:
        exact_result, exact_reason = self.exact_match(query_words, field_content)
        if exact_result:
            return True, f"EXACT: {exact_reason}"
        fuzzy_result, fuzzy_reason = self.fuzzy_match(
            query_words, field_content, vehicle_type
        )
        if fuzzy_result:
            return True, f"FUZZY: {fuzzy_reason}"
        return False, f"NO_MATCH: exact({exact_reason}) + fuzzy({fuzzy_reason})"

    def split_multi_value(self, value: str) -> List[str]:
        if not value:
            return []
        return [v.strip() for v in str(value).split(",") if v.strip()]

    def apply_filters(self, vehicles, filters) -> List[Dict]:
        if not filters:
            return vehicles
        filtered_vehicles = list(vehicles)
        for filter_key, filter_value in filters.items():
            if not filter_value or not filtered_vehicles:
                continue
            if filter_key == "modelo":

                def matches(v, fv=filter_value):
                    vt = v.get("tipo", "")
                    for field in ["modelo", "titulo", "versao"]:
                        fval = str(v.get(field, ""))
                        if self._any_csv_value_matches(fv, fval, vt, self.model_match):
                            return True
                    return False

                filtered_vehicles = [v for v in filtered_vehicles if matches(v)]
            elif filter_key in ["cor", "categoria", "opcionais", "combustivel"]:

                def matches(v, fk=filter_key, fv=filter_value):
                    vt = v.get("tipo", "")
                    fval = str(v.get(fk, ""))
                    return self._any_csv_value_matches(fv, fval, vt, self.fuzzy_match)

                filtered_vehicles = [v for v in filtered_vehicles if matches(v)]
            elif filter_key in self.exact_fields:
                normalized_vals = [
                    self.normalize_text(v) for v in self.split_multi_value(filter_value)
                ]
                filtered_vehicles = [
                    v
                    for v in filtered_vehicles
                    if self.normalize_text(str(v.get(filter_key, "")))
                    in normalized_vals
                ]
        return filtered_vehicles

    def apply_range_filters(
        self, vehicles, valormax, anomax, kmmax, ccmax
    ) -> List[Dict]:
        filtered_vehicles = list(vehicles)
        if anomax:
            try:
                max_year = int(anomax)
                filtered_vehicles = [
                    v
                    for v in filtered_vehicles
                    if self.convert_year(v.get("ano")) is not None
                    and self.convert_year(v.get("ano")) <= max_year
                ]
            except ValueError:
                pass
        if kmmax:
            try:
                max_km = int(kmmax)
                filtered_vehicles = [
                    v
                    for v in filtered_vehicles
                    if self.convert_km(v.get("km")) is not None
                    and self.convert_km(v.get("km")) <= max_km
                ]
            except ValueError:
                pass
        return filtered_vehicles

    def sort_vehicles(self, vehicles, valormax, anomax, kmmax, ccmax) -> List[Dict]:
        if not vehicles:
            return vehicles
        if ccmax:
            try:
                target_cc = float(ccmax)
                if target_cc < 10:
                    target_cc *= 1000
                return sorted(
                    vehicles,
                    key=lambda v: abs(
                        (self.convert_cc(v.get("cilindrada")) or 0) - target_cc
                    ),
                )
            except ValueError:
                pass
        if valormax:
            try:
                target_price = float(valormax)
                return sorted(
                    vehicles,
                    key=lambda v: abs(
                        (self.convert_price(v.get("preco")) or 0) - target_price
                    ),
                )
            except ValueError:
                pass
        if kmmax:
            return sorted(
                vehicles, key=lambda v: self.convert_km(v.get("km")) or float("inf")
            )
        if anomax:
            return sorted(
                vehicles,
                key=lambda v: self.convert_year(v.get("ano")) or 0,
                reverse=True,
            )
        return sorted(
            vehicles,
            key=lambda v: self.convert_price(v.get("preco")) or 0,
            reverse=True,
        )

    def search_with_fallback(
        self, vehicles, filters, valormax, anomax, kmmax, ccmax, excluded_ids
    ) -> SearchResult:
        filtered_vehicles = self.apply_filters(vehicles, filters)
        filtered_vehicles = self.apply_range_filters(
            filtered_vehicles, valormax, anomax, kmmax, ccmax
        )
        if excluded_ids:
            filtered_vehicles = [
                v for v in filtered_vehicles if str(v.get("id")) not in excluded_ids
            ]
        if filtered_vehicles:
            sorted_vehicles = self.sort_vehicles(
                filtered_vehicles, valormax, anomax, kmmax, ccmax
            )
            return SearchResult(
                vehicles=sorted_vehicles[:6],
                total_found=len(sorted_vehicles),
                fallback_info={},
                removed_filters=[],
            )

        current_filters = dict(filters)
        removed_filters = []
        current_valormax = valormax
        current_anomax = anomax
        current_kmmax = kmmax
        current_ccmax = ccmax

        for filter_to_remove in FALLBACK_PRIORITY:
            if filter_to_remove == "KmMax" and current_kmmax:
                test_vehicles = self.apply_filters(vehicles, current_filters)
                vehicles_within_km_limit = [
                    v
                    for v in test_vehicles
                    if self.convert_km(v.get("km")) is not None
                    and self.convert_km(v.get("km")) <= int(current_kmmax)
                ]
                if not vehicles_within_km_limit:
                    current_kmmax = None
                    removed_filters.append("KmMax")
                else:
                    continue
            elif filter_to_remove == "AnoMax" and current_anomax:
                test_vehicles = self.apply_filters(vehicles, current_filters)
                vehicles_within_year_limit = [
                    v
                    for v in test_vehicles
                    if self.convert_year(v.get("ano")) is not None
                    and self.convert_year(v.get("ano")) <= int(current_anomax)
                ]
                if not vehicles_within_year_limit:
                    current_anomax = None
                    removed_filters.append("AnoMax")
                else:
                    continue
            elif filter_to_remove == "modelo" and filter_to_remove in current_filters:
                model_value = current_filters["modelo"]
                if (
                    "categoria" not in current_filters
                    or not current_filters["categoria"]
                ):
                    mapped_category = self.find_category_by_model(model_value)
                    if mapped_category:
                        current_filters = {
                            k: v for k, v in current_filters.items() if k != "modelo"
                        }
                        current_filters["categoria"] = mapped_category
                        removed_filters.append(
                            f"modelo({model_value})->categoria({mapped_category})"
                        )
                        filtered_vehicles = self.apply_filters(
                            vehicles, current_filters
                        )
                        filtered_vehicles = self.apply_range_filters(
                            filtered_vehicles,
                            current_valormax,
                            current_anomax,
                            current_kmmax,
                            current_ccmax,
                        )
                        if excluded_ids:
                            filtered_vehicles = [
                                v
                                for v in filtered_vehicles
                                if str(v.get("id")) not in excluded_ids
                            ]
                        if filtered_vehicles:
                            sorted_vehicles = self.sort_vehicles(
                                filtered_vehicles,
                                current_valormax,
                                current_anomax,
                                current_kmmax,
                                current_ccmax,
                            )
                            return SearchResult(
                                vehicles=sorted_vehicles[:6],
                                total_found=len(sorted_vehicles),
                                fallback_info={
                                    "fallback": {"removed_filters": removed_filters}
                                },
                                removed_filters=removed_filters,
                            )
                    else:
                        current_filters = {
                            k: v for k, v in current_filters.items() if k != "modelo"
                        }
                        removed_filters.append(f"modelo({model_value})")
                else:
                    current_filters = {
                        k: v for k, v in current_filters.items() if k != "modelo"
                    }
                    removed_filters.append(f"modelo({model_value})")
            elif filter_to_remove in current_filters:
                current_filters = {
                    k: v for k, v in current_filters.items() if k != filter_to_remove
                }
                removed_filters.append(filter_to_remove)
            else:
                continue

            filtered_vehicles = self.apply_filters(vehicles, current_filters)
            filtered_vehicles = self.apply_range_filters(
                filtered_vehicles,
                current_valormax,
                current_anomax,
                current_kmmax,
                current_ccmax,
            )
            if excluded_ids:
                filtered_vehicles = [
                    v for v in filtered_vehicles if str(v.get("id")) not in excluded_ids
                ]
            if filtered_vehicles:
                sorted_vehicles = self.sort_vehicles(
                    filtered_vehicles,
                    current_valormax,
                    current_anomax,
                    current_kmmax,
                    current_ccmax,
                )
                return SearchResult(
                    vehicles=sorted_vehicles[:6],
                    total_found=len(sorted_vehicles),
                    fallback_info={"fallback": {"removed_filters": removed_filters}},
                    removed_filters=removed_filters,
                )

        return SearchResult(
            vehicles=[],
            total_found=0,
            fallback_info={},
            removed_filters=removed_filters,
        )


search_engine = VehicleSearchEngine()

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _format_vehicle(vehicle: Dict) -> str:
    tipo = vehicle.get("tipo", "").lower()

    def safe_value(value):
        if value is None or value == "":
            return ""
        return str(value)

    opcionais_str = vehicle.get("opcionais", "")
    codigos_opcionais = opcionais_para_codigos(opcionais_str)
    codigos_formatados = (
        f"[{','.join(map(str, codigos_opcionais))}]" if codigos_opcionais else "[]"
    )

    if "moto" in tipo:
        return ",".join(
            [
                safe_value(vehicle.get("id")),
                safe_value(vehicle.get("tipo")),
                safe_value(vehicle.get("marca")),
                safe_value(vehicle.get("modelo")),
                safe_value(vehicle.get("versao")),
                safe_value(vehicle.get("cor")),
                safe_value(vehicle.get("ano")),
                safe_value(vehicle.get("km")),
                safe_value(vehicle.get("combustivel")),
                safe_value(vehicle.get("cilindrada")),
                safe_value(vehicle.get("preco")),
            ]
        )
    else:
        return ",".join(
            [
                safe_value(vehicle.get("id")),
                safe_value(vehicle.get("tipo")),
                safe_value(vehicle.get("marca")),
                safe_value(vehicle.get("modelo")),
                safe_value(vehicle.get("versao")),
                safe_value(vehicle.get("cor")),
                safe_value(vehicle.get("ano")),
                safe_value(vehicle.get("km")),
                safe_value(vehicle.get("combustivel")),
                safe_value(vehicle.get("cambio")),
                safe_value(vehicle.get("motor")),
                safe_value(vehicle.get("portas")),
                safe_value(vehicle.get("preco")),
                codigos_formatados,
            ]
        )


def _collect_multi_params(qp: Any) -> Dict[str, str]:
    out: Dict[str, List[str]] = {}
    keys = set(qp.keys()) if hasattr(qp, "keys") else set(dict(qp).keys())
    for key in keys:
        vals = qp.getlist(key) if hasattr(qp, "getlist") else [qp.get(key)]
        acc: List[str] = []
        for v in vals:
            if v is None:
                continue
            parts = [p.strip() for p in str(v).split(",") if p.strip()]
            acc.extend(parts)
        if acc:
            out[key] = ",".join(acc)
    return out


# ─── Parser Transformers ──────────────────────────────────────────────────────
# Adicione aqui transformações específicas por parser.
# Se não existir transformador para o parser, a saída padrão é usada.


def _transform_revendai(vehicle: dict) -> dict:
    """Transformação específica para RevendaiParser — inclui campos extras do Revendai."""
    return {
        **vehicle,
        "valor_troca": vehicle.get("valor_troca"),
        "repasse": vehicle.get("repasse"),
    }


def _transform_revendai_locadora(vehicle: dict) -> dict:
    """Transformação específica para RevendaiLocadoraParser — inclui campos de planos de locadora."""
    return {
        **vehicle,
        "plano_start": vehicle.get("plano_start"),
        "plano_drive": vehicle.get("plano_drive"),
        "plano_km_livre": vehicle.get("plano_km_livre"),
    }


def _transform_revendamais(vehicle: dict) -> dict:
    """Transformação específica para RevendamaisParser — inclui campo blindado."""
    return {
        **vehicle,
        "blindado": vehicle.get("blindado"),
    }


def _transform_covel(vehicle: dict) -> dict:
    """Transformação específica para CovelParser — retorna apenas os campos do Covel."""
    fotos = vehicle.get("fotos") or []
    foto = fotos[0] if fotos else None
    return {
        "id": vehicle.get("id"),
        "marca": vehicle.get("marca"),
        "modelo": vehicle.get("modelo"),
        "descricao": vehicle.get("observacao"),
        "preco": vehicle.get("preco"),
        "foto": foto,
    }


def _transform_ecosys(vehicle: dict) -> dict:
    """Transformação específica para EcosysParser — retorna apenas os campos do Ecosys."""
    return {
        "id": vehicle.get("id"),
        "modelo": vehicle.get("modelo"),
        "descricao": vehicle.get("observacao"),
        "preco": vehicle.get("preco"),
        "fotos": vehicle.get("fotos", []),
    }


PARSER_TRANSFORMERS: Dict[str, Any] = {
    "RevendaiParser": _transform_revendai,
    "RevendaiLocadoraParser": _transform_revendai_locadora,
    "RevendamaisParser": _transform_revendamais,
    "CovelParser": _transform_covel,
    "EcosysParser": _transform_ecosys,
}


# Formatadores customizados para o endpoint /list por parser
# Recebe um vehicle (já transformado) e retorna string formatada
def _format_vehicle_covel(vehicle: dict) -> str:
    """Formata veículo Covel para o /list: id, marca, modelo, preco"""

    def sv(v):
        return "" if v is None else str(v)

    return ",".join(
        [
            sv(vehicle.get("id")),
            sv(vehicle.get("marca")),
            sv(vehicle.get("modelo")),
            sv(vehicle.get("preco")),
        ]
    )


def _format_vehicle_ecosys(vehicle: dict) -> str:
    """Formata veículo Ecosys para o /list: id, modelo, preco"""

    def sv(v):
        return "" if v is None else str(v)

    return ",".join(
        [
            sv(vehicle.get("id")),
            sv(vehicle.get("modelo")),
            sv(vehicle.get("preco")),
        ]
    )


def _format_vehicle_revendamais(vehicle: dict) -> str:
    """Formata veículo RevendaMais para o /list — igual ao padrão de carros + blindado no final"""
    tipo = (vehicle.get("tipo") or "").lower()

    def sv(v):
        return "" if v is None else str(v)

    opcionais_str = vehicle.get("opcionais", "")
    codigos_opcionais = opcionais_para_codigos(opcionais_str)
    codigos_formatados = (
        f"[{','.join(map(str, codigos_opcionais))}]" if codigos_opcionais else "[]"
    )

    blindado_val = vehicle.get("blindado")
    if blindado_val is True:
        blindado_str = "true"
    elif blindado_val is False:
        blindado_str = "false"
    else:
        blindado_str = ""

    if "moto" in tipo:
        return ",".join(
            [
                sv(vehicle.get("id")),
                sv(vehicle.get("tipo")),
                sv(vehicle.get("marca")),
                sv(vehicle.get("modelo")),
                sv(vehicle.get("versao")),
                sv(vehicle.get("cor")),
                sv(vehicle.get("ano")),
                sv(vehicle.get("km")),
                sv(vehicle.get("combustivel")),
                sv(vehicle.get("cilindrada")),
                sv(vehicle.get("preco")),
                blindado_str,
            ]
        )
    else:
        return ",".join(
            [
                sv(vehicle.get("id")),
                sv(vehicle.get("tipo")),
                sv(vehicle.get("marca")),
                sv(vehicle.get("modelo")),
                sv(vehicle.get("versao")),
                sv(vehicle.get("cor")),
                sv(vehicle.get("ano")),
                sv(vehicle.get("km")),
                sv(vehicle.get("combustivel")),
                sv(vehicle.get("cambio")),
                sv(vehicle.get("motor")),
                sv(vehicle.get("portas")),
                sv(vehicle.get("preco")),
                codigos_formatados,
                blindado_str,
            ]
        )


def _format_vehicle_revendai_locadora(vehicle: dict) -> str:
    """Formata veículo RevendaiLocadora para o /list — padrão de carros com campos de planos no final"""
    tipo = (vehicle.get("tipo") or "").lower()

    def sv(v):
        return "" if v is None else str(v)

    opcionais_str = vehicle.get("opcionais", "")
    codigos_opcionais = opcionais_para_codigos(opcionais_str)
    codigos_formatados = (
        f"[{','.join(map(str, codigos_opcionais))}]" if codigos_opcionais else "[]"
    )

    plano_start = vehicle.get("plano_start")
    plano_drive = vehicle.get("plano_drive")
    plano_km_livre = vehicle.get("plano_km_livre")

    planos_str = ",".join(
        [
            sv(plano_start),
            sv(plano_drive),
            sv(plano_km_livre),
        ]
    )

    if "moto" in tipo:
        return ",".join(
            [
                sv(vehicle.get("id")),
                sv(vehicle.get("tipo")),
                sv(vehicle.get("marca")),
                sv(vehicle.get("modelo")),
                sv(vehicle.get("versao")),
                sv(vehicle.get("cor")),
                sv(vehicle.get("ano")),
                sv(vehicle.get("km")),
                sv(vehicle.get("combustivel")),
                sv(vehicle.get("cilindrada")),
                sv(vehicle.get("preco")),
                planos_str,
            ]
        )
    else:
        return ",".join(
            [
                sv(vehicle.get("id")),
                sv(vehicle.get("tipo")),
                sv(vehicle.get("marca")),
                sv(vehicle.get("modelo")),
                sv(vehicle.get("versao")),
                sv(vehicle.get("cor")),
                sv(vehicle.get("ano")),
                sv(vehicle.get("km")),
                sv(vehicle.get("combustivel")),
                sv(vehicle.get("cambio")),
                sv(vehicle.get("motor")),
                sv(vehicle.get("portas")),
                sv(vehicle.get("preco")),
                codigos_formatados,
                planos_str,
            ]
        )


def _format_vehicle_revendai(vehicle: dict) -> str:
    """Formata veículo Revendai para o /list — formato padrão (repasse já separado em ESTOQUE/REPASSE)"""
    tipo = (vehicle.get("tipo") or "").lower()

    def sv(v):
        return "" if v is None else str(v)

    opcionais_str = vehicle.get("opcionais", "")
    codigos_opcionais = opcionais_para_codigos(opcionais_str)
    codigos_formatados = (
        f"[{','.join(map(str, codigos_opcionais))}]" if codigos_opcionais else "[]"
    )

    if "moto" in tipo:
        return ",".join(
            [
                sv(vehicle.get("id")),
                sv(vehicle.get("tipo")),
                sv(vehicle.get("marca")),
                sv(vehicle.get("modelo")),
                sv(vehicle.get("versao")),
                sv(vehicle.get("cor")),
                sv(vehicle.get("ano")),
                sv(vehicle.get("km")),
                sv(vehicle.get("combustivel")),
                sv(vehicle.get("cilindrada")),
                sv(vehicle.get("preco")),
            ]
        )
    else:
        return ",".join(
            [
                sv(vehicle.get("id")),
                sv(vehicle.get("tipo")),
                sv(vehicle.get("marca")),
                sv(vehicle.get("modelo")),
                sv(vehicle.get("versao")),
                sv(vehicle.get("cor")),
                sv(vehicle.get("ano")),
                sv(vehicle.get("km")),
                sv(vehicle.get("combustivel")),
                sv(vehicle.get("cambio")),
                sv(vehicle.get("motor")),
                sv(vehicle.get("portas")),
                sv(vehicle.get("preco")),
                codigos_formatados,
            ]
        )


PARSER_LIST_FORMATTERS: Dict[str, Any] = {
    "CovelParser": _format_vehicle_covel,
    "EcosysParser": _format_vehicle_ecosys,
    "RevendamaisParser": _format_vehicle_revendamais,
    "RevendaiLocadoraParser": _format_vehicle_revendai_locadora,
    "RevendaiParser": _format_vehicle_revendai,
    "FordPlusParser": _format_vehicle_revendai,
}

# Instruções customizadas para o endpoint /list por parser
PARSER_LIST_INSTRUCTIONS: Dict[str, str] = {
    "RevendaiParser": (
        "### COMO LER O JSON de 'BuscaEstoque' — Revendai (CRUCIAL — leia cada linha com atenção)\n"
        "- Para motocicletas (se o segundo valor no JSON for 'moto'):\n"
        "Código ID, tipo (moto), marca, modelo, versão, cor, ano, quilometragem, combustível, cilindrada, preço\n"
        "- Para carros (se o segundo valor no JSON for 'carro'):\n"
        "Código ID, tipo (carro), marca, modelo, versão, cor, ano, quilometragem, combustível, câmbio, motor, portas, preço, [opcionais]\n\n"
        "- Para os opcionais dos carros, alguns números podem aparecer. Aqui está o significado de cada número:\n"
        "1 - ar-condicionado\n2 - airbag\n3 - vidros elétricos\n4 - freios ABS\n5 - direção hidráulica\n6 - direção elétrica\n7 - sete lugares\n"
        "- IMPORTANTE: Os veículos estão separados em dois grupos principais: 'ESTOQUE' (veículos próprios) e 'REPASSE' (veículos de repasse). "
        "Dentro de cada grupo, os veículos estão organizados por categoria (Hatch, Sedan, Suv, etc).\n"
    ),
    "CovelParser": (
        "### COMO LER O JSON de 'BuscaEstoque' — Covel (motos elétricas)\n"
        "Cada item contém os seguintes campos:\n"
        "id, marca, modelo, preco\n"
        "- id: identificador único do produto\n"
        "- marca: fabricante da moto elétrica\n"
        "- modelo: nome completo do modelo\n"
        "- preco: preço de venda em reais\n"
    ),
    "EcosysParser": (
        "### COMO LER O JSON de 'BuscaEstoque' — EcosysAuto\n"
        "Cada item contém os seguintes campos:\n"
        "id, modelo, preco\n"
        "- id: identificador único do veículo\n"
        "- modelo: nome do modelo do veículo\n"
        "- preco: preço de venda em reais\n"
    ),
    "RevendamaisParser": (
        "### COMO LER O JSON de 'BuscaEstoque' (CRUCIAL — leia cada linha com atenção)\n"
        "- Para motocicletas (se o segundo valor no JSON for 'moto'):\n"
        "Código ID, tipo (moto), marca, modelo, versão, cor, ano, quilometragem, combustível, cilindrada, preço, blindado\n"
        "- Para carros (se o segundo valor no JSON for 'carro'):\n"
        "Código ID, tipo (carro), marca, modelo, versão, cor, ano, quilometragem, combustível, câmbio, motor, portas, preço, [opcionais], blindado\n\n"
        "- Para os opcionais dos carros, alguns números podem aparecer. Aqui está o significado de cada número:\n"
        "1 - ar-condicionado\n2 - airbag\n3 - vidros elétricos\n4 - freios ABS\n5 - direção hidráulica\n6 - direção elétrica\n7 - sete lugares\n"
        "- blindado: 'true' se o veículo é blindado, 'false' se não é, vazio se não informado\n"
    ),
    "RevendaiLocadoraParser": (
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
    ),
    "FordPlusParser": (
        "### COMO LER O JSON de 'BuscaEstoque' — FordPlus (CRUCIAL — leia cada linha com atenção)\n"
        "- Para carros (se o segundo valor no JSON for 'carro'):\n"
        "Código ID, tipo (carro), marca, modelo, versão, cor, ano, quilometragem, combustível, câmbio, motor, portas, preço, [opcionais]\n\n"
        "- Para os opcionais dos carros, alguns números podem aparecer. Aqui está o significado de cada número:\n"
        "1 - ar-condicionado\n2 - airbag\n3 - vidros elétricos\n4 - freios ABS\n5 - direção hidráulica\n6 - direção elétrica\n7 - sete lugares\n"
        "- IMPORTANTE: Veículos novos (km vazio) com a mesma versão são agrupados como um único veículo. "
        "O campo 'cor' pode conter múltiplas cores separadas por vírgula (ex: 'Branco, Preto, Prata'). "
        "As fotos são o conjunto de todos os veículos agrupados.\n"
    ),
}


def _apply_parser_transform(vehicles: List[Dict], parser_name: str) -> List[Dict]:
    """Aplica transformação específica do parser se existir, senão retorna como está."""
    transformer = PARSER_TRANSFORMERS.get(parser_name or "")
    if not transformer:
        return vehicles
    return [transformer(v) for v in vehicles]


def _get_client_vehicles(slug: str):
    """Load vehicles for a client slug, apply parser transform, or raise 404."""
    client = client_manager.get_client_by_slug(slug)
    if not client:
        raise HTTPException(status_code=404, detail=f"Cliente '{slug}' não encontrado")
    data = client_manager.load_client_vehicles(slug)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail="Dados ainda não disponíveis. Aguarde o primeiro deploy.",
        )
    vehicles = data.get("veiculos", [])
    if not isinstance(vehicles, list):
        raise HTTPException(status_code=500, detail="Formato de dados inválido")
    # Aplica transformação específica do parser (ou retorna padrão se não existir)
    parser_name = getattr(client, "parser_used", None) or ""
    return _apply_parser_transform(vehicles, parser_name)


# ─── Public API routes ────────────────────────────────────────────────────────


@app.get("/{slug}/api/health")
def client_health(slug: str):
    client = client_manager.get_client_by_slug(slug)
    if not client:
        raise HTTPException(status_code=404, detail=f"Cliente '{slug}' não encontrado")
    return {
        "status": "healthy",
        "client": slug,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/{slug}/api/status")
def client_status(slug: str):
    client = client_manager.get_client_by_slug(slug)
    if not client:
        raise HTTPException(status_code=404, detail=f"Cliente '{slug}' não encontrado")
    return {
        "client": slug,
        "status": client.status,
        "parser_used": client.parser_used,
        "last_updated_at": client.last_updated_at,
        "vehicle_count": client.vehicle_count,
        "last_error": client.last_error,
    }


@app.get("/{slug}/list")
def client_list_vehicles(slug: str, request: Request):
    vehicles = _get_client_vehicles(slug)

    # Obtém o parser_used para customizar a instrução
    _client = client_manager.get_client_by_slug(slug)
    parser_name = getattr(_client, "parser_used", None) or ""

    query_params = dict(request.query_params)
    filter_categoria = query_params.get("categoria")
    filter_tipo = query_params.get("tipo")

    filtered_vehicles = vehicles
    if filter_categoria:
        filtered_vehicles = [
            v
            for v in filtered_vehicles
            if v.get("categoria")
            and filter_categoria.lower() in v.get("categoria", "").lower()
        ]
    if filter_tipo:
        filtered_vehicles = [
            v
            for v in filtered_vehicles
            if v.get("tipo") and filter_tipo.lower() in v.get("tipo", "").lower()
        ]

    has_localizacao = any(
        v.get("localizacao") and v.get("localizacao") not in ["", "None", None]
        for v in filtered_vehicles
    )

    # Usa instrução customizada do parser se existir, senão usa o padrão
    instruction_text = PARSER_LIST_INSTRUCTIONS.get(
        parser_name,
        (
            "### COMO LER O JSON de 'BuscaEstoque' (CRUCIAL — leia cada linha com atenção)\n"
            "- Para motocicletas (se o segundo valor no JSON for 'moto'):\n"
            "Código ID, tipo (moto), marca, modelo, versão, cor, ano, quilometragem, combustível, cilindrada, preço\n"
            "- Para carros (se o segundo valor no JSON for 'carro'):\n"
            "Código ID, tipo (carro), marca, modelo, versão, cor, ano, quilometragem, combustível, câmbio, motor, portas, preço, [opcionais]\n\n"
            "- Para os opcionais dos carros, alguns números podem aparecer. Aqui está o significado de cada número:\n"
            "1 - ar-condicionado\n2 - airbag\n3 - vidros elétricos\n4 - freios ABS\n5 - direção hidráulica\n6 - direção elétrica\n7 - sete lugares\n"
        ),
    )

    # Usa formatador customizado do parser se existir, senão usa o padrão
    _list_formatter = PARSER_LIST_FORMATTERS.get(parser_name, _format_vehicle)

    result = {"instruction": instruction_text}

    if has_localizacao:
        localizacoes_dict = {}
        for vehicle in filtered_vehicles:
            localizacao = vehicle.get("localizacao")
            if not localizacao or localizacao in ["", "None", None]:
                localizacao = "SEM LOCALIZAÇÃO"
            if localizacao not in localizacoes_dict:
                localizacoes_dict[localizacao] = {"categorias": {}, "nao_mapeados": []}
            categoria = vehicle.get("categoria")
            formatted_vehicle = _list_formatter(vehicle)
            if not categoria or categoria in ["", "None", None]:
                localizacoes_dict[localizacao]["nao_mapeados"].append(formatted_vehicle)
            else:
                # Normaliza categoria para Title Case para evitar duplicatas
                categoria_key = categoria.strip().title()
                if categoria_key not in localizacoes_dict[localizacao]["categorias"]:
                    localizacoes_dict[localizacao]["categorias"][categoria_key] = []
                localizacoes_dict[localizacao]["categorias"][categoria_key].append(
                    formatted_vehicle
                )
        for localizacao in sorted(localizacoes_dict.keys()):
            loc_data = localizacoes_dict[localizacao]
            result[localizacao] = {}
            for categoria in sorted(loc_data["categorias"].keys()):
                result[localizacao][categoria] = loc_data["categorias"][categoria]
            if loc_data["nao_mapeados"]:
                result[localizacao]["NÃO MAPEADOS"] = loc_data["nao_mapeados"]
    else:
        # Verifica se o parser suporta repasse (apenas RevendaiParser)
        has_repasse = parser_name == "RevendaiParser"

        if has_repasse:
            # Separa veículos por repasse
            veiculos_normais = []
            veiculos_repasse = []
            for vehicle in filtered_vehicles:
                if vehicle.get("repasse") is True:
                    veiculos_repasse.append(vehicle)
                else:
                    veiculos_normais.append(vehicle)

            # Grupo ESTOQUE — categorias normais
            estoque_categorias = {}
            estoque_nao_mapeados = []
            for vehicle in veiculos_normais:
                categoria = vehicle.get("categoria")
                if not categoria or categoria in ["", "None", None]:
                    estoque_nao_mapeados.append(_list_formatter(vehicle))
                    continue
                categoria_key = categoria.strip().title()
                if categoria_key not in estoque_categorias:
                    estoque_categorias[categoria_key] = []
                estoque_categorias[categoria_key].append(_list_formatter(vehicle))
            result["ESTOQUE"] = {}
            for categoria in sorted(estoque_categorias.keys()):
                result["ESTOQUE"][categoria] = estoque_categorias[categoria]
            if estoque_nao_mapeados:
                result["ESTOQUE"]["NÃO MAPEADOS"] = estoque_nao_mapeados

            # Grupo REPASSE — subcategorias dentro de repasse
            if veiculos_repasse:
                repasse_categorias = {}
                repasse_nao_mapeados = []
                for vehicle in veiculos_repasse:
                    categoria = vehicle.get("categoria")
                    if not categoria or categoria in ["", "None", None]:
                        repasse_nao_mapeados.append(_list_formatter(vehicle))
                        continue
                    categoria_key = categoria.strip().title()
                    if categoria_key not in repasse_categorias:
                        repasse_categorias[categoria_key] = []
                    repasse_categorias[categoria_key].append(_list_formatter(vehicle))
                result["REPASSE"] = {}
                for categoria in sorted(repasse_categorias.keys()):
                    result["REPASSE"][categoria] = repasse_categorias[categoria]
                if repasse_nao_mapeados:
                    result["REPASSE"]["NÃO MAPEADOS"] = repasse_nao_mapeados
        else:
            # Comportamento padrão (sem separação por repasse)
            categorized_vehicles = {}
            nao_mapeados = []
            for vehicle in filtered_vehicles:
                categoria = vehicle.get("categoria")
                if not categoria or categoria in ["", "None", None]:
                    nao_mapeados.append(_list_formatter(vehicle))
                    continue
                # Normaliza categoria para Title Case para evitar duplicatas (ex: "hatch" e "Hatch")
                categoria_key = categoria.strip().title()
                if categoria_key not in categorized_vehicles:
                    categorized_vehicles[categoria_key] = []
                categorized_vehicles[categoria_key].append(_list_formatter(vehicle))
            for categoria in sorted(categorized_vehicles.keys()):
                result[categoria] = categorized_vehicles[categoria]
            if nao_mapeados:
                result["NÃO MAPEADOS"] = nao_mapeados

    return JSONResponse(content=result)


@app.get("/{slug}/api/data")
def client_get_data(slug: str, request: Request):
    vehicles = _get_client_vehicles(slug)

    query_params = _collect_multi_params(request.query_params)

    valormax = search_engine.get_max_value_from_range_param(
        query_params.pop("ValorMax", None)
    )
    anomax = search_engine.get_max_value_from_range_param(
        query_params.pop("AnoMax", None)
    )
    kmmax = search_engine.get_max_value_from_range_param(
        query_params.pop("KmMax", None)
    )
    ccmax = search_engine.get_max_value_from_range_param(
        query_params.pop("CcMax", None)
    )
    simples = query_params.pop("simples", None)
    excluir_raw = query_params.pop("excluir", None)
    id_csv = query_params.pop("id", None)
    id_set = set(search_engine.split_multi_value(id_csv)) if id_csv else set()

    filters = {
        "tipo": query_params.get("tipo"),
        "modelo": query_params.get("modelo"),
        "categoria": query_params.get("categoria"),
        "cambio": query_params.get("cambio"),
        "opcionais": query_params.get("opcionais"),
        "observacao": query_params.get("observacao"),
        "marca": query_params.get("marca"),
        "cor": query_params.get("cor"),
        "combustivel": query_params.get("combustivel"),
        "motor": query_params.get("motor"),
        "portas": query_params.get("portas"),
        "localizacao": query_params.get("localizacao"),
    }
    filters = {k: v for k, v in filters.items() if v}

    excluded_ids = (
        set(search_engine.split_multi_value(excluir_raw)) if excluir_raw else set()
    )

    def _trim_fotos(vehicle_list):
        if simples == "1":
            for vehicle in vehicle_list:
                fotos = vehicle.get("fotos")
                if isinstance(fotos, list) and len(fotos) > 0:
                    if isinstance(fotos[0], str):
                        vehicle["fotos"] = [fotos[0]]
                    elif isinstance(fotos[0], list) and len(fotos[0]) > 0:
                        vehicle["fotos"] = [[fotos[0][0]]]
                    else:
                        vehicle["fotos"] = []
                else:
                    vehicle["fotos"] = []
        return vehicle_list

    if id_set:
        id_set -= excluded_ids
        matched = [v for v in vehicles if str(v.get("id")) in id_set]
        if matched:
            return JSONResponse(
                content={
                    "resultados": _trim_fotos(matched),
                    "total_encontrado": len(matched),
                    "info": f"Veículos encontrados por IDs: {', '.join(sorted(id_set))}",
                }
            )
        else:
            return JSONResponse(
                content={
                    "resultados": [],
                    "total_encontrado": 0,
                    "error": f"Veículo(s) com ID {', '.join(sorted(id_set))} não encontrado(s)",
                }
            )

    has_search_filters = bool(filters) or valormax or anomax or kmmax or ccmax

    if not has_search_filters:
        all_vehicles = (
            [v for v in vehicles if str(v.get("id")) not in excluded_ids]
            if excluded_ids
            else list(vehicles)
        )
        sorted_vehicles = sorted(
            all_vehicles,
            key=lambda v: search_engine.convert_price(v.get("preco")) or 0,
            reverse=True,
        )
        return JSONResponse(
            content={
                "resultados": _trim_fotos(sorted_vehicles),
                "total_encontrado": len(sorted_vehicles),
                "info": "Exibindo todo o estoque disponível",
            }
        )

    result = search_engine.search_with_fallback(
        vehicles, filters, valormax, anomax, kmmax, ccmax, excluded_ids
    )
    _trim_fotos(result.vehicles)

    response_data = {
        "resultados": result.vehicles,
        "total_encontrado": result.total_found,
    }
    if result.fallback_info:
        response_data.update(result.fallback_info)
    if result.total_found == 0:
        response_data["instrucao_ia"] = (
            "Não encontramos veículos com os parâmetros informados e também não encontramos opções próximas."
        )
    return JSONResponse(content=response_data)


@app.get("/{slug}/api/lookup")
def client_lookup_model(slug: str, request: Request):
    # Validate client exists
    client = client_manager.get_client_by_slug(slug)
    if not client:
        raise HTTPException(status_code=404, detail=f"Cliente '{slug}' não encontrado")

    query_params = dict(request.query_params)
    modelo = query_params.get("modelo", "").strip()
    tipo = query_params.get("tipo", "").strip().lower()

    if not modelo:
        return JSONResponse(
            content={"error": "Parâmetro 'modelo' é obrigatório"}, status_code=400
        )
    if not tipo:
        return JSONResponse(
            content={"error": "Parâmetro 'tipo' é obrigatório"}, status_code=400
        )
    if tipo not in ["carro", "moto"]:
        return JSONResponse(
            content={"error": "Parâmetro 'tipo' deve ser 'carro' ou 'moto'"},
            status_code=400,
        )

    normalized_model = search_engine.normalize_text(modelo)

    if tipo == "moto":
        if normalized_model in MAPEAMENTO_MOTOS:
            cilindrada, categoria = MAPEAMENTO_MOTOS[normalized_model]
            return JSONResponse(
                content={
                    "modelo": modelo,
                    "tipo": tipo,
                    "cilindrada": cilindrada,
                    "categoria": categoria,
                    "match_type": "exact",
                }
            )
        model_words = normalized_model.split()
        for word in model_words:
            if len(word) >= 3 and word in MAPEAMENTO_MOTOS:
                cilindrada, categoria = MAPEAMENTO_MOTOS[word]
                return JSONResponse(
                    content={
                        "modelo": modelo,
                        "tipo": tipo,
                        "cilindrada": cilindrada,
                        "categoria": categoria,
                        "match_type": "partial_word",
                    }
                )
        for key, (cilindrada, categoria) in MAPEAMENTO_MOTOS.items():
            if key in normalized_model or normalized_model in key:
                return JSONResponse(
                    content={
                        "modelo": modelo,
                        "tipo": tipo,
                        "cilindrada": cilindrada,
                        "categoria": categoria,
                        "match_type": "substring",
                    }
                )
        return JSONResponse(
            content={
                "modelo": modelo,
                "tipo": tipo,
                "cilindrada": None,
                "categoria": None,
                "message": "Modelo de moto não encontrado",
            }
        )
    else:
        if normalized_model in MAPEAMENTO_CATEGORIAS:
            categoria = MAPEAMENTO_CATEGORIAS[normalized_model]
            return JSONResponse(
                content={
                    "modelo": modelo,
                    "tipo": tipo,
                    "categoria": categoria,
                    "match_type": "exact",
                }
            )
        model_words = normalized_model.split()
        for word in model_words:
            if len(word) >= 3 and word in MAPEAMENTO_CATEGORIAS:
                categoria = MAPEAMENTO_CATEGORIAS[word]
                return JSONResponse(
                    content={
                        "modelo": modelo,
                        "tipo": tipo,
                        "categoria": categoria,
                        "match_type": "partial_word",
                    }
                )
        for key, categoria in MAPEAMENTO_CATEGORIAS.items():
            if key in normalized_model or normalized_model in key:
                return JSONResponse(
                    content={
                        "modelo": modelo,
                        "tipo": tipo,
                        "categoria": categoria,
                        "match_type": "substring",
                    }
                )
        return JSONResponse(
            content={
                "modelo": modelo,
                "tipo": tipo,
                "categoria": None,
                "message": "Modelo de carro não encontrado",
            }
        )


# ─── FordPlus individual endpoint ────────────────────────────────────────────


@app.get("/fordplus/{slug}/veiculos")
def fordplus_veiculos(slug: str, request: Request):
    """Endpoint individual para FordPlusParser com saída customizada."""
    client = client_manager.get_client_by_slug(slug)
    if not client:
        raise HTTPException(status_code=404, detail=f"Cliente '{slug}' não encontrado")

    data = client_manager.load_client_vehicles(slug)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail="Dados ainda não disponíveis. Aguarde o primeiro deploy.",
        )

    vehicles = data.get("veiculos", [])
    if not isinstance(vehicles, list):
        raise HTTPException(status_code=500, detail="Formato de dados inválido")

    parser_name = getattr(client, "parser_used", None) or ""
    if parser_name != "FordPlusParser":
        raise HTTPException(
            status_code=400,
            detail=f"Este endpoint é exclusivo para FordPlusParser. Parser atual: {parser_name}",
        )

    query_params = dict(request.query_params)
    filter_categoria = query_params.get("categoria")
    filter_marca = query_params.get("marca")

    filtered = vehicles
    if filter_categoria:
        filtered = [
            v
            for v in filtered
            if v.get("categoria")
            and filter_categoria.lower() in v.get("categoria", "").lower()
        ]
    if filter_marca:
        filtered = [
            v
            for v in filtered
            if v.get("marca") and filter_marca.lower() in v.get("marca", "").lower()
        ]

    return JSONResponse(
        content={
            "veiculos": filtered,
            "total": len(filtered),
        }
    )


# ─── Global health ────────────────────────────────────────────────────────────


@app.get("/health")
def global_health():
    return {
        "status": "healthy",
        "clients_count": len(client_manager.list_clients()),
        "timestamp": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=3000)
