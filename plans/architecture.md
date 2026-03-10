# RevendAI Multi-Tenant API Platform — Architecture Plan

## Overview

A new standalone FastAPI application that hosts **all client vehicle-stock APIs** in a single Docker container, with an admin panel for managing them. The existing `apiv4` continues running for legacy clients.

---

## System Architecture

```mermaid
graph TD
    Admin[Admin Browser] -->|HTTPS| Panel[Admin Panel - /login, /dashboard]
    Consumer[API Consumer] -->|HTTPS| PublicAPI[Public API - /{slug}/...]

    Panel --> FastAPI[FastAPI App - main.py]
    PublicAPI --> FastAPI

    FastAPI --> AuthMiddleware[JWT Auth Middleware]
    FastAPI --> ClientManager[ClientManager]
    FastAPI --> Scheduler[APScheduler - per-client 2h jobs]

    ClientManager --> ClientsJSON[data/clients.json - registry]
    ClientManager --> ClientDirs[data/clients/{slug}/ - per-client files]

    ClientDirs --> DataJSON[data.json - parsed vehicles]
    ClientDirs --> StatusJSON[status.json - last update info]

    Scheduler --> XMLFetcher[UnifiedVehicleFetcher - reused from apiv4]
    XMLFetcher --> Parsers[fetchers/ - all 22 parsers]
```

---

## Directory Structure

```
apiv5/
├── main.py                    # FastAPI app entrypoint
├── client_manager.py          # ClientManager class (thread-safe)
├── xml_fetcher.py             # Copied/adapted from apiv4 (+ SSRF validation)
├── vehicle_mappings.py        # Copied from apiv4
├── auth.py                    # JWT auth helpers (fail-fast on missing env vars)
├── scheduler.py               # Multi-tenant APScheduler manager
├── requirements.txt
├── Dockerfile
├── .dockerignore              # Excludes .git, .env, data/, __pycache__, etc.
├── .env.example               # Template for required env vars (commit this)
├── docker-compose.yml         # For local dev (reads from .env file)
├── docker-stack.yml           # For Docker Swarm production (no credential defaults)
├── fetchers/                  # All 22 parsers copied from apiv4
│   ├── __init__.py
│   ├── base_parser.py
│   └── ... (all parsers)
├── templates/                 # Jinja2 HTML templates
│   ├── login.html
│   ├── dashboard.html
│   └── base.html
├── static/                    # CSS, JS, icons
│   ├── style.css
│   └── app.js
└── data/                      # Runtime data (gitignored, mounted as Docker volume)
    ├── clients.json           # Client registry
    └── clients/
        ├── {slug1}/
        │   ├── data.json
        │   └── status.json
        └── {slug2}/
            ├── data.json
            └── status.json
```

---

## Data Models

### `data/clients.json` — Client Registry

```json
[
  {
    "id": "uuid4",
    "name": "Nome do Cliente",
    "slug": "nome-do-cliente",
    "source_url": "https://fonte.com/estoque.xml",
    "parser_used": "AltimusParser",
    "status": "running",
    "created_at": "2026-03-05T00:00:00",
    "last_updated_at": "2026-03-05T02:00:00",
    "last_error": null
  }
]
```

### Status Values

| Value | Color | Meaning |
|-------|-------|---------|
| `pending` | 🟡 Yellow | Created but never deployed yet |
| `error` | 🔴 Red | Last fetch/parse failed |
| `running` | 🟢 Green | Last fetch succeeded |

---

## Authentication

- **Admin credentials** stored in environment variables — **no defaults; app refuses to start if any are missing**:
  - `ADMIN_EMAIL` — admin login e-mail
  - `ADMIN_PASSWORD` — admin login password (use a strong password)
  - `JWT_SECRET` — long random string; generate with `openssl rand -hex 32`
- Login endpoint returns a **JWT token stored in an `httponly` cookie** (`revendai_token`)
  - `httponly=True` prevents JavaScript from reading the cookie, blocking XSS token theft
  - All `/admin/*` HTML routes read the token from the cookie
  - All `/admin/*` JSON API routes also accept `Authorization: Bearer <token>` header
- Token expiry: **4 hours** (reduced from 24h to limit exposure window)

---

