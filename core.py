"""
core.py — Singletons compartilhados por toda a aplicação.
Importado por routes/, main.py e qualquer módulo que precise dos serviços centrais.
"""

import os

from fastapi.templating import Jinja2Templates

from client_manager import ClientManager
from scheduler import MultiTenantScheduler
from search_engine import VehicleSearchEngine

# ─── Configuração ─────────────────────────────────────────────────────────────

BASE_URL = os.getenv("BASE_URL", "https://api.revendai.com")

# ─── Singletons ───────────────────────────────────────────────────────────────

client_manager = ClientManager()
scheduler = MultiTenantScheduler(client_manager)
search_engine = VehicleSearchEngine()
templates = Jinja2Templates(directory="templates")
