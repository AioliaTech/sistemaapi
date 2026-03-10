# Como Ver os Logs na VPS

## Opção 1: Se estiver usando Docker Compose

```bash
# Ver logs em tempo real (últimas linhas e continua mostrando)
docker-compose logs -f

# Ver apenas as últimas 100 linhas
docker-compose logs --tail=100

# Ver logs de um serviço específico
docker-compose logs -f <nome-do-servico>
```

## Opção 2: Se estiver usando Docker Stack (Swarm)

```bash
# Listar os serviços
docker service ls

# Ver logs de um serviço específico (em tempo real)
docker service logs -f <nome-do-servico>

# Ver últimas 100 linhas
docker service logs --tail=100 <nome-do-servico>
```

## Opção 3: Se estiver usando Portainer

1. Acesse o Portainer no navegador
2. Vá em **Stacks** ou **Services**
3. Clique no seu stack/service
4. Clique em **Logs** no menu lateral
5. Os logs aparecerão em tempo real

## Opção 4: Docker direto (container individual)

```bash
# Listar containers rodando
docker ps

# Ver logs de um container específico (em tempo real)
docker logs -f <container-id-ou-nome>

# Ver últimas 100 linhas
docker logs --tail=100 <container-id-ou-nome>
```

## O que procurar nos logs:

### ✅ Se tudo estiver funcionando, você verá:

```
================================================================================
[APP] ⚡ STARTUP EVENT TRIGGERED em 2026-03-09...
================================================================================
[SCHEDULER] ✓ Scheduler inicializado em 2026-03-09...
[SCHEDULER] ⚡ Método start() chamado em 2026-03-09...
[SCHEDULER] ✓ BackgroundScheduler.start() executado, running=True
[CLIENT_MANAGER] 📂 Carregando registry de data/clients.json
[CLIENT_MANAGER] ✓ 5 cliente(s) carregado(s)
[CLIENT_MANAGER]   - Cliente1 (cliente1) - status: running
[CLIENT_MANAGER]   - Cliente2 (cliente2) - status: running
...
[SCHEDULER] Iniciando com 5 cliente(s)
[SCHEDULER] ✓ Job agendado para cliente abc-123
[SCHEDULER]   - Job ID: fetch_abc-123
[SCHEDULER]   - Intervalo: 2 horas
[SCHEDULER]   - Próxima execução: 2026-03-09 23:21:00-03:00
...
[SCHEDULER] ✓ Total de jobs agendados: 5
```

### ⚠️ Se houver problema, você verá:

**Problema 1: Nenhum cliente**
```
[CLIENT_MANAGER] ⚠️  Registry não existe em data/clients.json, criando novo
[SCHEDULER] Iniciando com 0 cliente(s)
[SCHEDULER] ⚠️  AVISO: Nenhum cliente encontrado! Nenhum job será agendado.
```

**Problema 2: Startup não está sendo chamado**
```
# Você NÃO verá as linhas com "STARTUP EVENT TRIGGERED"
# Neste caso, o scheduler não inicia
```

**Problema 3: Jobs não executam**
```
# Você verá os jobs sendo agendados, mas nunca verá:
[SCHEDULER] 🔄 _fetch_client() chamado em...
```

## Após 2 horas, você deve ver:

```
[SCHEDULER] 🔄 _fetch_client() chamado em 2026-03-09 23:21:00 para client_id=abc-123
[SCHEDULER] ✓ Iniciando fetch para cliente 'Cliente1' (cliente1)
[SCHEDULER] ✓ Cliente 'Cliente1': 45 veículos, parser=revendamais
```

## Comandos úteis:

```bash
# Ver logs e filtrar apenas linhas do SCHEDULER
docker logs <container> 2>&1 | grep SCHEDULER

# Ver logs e filtrar apenas linhas do APP
docker logs <container> 2>&1 | grep APP

# Ver logs e filtrar apenas linhas do CLIENT_MANAGER
docker logs <container> 2>&1 | grep CLIENT_MANAGER

# Salvar logs em um arquivo
docker logs <container> > logs.txt 2>&1
```

## Me envie:

Copie e cole aqui as primeiras 50-100 linhas dos logs após o redeploy, especialmente as que contêm:
- `[APP]`
- `[SCHEDULER]`
- `[CLIENT_MANAGER]`

Isso me permitirá confirmar o diagnóstico e aplicar a correção apropriada.
