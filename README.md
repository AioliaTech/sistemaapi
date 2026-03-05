# RevendAI Multi-Tenant API Platform

Sistema centralizado para gerenciar múltiplas APIs de estoque de veículos em um único painel administrativo.

## 🚀 Funcionalidades

- **Painel administrativo** com login JWT
- **Gerenciamento de clientes** (criar, editar, excluir, redeploy)
- **Auto-detecção de parsers** — suporta 22 formatos diferentes de estoque (XML/JSON)
- **Atualização automática** a cada 2 horas por cliente
- **Status em tempo real** — 🟢 Rodando | 🟡 Pendente | 🔴 Erro
- **API pública por cliente** — `https://api.revendai.com/{slug}/list`, `/api/data`, etc.

---

## 📦 Deploy no Portainer (Docker Swarm)

### 1. Configurar Stack via Git

No Portainer → **Stacks** → **Add stack** → **Repository**:

| Campo | Valor |
|-------|-------|
| Repository URL | `https://github.com/AioliaTech/sistemaapi` |
| Repository reference | `refs/heads/main` |
| Compose path | `docker-stack.yml` |

### 2. Definir variáveis de ambiente

Adicione as 4 variáveis obrigatórias:

| Name | Value | Exemplo |
|------|-------|---------|
| `ADMIN_EMAIL` | E-mail do admin | `admin@revendai.com` |
| `ADMIN_PASSWORD` | Senha do admin | `@Admin123` |
| `JWT_SECRET` | Secret para JWT | `openssl rand -hex 32` |
| `BASE_URL` | URL base do sistema | `https://api.revendai.com` |

### 3. Deploy

Clique em **Deploy the stack** — o Portainer vai:
1. Clonar o repositório
2. Fazer o build da imagem Docker
3. Criar o volume `revendai_data` para persistência
4. Iniciar o container na porta 3000

---

## 🐳 Deploy local (teste)

```bash
# 1. Clone o repositório
git clone https://github.com/AioliaTech/sistemaapi.git
cd sistemaapi

# 2. Configure as variáveis de ambiente
cp .env.example .env
# Edite o .env com seus valores

# 3. Suba o container
docker-compose up --build
```

Acesse: `http://localhost:3000`

---

## 📁 Estrutura do projeto

```
├── main.py                 # FastAPI app + todas as rotas
├── client_manager.py       # CRUD de clientes + registry JSON
├── auth.py                 # JWT authentication
├── scheduler.py            # APScheduler multi-tenant (2h por cliente)
├── xml_fetcher.py          # Fetch + parse por cliente
├── vehicle_mappings.py     # Mapeamentos de categorias
├── fetchers/               # 22 parsers (Altimus, Netcar, Boom, etc.)
├── templates/              # Jinja2 HTML (login + dashboard)
├── static/                 # CSS + JS
├── Dockerfile
├── docker-stack.yml        # Docker Swarm
└── docker-compose.yml      # Local dev
```

---

## 🔐 Segurança

- **JWT tokens** com expiração de 4 horas
- **Variáveis obrigatórias** — app recusa iniciar se `ADMIN_EMAIL`, `ADMIN_PASSWORD` ou `JWT_SECRET` não estiverem definidas
- **`.env` gitignored** — credenciais nunca vão para o repositório
- **Cookies httponly** — proteção contra XSS

---

## 📊 Endpoints públicos por cliente

Cada cliente criado no painel gera automaticamente:

```
GET /{slug}/list              # Listagem de veículos por categoria
GET /{slug}/api/data          # Busca com filtros (modelo, marca, preço, etc.)
GET /{slug}/api/lookup        # Lookup de modelo/categoria
GET /{slug}/api/status        # Status da última atualização
GET /{slug}/api/health        # Health check
```

---

## 🛠️ Tecnologias

- **FastAPI** — framework web
- **Jinja2** — templates HTML
- **APScheduler** — jobs em background
- **python-jose** — JWT
- **Docker** — containerização
- **Docker Swarm** — orquestração

---

## 📝 Licença

Propriedade de **RevendAI** — uso interno.
