"""
route_public.py — Endpoints públicos de consulta de estoque por cliente.
"""

from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from core import client_manager, search_engine
from fetchers import get_parser_by_name
from vehicle_mappings import MAPEAMENTO_CATEGORIAS, MAPEAMENTO_MOTOS

router = APIRouter(tags=["public"])


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _collect_multi_params(qp: Any) -> Dict[str, str]:
    """Consolida parâmetros repetidos e com vírgula em um único valor CSV."""
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


def _get_client_vehicles(slug: str):
    """
    Carrega veículos de um cliente, aplica o transform do parser.
    Retorna (vehicles, parser, client). Lança HTTPException em caso de erro.
    """
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
    parser = get_parser_by_name(parser_name)

    transformed = [parser.transform(v) for v in vehicles]
    return transformed, parser, client


# ─── Health ───────────────────────────────────────────────────────────────────


@router.get("/health")
def global_health():
    return {
        "status": "healthy",
        "clients_count": len(client_manager.list_clients()),
        "timestamp": datetime.now().isoformat(),
    }


# ─── Per-client endpoints ─────────────────────────────────────────────────────


@router.get("/{slug}/api/health")
def client_health(slug: str):
    client = client_manager.get_client_by_slug(slug)
    if not client:
        raise HTTPException(status_code=404, detail=f"Cliente '{slug}' não encontrado")
    return {
        "status": "healthy",
        "client": slug,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/{slug}/api/status")
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


@router.get("/{slug}/list")
def client_list_vehicles(slug: str, request: Request):
    vehicles, parser, _client = _get_client_vehicles(slug)

    query_params = dict(request.query_params)
    filter_categoria = query_params.get("categoria")
    filter_tipo = query_params.get("tipo")

    filtered = vehicles
    if filter_categoria:
        filtered = [
            v for v in filtered
            if v.get("categoria")
            and filter_categoria.lower() in v.get("categoria", "").lower()
        ]
    if filter_tipo:
        filtered = [
            v for v in filtered
            if v.get("tipo") and filter_tipo.lower() in v.get("tipo", "").lower()
        ]

    result = {"instruction": parser.get_instructions()}
    result.update(parser.format_list(filtered))

    return JSONResponse(content=result)


@router.get("/{slug}/api/data")
def client_get_data(slug: str, request: Request):
    vehicles, _parser, _client = _get_client_vehicles(slug)

    query_params = _collect_multi_params(request.query_params)

    valormax = search_engine.get_max_value_from_range_param(query_params.pop("ValorMax", None))
    anomax = search_engine.get_max_value_from_range_param(query_params.pop("AnoMax", None))
    kmmax = search_engine.get_max_value_from_range_param(query_params.pop("KmMax", None))
    ccmax = search_engine.get_max_value_from_range_param(query_params.pop("CcMax", None))
    simples = query_params.pop("simples", None)
    excluir_raw = query_params.pop("excluir", None)
    id_csv = query_params.pop("id", None)
    id_set = set(search_engine.split_multi_value(id_csv)) if id_csv else set()

    filters = {
        k: query_params.get(k)
        for k in [
            "tipo", "modelo", "categoria", "cambio", "opcionais",
            "observacao", "marca", "cor", "combustivel", "motor",
            "portas", "localizacao",
        ]
        if query_params.get(k)
    }

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
            return JSONResponse(content={"resultados": _trim_fotos(matched), "total_encontrado": len(matched), "info": f"Veículos encontrados por IDs: {', '.join(sorted(id_set))}"})
        else:
            return JSONResponse(content={"resultados": [], "total_encontrado": 0, "error": f"Veículo(s) com ID {', '.join(sorted(id_set))} não encontrado(s)"})

    has_search_filters = bool(filters) or valormax or anomax or kmmax or ccmax

    if not has_search_filters:
        all_vehicles = ([v for v in vehicles if str(v.get("id")) not in excluded_ids] if excluded_ids else list(vehicles))
        sorted_vehicles = sorted(all_vehicles, key=lambda v: search_engine.convert_price(v.get("preco")) or 0, reverse=True)
        return JSONResponse(content={"resultados": _trim_fotos(sorted_vehicles), "total_encontrado": len(sorted_vehicles), "info": "Exibindo todo o estoque disponível"})

    result = search_engine.search_with_fallback(vehicles, filters, valormax, anomax, kmmax, ccmax, excluded_ids)
    _trim_fotos(result.vehicles)

    response_data = {"resultados": result.vehicles, "total_encontrado": result.total_found}
    if result.fallback_info:
        response_data.update(result.fallback_info)
    if result.total_found == 0:
        response_data["instrucao_ia"] = "Não encontramos veículos com os parâmetros informados e também não encontramos opções próximas."
    return JSONResponse(content=response_data)


@router.get("/{slug}/api/lookup")
def client_lookup_model(slug: str, request: Request):
    client = client_manager.get_client_by_slug(slug)
    if not client:
        raise HTTPException(status_code=404, detail=f"Cliente '{slug}' não encontrado")

    query_params = dict(request.query_params)
    modelo = query_params.get("modelo", "").strip()
    tipo = query_params.get("tipo", "").strip().lower()

    if not modelo:
        return JSONResponse(content={"error": "Parâmetro 'modelo' é obrigatório"}, status_code=400)
    if not tipo:
        return JSONResponse(content={"error": "Parâmetro 'tipo' é obrigatório"}, status_code=400)
    if tipo not in ["carro", "moto"]:
        return JSONResponse(content={"error": "Parâmetro 'tipo' deve ser 'carro' ou 'moto'"}, status_code=400)

    normalized_model = search_engine.normalize_text(modelo)

    if tipo == "moto":
        if normalized_model in MAPEAMENTO_MOTOS:
            cilindrada, categoria = MAPEAMENTO_MOTOS[normalized_model]
            return JSONResponse(content={"modelo": modelo, "tipo": tipo, "cilindrada": cilindrada, "categoria": categoria, "match_type": "exact"})
        for word in normalized_model.split():
            if len(word) >= 3 and word in MAPEAMENTO_MOTOS:
                cilindrada, categoria = MAPEAMENTO_MOTOS[word]
                return JSONResponse(content={"modelo": modelo, "tipo": tipo, "cilindrada": cilindrada, "categoria": categoria, "match_type": "partial_word"})
        for key, (cilindrada, categoria) in MAPEAMENTO_MOTOS.items():
            if key in normalized_model or normalized_model in key:
                return JSONResponse(content={"modelo": modelo, "tipo": tipo, "cilindrada": cilindrada, "categoria": categoria, "match_type": "substring"})
        return JSONResponse(content={"modelo": modelo, "tipo": tipo, "cilindrada": None, "categoria": None, "message": "Modelo de moto não encontrado"})
    else:
        if normalized_model in MAPEAMENTO_CATEGORIAS:
            return JSONResponse(content={"modelo": modelo, "tipo": tipo, "categoria": MAPEAMENTO_CATEGORIAS[normalized_model], "match_type": "exact"})
        for word in normalized_model.split():
            if len(word) >= 3 and word in MAPEAMENTO_CATEGORIAS:
                return JSONResponse(content={"modelo": modelo, "tipo": tipo, "categoria": MAPEAMENTO_CATEGORIAS[word], "match_type": "partial_word"})
        for key, categoria in MAPEAMENTO_CATEGORIAS.items():
            if key in normalized_model or normalized_model in key:
                return JSONResponse(content={"modelo": modelo, "tipo": tipo, "categoria": categoria, "match_type": "substring"})
        return JSONResponse(content={"modelo": modelo, "tipo": tipo, "categoria": None, "message": "Modelo de carro não encontrado"})


# ─── FordPlus endpoint específico ─────────────────────────────────────────────


@router.get("/fordplus/{slug}/veiculos")
def fordplus_veiculos(slug: str, request: Request):
    """Endpoint individual para FordPlusParser com saída JSON completa."""
    client = client_manager.get_client_by_slug(slug)
    if not client:
        raise HTTPException(status_code=404, detail=f"Cliente '{slug}' não encontrado")

    data = client_manager.load_client_vehicles(slug)
    if data is None:
        raise HTTPException(status_code=404, detail="Dados ainda não disponíveis. Aguarde o primeiro deploy.")

    vehicles = data.get("veiculos", [])
    if not isinstance(vehicles, list):
        raise HTTPException(status_code=500, detail="Formato de dados inválido")

    parser_name = getattr(client, "parser_used", None) or ""
    if parser_name != "FordPlusParser":
        raise HTTPException(status_code=400, detail=f"Este endpoint é exclusivo para FordPlusParser. Parser atual: {parser_name}")

    query_params = dict(request.query_params)
    filter_categoria = query_params.get("categoria")
    filter_marca = query_params.get("marca")

    filtered = vehicles
    if filter_categoria:
        filtered = [v for v in filtered if v.get("categoria") and filter_categoria.lower() in v.get("categoria", "").lower()]
    if filter_marca:
        filtered = [v for v in filtered if v.get("marca") and filter_marca.lower() in v.get("marca", "").lower()]

    return JSONResponse(content={"veiculos": filtered, "total": len(filtered)})
