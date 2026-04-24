"""
route_dashboard.py — Rotas HTML: login, logout e dashboard de administração.
"""

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from auth import authenticate_user, create_access_token, require_auth, COOKIE_NAME
from core import client_manager, templates, BASE_URL

router = APIRouter()


# ─── Auth ─────────────────────────────────────────────────────────────────────


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="login.html", context={"error": None}
    )


@router.post("/login")
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
        max_age=86400,
        samesite="lax",
    )
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


# ─── Dashboard ────────────────────────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse)
def root_redirect():
    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, _auth=Depends(require_auth)):
    clients = client_manager.list_clients()
    clients_data = []
    for c in clients:
        status = c.status
        if c.status == "running" and c.vehicle_count == 0:
            status = "error"

        cat_stats = client_manager.get_categorization_stats(c.slug)

        clients_data.append(
            {
                **c.to_dict(),
                "status": status,
                "base_url": f"{BASE_URL}/{c.slug}",
                "categorization_stats": cat_stats,
            }
        )

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
