# 🚀 Guia de Deploy — RevendAI Panel

Como o Docker Swarm não suporta `build:` direto do GitHub, vamos usar **docker-compose** no servidor.

---

## 📋 Pré-requisitos

- Servidor Linux com Docker e Docker Compose instalados
- Acesso SSH ao servidor
- Porta 3000 liberada no firewall

---

## 🔧 Deploy via SSH (método recomendado)

### 1. Conecte ao servidor via SSH

```bash
ssh usuario@IP_DO_SERVIDOR
```

### 2. Clone o repositório

```bash
cd /opt  # ou outro diretório de sua preferência
git clone https://github.com/AioliaTech/sistemaapi.git
cd sistemaapi
```

### 3. Configure as variáveis de ambiente

```bash
cp .env.example .env
nano .env  # ou vim .env
```

Preencha com seus valores:
```env
ADMIN_EMAIL=admin@revendai.com
ADMIN_PASSWORD=@Admin123
JWT_SECRET=cole-aqui-uma-string-longa-e-aleatoria
BASE_URL=http://IP_DO_SERVIDOR:3000
```

Para gerar o `JWT_SECRET`:
```bash
openssl rand -hex 32
```

### 4. Inicie o container

```bash
docker-compose up -d
```

### 5. Verifique se está rodando

```bash
docker-compose ps
docker-compose logs -f
```

Você deve ver:
```
[APP] RevendAI Multi-Tenant Platform iniciado
INFO:     Uvicorn running on http://0.0.0.0:3000
```

### 6. Acesse o painel

Abra no navegador:
```
http://IP_DO_SERVIDOR:3000
```

---

## 🔄 Atualizar para nova versão

Quando houver atualizações no GitHub:

```bash
cd /opt/sistemaapi
git pull
docker-compose down
docker-compose up -d --build
```

---

## 🛑 Parar o sistema

```bash
docker-compose down
```

---

## 📊 Monitorar logs

```bash
# Logs em tempo real
docker-compose logs -f

# Últimas 100 linhas
docker-compose logs --tail=100

# Logs de um serviço específico
docker-compose logs -f revendai-panel
```

---

## 🔐 Configurar HTTPS (opcional)

### Opção 1 — Nginx Reverse Proxy + Let's Encrypt

Crie `/etc/nginx/sites-available/revendai`:
```nginx
server {
    listen 80;
    server_name api.revendai.com;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Ative e obtenha certificado SSL:
```bash
sudo ln -s /etc/nginx/sites-available/revendai /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d api.revendai.com
```

### Opção 2 — Cloudflare (mais simples)

1. Adicione o domínio no Cloudflare
2. Ative o proxy (nuvem laranja)
3. SSL/TLS mode: **Full**
4. Pronto — HTTPS automático

---

## 🐛 Troubleshooting

### Container não inicia
```bash
docker-compose logs
```

### Erro "ADMIN_EMAIL is required"
Verifique se o `.env` está no mesmo diretório do `docker-compose.yml`:
```bash
ls -la .env
cat .env
```

### Porta 3000 já em uso
Mude a porta no `docker-compose.yml`:
```yaml
ports:
  - "8080:3000"  # Acesse via porta 8080
```

### Dados não persistem após restart
Verifique se o volume está criado:
```bash
docker volume ls | grep revendai
```

---

## 📁 Estrutura de arquivos no servidor

```
/opt/sistemaapi/
├── .env                    # Suas credenciais (gitignored)
├── docker-compose.yml
├── Dockerfile
├── main.py
├── ... (resto do código)
└── data/                   # Volume Docker (criado automaticamente)
    ├── clients.json
    └── clients/
        └── {slug}/
            └── data.json
```

---

## ✅ Checklist de deploy

- [ ] Servidor Linux com Docker instalado
- [ ] Repositório clonado em `/opt/sistemaapi`
- [ ] Arquivo `.env` criado e preenchido
- [ ] `docker-compose up -d` executado
- [ ] Container rodando (`docker-compose ps`)
- [ ] Painel acessível em `http://IP:3000`
- [ ] Login funcionando
- [ ] DNS configurado (opcional)
- [ ] HTTPS configurado (opcional)
