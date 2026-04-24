# Contexto do Projeto: Sistema de Cache de Fotos para API de Veículos

## Objetivo
Reduzir consumo de tokens da IA substituindo URLs longas de fotos de veículos por URLs curtas servidas via domínio próprio. A IA usa essas URLs como output tokens — URLs menores = economia direta de custo.

## Problema atual
Cada veículo tem ~15 fotos com URLs longas (~84 chars cada):
```
https://clickgarage-prod.s3.us-west-1.amazonaws.com/veiculos/218046/YxpJA9epev8bUXCKFVdkgd2pEidc07ZG.jpg
```
→ ~1.430 chars por veículo só em fotos.

## Solução
Baixar as fotos e servir via domínio curto próprio:
```
https://xx.com/a9Xe83kL.jpg
```
→ ~646 chars por veículo. Redução de ~55%.

---

## Infra existente
- VPS Hetzner com Docker Swarm + Portainer + Traefik
- ~170 projetos de clientes rodando (FastAPI por cliente)
- Sistema já existente: parsers Python (BaseParser + subclasses por fonte) que consomem JSON/XML de estoques e expõem como FastAPI
- Redeploy a cada 2h com fila serial (um projeto por vez)
- Evolution API enviando fotos via WhatsApp — ela baixa a URL pública e envia ao cliente final

## Nova infra a provisionar
- **Hetzner Object Storage** (S3-compatível): armazena as fotos, expõe URLs públicas sem depender do container estar online
  - Custo: ~$0.013/GB/mês
  - URL padrão: `https://bucket.fsn1.your-objectstorage.com/arquivo.jpg`
- **Domínio curto** (ex: `xx.com`, 2-3 chars): CNAME apontando pro bucket → URL final: `https://xx.com/a9Xe83kL.jpg`
- **SQLite local** por instância: persiste o mapeamento `url_original → short_name`

---

## Lógica do sistema

### Geração do nome curto
- MD5 da URL original → primeiros 6 bytes → base62 → 8 chars fixos + extensão original
- Garante determinismo (mesma URL → mesmo nome), sem colisões práticas, sem tabela de sequência
- Exemplo: `a9Xe83kL.jpg`

### Fluxo por ciclo (a cada 2h)
1. `cycle_start()`: marca todas as entradas no SQLite como `seen=0`
2. Para cada foto de cada veículo:
   - Se já existe no SQLite com `downloaded=1` → retorna URL curta, marca `seen=1`
   - Se não existe ou `downloaded=0` → tenta baixar e fazer upload pro Object Storage
     - Sucesso: salva no SQLite como `downloaded=1, seen=1`, retorna URL curta
     - Falha: mantém URL original no JSON, `downloaded=0` — tenta novamente no próximo ciclo
3. `cycle_end()`: deleta do SQLite e do Object Storage tudo que ficou `seen=0` (fotos órfãs — veículos removidos do estoque)

### Integração no BaseParser
```python
async def process_vehicle(self, vehicle: dict) -> dict:
    if fotos := vehicle.get("fotos"):
        vehicle["fotos"] = await photo_cache.resolve_many(fotos)
    return vehicle
```

### Ciclo de atualização
```python
async def run_update_cycle():
    photo_cache.cycle_start()
    try:
        await parse_and_update_all()
    finally:
        removed = photo_cache.cycle_end()
        logger.info(f"Fotos órfãs removidas: {removed}")
```
O `finally` é obrigatório — garante que o sweep roda mesmo se o parse explodir.

---

## Stack técnica
- **Python + asyncio + httpx**: download assíncrono das fotos com semáforo pra limitar conexões simultâneas (evitar rate limit de S3 terceiros)
- **boto3**: upload pro Hetzner Object Storage (API S3-compatível)
- **SQLite**: persistência do mapeamento, leve, sem dependência externa
- **FastAPI**: já existente, nenhuma mudança estrutural necessária
- **Traefik**: já existente, gerencia SSL e roteamento

---

## Pontos de atenção
- **Semáforo nos downloads**: limitar concorrência (ex: `asyncio.Semaphore(20)`) pra não tomar rate limit dos S3 de terceiros
- **Disponibilidade**: com Object Storage, fotos ficam online mesmo se container reiniciar — resolve o problema da Evolution API não conseguir baixar
- **Disco**: não há disco local envolvido — tudo vai direto pro Object Storage
- **Crescimento**: 170 clientes × ~50 carros × ~15 fotos = ~127k imagens. Monitorar tamanho do bucket
- **Domínio**: CNAME do domínio curto apontando pro endpoint público do bucket Hetzner

---

## O que NÃO implementar (overkill pra esse volume)
- Nginx separado pra servir estático
- Redis/cache layer
- Múltiplas instâncias do serviço de foto
- CDN adicional
