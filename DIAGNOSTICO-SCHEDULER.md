# Diagnóstico do Problema do Scheduler

## Problema Relatado
As APIs não estão atualizando a cada 2 horas conforme o scheduler configurado.

## Análise das Possíveis Causas

### 1. **FastAPI startup event não está sendo executado** (MAIS PROVÁVEL)
- O decorator `@app.on_event("startup")` pode estar sendo ignorado
- Uvicorn pode estar rodando com múltiplos workers, causando múltiplas instâncias do scheduler

### 2. **Nenhum cliente registrado** (POSSÍVEL)
- Se não houver clientes em `/app/data/clients.json`, nenhum job será agendado
- O scheduler inicia mas não tem trabalho a fazer

### 3. **APScheduler não está rodando em background**
- O BackgroundScheduler pode não estar persistindo entre reinicializações
- Jobs podem estar sendo criados mas não executados

### 4. **Container reinicia e perde o estado do scheduler**
- Scheduler é in-memory, se o container reiniciar, os jobs são perdidos
- Precisa reagendar na inicialização

## Logs Adicionados para Diagnóstico

Adicionei logs detalhados em:

1. **scheduler.py**:
   - `__init__`: Confirma inicialização do scheduler
   - `start()`: Mostra quantos clientes foram encontrados e jobs agendados
   - `_schedule_client()`: Mostra detalhes de cada job (ID, intervalo, próxima execução)
   - `_fetch_client()`: Mostra quando o fetch é executado

2. **main.py**:
   - `on_startup()`: Confirma que o evento de startup foi disparado
   - `on_shutdown()`: Confirma que o shutdown foi chamado

3. **client_manager.py**:
   - `_load_registry()`: Mostra quantos clientes foram carregados e seus detalhes

## Como Verificar na VPS

### Passo 1: Verificar os logs do container
```bash
# Ver logs em tempo real
docker logs -f <nome-do-container>

# Ou se estiver usando docker stack/swarm
docker service logs -f <nome-do-servico>
```

### Passo 2: Procurar por estas mensagens nos logs

**Se o scheduler está iniciando corretamente:**
```
================================================================================
[APP] ⚡ STARTUP EVENT TRIGGERED em 2026-03-09...
================================================================================
[SCHEDULER] ✓ Scheduler inicializado em 2026-03-09...
[SCHEDULER] ⚡ Método start() chamado em 2026-03-09...
[SCHEDULER] ✓ BackgroundScheduler.start() executado, running=True
[CLIENT_MANAGER] 📂 Carregando registry de data/clients.json
[CLIENT_MANAGER] ✓ X cliente(s) carregado(s)
[SCHEDULER] Iniciando com X cliente(s)
[SCHEDULER] ✓ Job agendado para cliente <id>
[SCHEDULER] ✓ Total de jobs agendados: X
```

**Se NÃO houver clientes:**
```
[CLIENT_MANAGER] ⚠️  Registry não existe em data/clients.json, criando novo
[SCHEDULER] Iniciando com 0 cliente(s)
[SCHEDULER] ⚠️  AVISO: Nenhum cliente encontrado! Nenhum job será agendado.
```

**Se o fetch estiver rodando a cada 2 horas:**
```
[SCHEDULER] 🔄 _fetch_client() chamado em 2026-03-09... para client_id=<id>
[SCHEDULER] ✓ Iniciando fetch para cliente '<nome>' (<slug>)
[SCHEDULER] ✓ Cliente '<nome>': X veículos, parser=<parser>
```

### Passo 3: Verificar se há clientes registrados
```bash
# Entrar no container
docker exec -it <nome-do-container> bash

# Ver o arquivo de clientes
cat /app/data/clients.json

# Verificar se o diretório existe
ls -la /app/data/
```

## Próximos Passos

**Por favor, execute os comandos acima na VPS e me envie:**

1. ✅ Os logs do container (últimas 100 linhas)
2. ✅ O conteúdo do arquivo `/app/data/clients.json` (se existir)
3. ✅ A saída de `ls -la /app/data/`

Com essas informações, poderei confirmar o diagnóstico e aplicar a correção apropriada.

## Possíveis Soluções (aguardando confirmação)

### Solução A: Se o startup event não está sendo chamado
- Migrar de `@app.on_event("startup")` para `lifespan` context manager (FastAPI moderno)
- Ou iniciar o scheduler diretamente no módulo

### Solução B: Se não há clientes registrados
- Verificar por que os clientes não estão sendo persistidos
- Verificar se o volume Docker está montado corretamente

### Solução C: Se o scheduler não está executando os jobs
- Adicionar `misfire_grace_time` aos jobs
- Verificar se há múltiplos workers do uvicorn
- Considerar usar um scheduler externo (cron, celery, etc.)