## API Routes

### Public Routes (no auth)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/{slug}/list` | Vehicle listing grouped by category (same as apiv4 `/list`) |
| GET | `/{slug}/api/data` | Vehicle search with filters (same as apiv4 `/api/data`) |
| GET | `/{slug}/api/lookup` | Model lookup (same as apiv4 `/api/lookup`) |
| GET | `/{slug}/api/health` | Health check |
| GET | `/{slug}/api/status` | Last update status |

### Admin Panel Routes (HTML, auth via cookie/session)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/login` | Login page |
| POST | `/login` | Process login, set JWT cookie |
| GET | `/dashboard` | Main dashboard (requires auth) |
| GET | `/logout` | Clear session |

### Admin API Routes (JSON, auth via JWT Bearer)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/clients` | List all clients |
| POST | `/admin/clients` | Create new client |
| PUT | `/admin/clients/{id}` | Update client (name + source_url) |
| DELETE | `/admin/clients/{id}` | Delete client |
| POST | `/admin/clients/{id}/redeploy` | Trigger immediate re-fetch |

---

## Frontend UI (Jinja2 + Vanilla JS)

### Login Page (`/login`)
- Clean centered card with email + password fields
- Logo/brand at top
- On success: redirect to `/dashboard`

### Dashboard (`/dashboard`)
- Header with "RevendAI API Panel" + logout button + "Nova API" button (top right)
- Table with columns:
  - **Nome** — client name
  - **Parser** — parser class name detected
  - **Status** — colored badge (🟡 pending / 🔴 error / 🟢 running)
  - **Última Atualização** — formatted in São Paulo timezone
  - **URL Base** — `https://api.revendai.com/{slug}/`
  - **Ações** — 3 buttons: Edit | Delete | Redeploy

### Modals (vanilla JS, no framework)
1. **Create API Modal** — fields: Nome, URL da Fonte de Estoque → POST `/admin/clients`
2. **Edit API Modal** — fields: Nome, URL da Fonte de Estoque + Redeploy button → PUT `/admin/clients/{id}`
3. **Delete Confirmation Modal** — warning text "Esta ação não pode ser desfeita" + Cancel/Confirm buttons → DELETE `/admin/clients/{id}`

---

## ClientManager Class

```python
class ClientManager:
    def list_clients() -> List[ClientConfig]
    def get_client(id: str) -> ClientConfig
    def get_client_by_slug(slug: str) -> ClientConfig
    def create_client(name: str, source_url: str) -> ClientConfig
    def update_client(id: str, name: str, source_url: str) -> ClientConfig
    def delete_client(id: str) -> None
    def get_client_data_path(slug: str) -> Path
    def get_client_status_path(slug: str) -> Path
    def save_registry() -> None
    def load_registry() -> None
```

- Slug is auto-generated from name using `slugify` (e.g. "Minha Loja" → `minha-loja`)
- If slug already exists, appends `-2`, `-3`, etc.
- On delete: removes `data/clients/{slug}/` directory

---

## Scheduler (Multi-Tenant)

```python
class MultiTenantScheduler:
    def __init__(self, client_manager: ClientManager)
    def start() -> None
    def add_client_job(client_id: str) -> None
    def remove_client_job(client_id: str) -> None
    def trigger_now(client_id: str) -> None  # for redeploy
    def _fetch_client(client_id: str) -> None  # actual fetch logic
```

- Uses `APScheduler BackgroundScheduler` with `timezone="America/Sao_Paulo"`
- Each client gets its own job with `id=f"fetch_{client_id}"`, interval 2 hours
- On startup: loads all clients from registry and schedules jobs
- On create: adds new job immediately + triggers first fetch
- On delete: removes job
- On redeploy: triggers job immediately (does not reset 2h interval)
- Fetch logic: calls `UnifiedVehicleFetcher` with the client's `source_url` set as env var, saves result to `data/clients/{slug}/data.json`

---

## Fetch Logic Adaptation

The existing `UnifiedVehicleFetcher` reads URLs from env vars (`XML_URL*`). For multi-tenant, we adapt it to accept a URL directly:

