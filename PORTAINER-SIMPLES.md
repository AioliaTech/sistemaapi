# 🚀 Deploy SUPER SIMPLES no Portainer

## Método 1 — Via Console do Portainer (MAIS FÁCIL)

### 1. No Portainer, vá em **Containers** → **Add container**

Preencha:

| Campo | Valor |
|-------|-------|
| **Name** | `revendai-panel` |
| **Image** | `python:3.11-slim` |
| **Command** | deixe vazio |
| **Console** | `Interactive & TTY` ✅ |
| **Restart policy** | `Unless stopped` |

### 2. Na aba **Network**, em **Publish a new network port**:

| Host | Container |
|------|-----------|
| `3000` | `3000` |

### 3. Na aba **Env**, adicione:

| Name | Value |
|------|-------|
| `ADMIN_EMAIL` | `admin@revendai.com` |
| `ADMIN_PASSWORD` | `@Admin123` |
| `JWT_SECRET` | `sua-string-aleatoria-aqui` |
| `BASE_URL` | `http://IP_DO_SERVIDOR:3000` |

### 4. Na aba **Volumes**, adicione:

| Container | Volume |
|-----------|--------|
| `/app/data` | `revendai_data` (create new) |

### 5. Clique em **Deploy the container**

### 6. Depois que o container iniciar, clique nele → **Console** → **Connect**

No terminal que abrir, cole:

```bash
cd /app
apt-get update && apt-get install -y git curl
git clone https://github.com/AioliaTech/sistemaapi.git .
pip install --no-cache-dir -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 3000
```

Pronto! Acesse `http://IP_DO_SERVIDOR:3000`

---

## Método 2 — Via SSH (ainda mais simples)

Se você tem acesso SSH ao servidor:

```bash
# 1. Conecte ao servidor
ssh usuario@IP_DO_SERVIDOR

# 2. Clone e rode
git clone https://github.com/AioliaTech/sistemaapi.git
cd sistemaapi
cp .env.example .env
nano .env  # Preencha as variáveis

# 3. Suba
docker-compose up -d

# 4. Veja os logs
docker-compose logs -f
```

Acesse `http://IP_DO_SERVIDOR:3000`

---

## 🎯 Qual método usar?

- **Tem acesso SSH?** → Use o **Método 2** (SSH) — é o mais rápido
- **Só tem Portainer?** → Use o **Método 1** (Console)

Ambos funcionam perfeitamente!
