"""
main.py — RevendAI Multi-Tenant API Platform
Inicialização da aplicação FastAPI. Toda a lógica está nos módulos:
  - core.py          → singletons (client_manager, scheduler, search_engine, templates)
  - routes/          → endpoints (dashboard, admin, public)
  - services/        → search engine
  - fetchers/        → parsers
"""

from datetime import datetime

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from core import client_manager, scheduler
from route_dashboard import router as dashboard_router
from route_admin import router as admin_router
from route_public import router as public_router

# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(title="RevendAI Panel", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ─── Routers ──────────────────────────────────────────────────────────────────

app.include_router(dashboard_router)
app.include_router(admin_router)
app.include_router(public_router)

# ─── Lifecycle ────────────────────────────────────────────────────────────────


@app.on_event("startup")
def on_startup():
    print("=" * 80)
    print(f"[APP] STARTUP em {datetime.now()}")
    print("=" * 80)
    scheduler.start()
    print("[APP] RevendAI Multi-Tenant Platform iniciado")
    print("=" * 80)


@app.on_event("shutdown")
def on_shutdown():
    print(f"[APP] SHUTDOWN em {datetime.now()}")
    scheduler.shutdown()
    print("[APP] Scheduler desligado")


# ─── Dev entrypoint ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=3000, reload=True)