```python
def fetch_for_client(source_url: str, output_path: Path) -> dict:
    fetcher = UnifiedVehicleFetcher()
    # Process single URL directly instead of reading from env
    vehicles = fetcher.process_url(source_url)
    parser_name = fetcher.last_parser_used  # track which parser was selected
    result = {
        "veiculos": vehicles,
        "_updated_at": datetime.now().isoformat(),
        "_total_count": len(vehicles),
        "_parser_used": parser_name
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result
```

---

## Docker Configuration

### `.dockerignore`
A `.dockerignore` file is required to prevent leaking secrets and dev artefacts into the image:
```
.git
.env
.env.*
!.env.example
data/
__pycache__/
*.pyc
venv/
.vscode/
```

### `Dockerfile`
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
RUN mkdir -p /app/data/clients
VOLUME ["/app/data"]
EXPOSE 3000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3000"]
```

### `docker-stack.yml` (Docker Swarm)
```yaml
version: "3.8"
services:
  revendai-panel:
    image: revendai/panel:latest
    ports:
      - "3000:3000"
    environment:
      # REQUIRED — no defaults. Set via Docker secrets or CI/CD pipeline.
      # Generate JWT_SECRET with: openssl rand -hex 32
      - ADMIN_EMAIL
      - ADMIN_PASSWORD
      - JWT_SECRET
      - BASE_URL=${BASE_URL:-https://api.revendai.com}
    volumes:
      - revendai_data:/app/data
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure

volumes:
  revendai_data:
```

### Local development (`docker-compose.yml`)
Copy `.env.example` to `.env`, fill in the values, then run `docker compose up`.
Never commit `.env` to version control.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ADMIN_EMAIL` | **required** | Admin login email |
| `ADMIN_PASSWORD` | **required** | Admin login password |
| `JWT_SECRET` | **required** | Secret for JWT signing — generate with `openssl rand -hex 32` |
| `BASE_URL` | `https://api.revendai.com` | Base URL shown in dashboard |

> **Note:** The application will exit immediately at startup if `ADMIN_EMAIL`, `ADMIN_PASSWORD`, or `JWT_SECRET` are not set. There are no insecure defaults.

---

## Implementation Steps (Execution Order)

1. **Create project skeleton** — directories, `requirements.txt`, `.gitignore`, `.dockerignore`, `.env.example`
2. **Copy & adapt parsers** — copy `fetchers/`, `vehicle_mappings.py`, adapt `xml_fetcher.py` (add SSRF URL validation)
3. **`client_manager.py`** — ClientConfig dataclass + ClientManager class
4. **`auth.py`** — JWT creation/validation helpers
5. **`scheduler.py`** — MultiTenantScheduler class
6. **`main.py`** — FastAPI app wiring all routes together
7. **`templates/base.html`** — shared layout with nav
8. **`templates/login.html`** — login form
9. **`templates/dashboard.html`** — table + modals
10. **`static/style.css`** — clean modern styling
11. **`static/app.js`** — modal logic + API calls
12. **`Dockerfile`** + **`docker-stack.yml`**

---

## Key Design Decisions

- **No database** — `clients.json` as registry, per-client `data.json` for vehicle data
- **No build step** — Jinja2 templates + vanilla JS, served by FastAPI
- **JWT in `httponly` cookie** — `httponly=True` prevents XSS token theft; dashboard auth reads cookie, API routes also accept Bearer header
- **No credential defaults** — `ADMIN_EMAIL`, `ADMIN_PASSWORD`, and `JWT_SECRET` are required env vars; app exits at startup if any are missing
- **SSRF protection** — `validate_source_url()` in `xml_fetcher.py` blocks private/loopback/link-local IP ranges before any HTTP request is made
- **Thread-safe registry** — `ClientManager` uses `threading.Lock` around all reads and writes to `clients.json`
- **Slug as routing key** — `/{slug}/` prefix routes to correct client data
- **Parser detection at fetch time** — `parser_used` field updated after each successful fetch
- **Redeploy = immediate re-fetch** — triggers the scheduler job now, updates status
- **Status transitions**: `pending` → `running` (success) or `error` (failure)
- **São Paulo timezone** — all timestamps displayed in `America/Sao_Paulo`
- **4-hour JWT expiry** — shorter window limits damage if a token is stolen; no refresh token mechanism currently
