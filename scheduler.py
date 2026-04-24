"""
scheduler.py — Multi-tenant APScheduler manager.
A single background cron job updates ALL clients at fixed even hours:
00:00, 02:00, 04:00, 06:00, 08:00, 10:00, 12:00, 14:00, 16:00, 18:00, 20:00, 22:00 (America/Sao_Paulo).
On startup/redeploy, existing data.json files are preserved — no re-parse is forced.
"""

import threading
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import JobLookupError
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
import pytz

if TYPE_CHECKING:
    from client_manager import ClientManager

from xml_fetcher import fetch_for_client


class MultiTenantScheduler:
    def __init__(self, client_manager: "ClientManager"):
        self.client_manager = client_manager
        self.timezone = pytz.timezone("America/Sao_Paulo")
        self.scheduler = BackgroundScheduler(timezone=self.timezone)
        now_local = datetime.now(self.timezone)
        print(f"[SCHEDULER] ✓ Scheduler inicializado em {now_local}")

    def start(self) -> None:
        """Starts the scheduler and schedules a single cron job that updates ALL clients at fixed even hours."""
        now_local = datetime.now(self.timezone)
        print(f"[SCHEDULER] ⚡ Método start() chamado em {now_local}")
        self.scheduler.start()
        print(f"[SCHEDULER] ✓ BackgroundScheduler.start() executado, running={self.scheduler.running}")
        
        clients = self.client_manager.list_clients()
        print(f"[SCHEDULER] Iniciando com {len(clients)} cliente(s)")
        
        if len(clients) == 0:
            print("[SCHEDULER] ⚠️  AVISO: Nenhum cliente encontrado!")
        
        # Agendar UM ÚNICO JOB com horários fixos (cron) — não executa imediatamente no startup
        self._schedule_all_clients_job()
        
        # NÃO executa fetch imediato no startup para não re-parsear dados existentes.
        # Os dados persistidos no volume Docker são mantidos até o próximo cron.
        print(f"[SCHEDULER] ℹ️  Startup sem re-parse: dados existentes serão mantidos até o próximo cron.")
        
        # Log all scheduled jobs
        jobs = self.scheduler.get_jobs()
        print(f"[SCHEDULER] ✓ Total de jobs agendados: {len(jobs)}")
        for job in jobs:
            print(f"[SCHEDULER]   - Job: {job.id}, próxima execução: {job.next_run_time}")
        
        print("[SCHEDULER] Todos os jobs agendados")

    def _schedule_all_clients_job(self) -> None:
        """Schedules a single cron job that updates ALL clients at fixed even hours (00,02,04,...,22)."""
        job_id = "fetch_all_clients"
        # Remove existing job if any
        try:
            self.scheduler.remove_job(job_id)
            print(f"[SCHEDULER] Job existente removido: {job_id}")
        except JobLookupError:
            pass
        
        job = self.scheduler.add_job(
            self._fetch_all_clients,
            "cron",
            hour="0,2,4,6,8,10,12,14,16,18,20,22",
            minute=0,
            second=0,
            id=job_id,
            replace_existing=True,
        )
        print(f"[SCHEDULER] ✓ Job global agendado: atualizar TODOS os clientes nos horários fixos (00,02,04,...,22h)")
        print(f"[SCHEDULER]   - Job ID: {job.id}")
        print(f"[SCHEDULER]   - Trigger: cron (horários fixos do dia)")
        print(f"[SCHEDULER]   - Próxima execução: {job.next_run_time}")
    
    def _fetch_all_clients(self) -> None:
        """Fetches data for ALL clients at once."""
        from photo_cache import photo_cache  # import lazy — evita circular na inicialização

        now_local = datetime.now(self.timezone)
        print("=" * 80)
        print(f"[SCHEDULER] 🔄 ATUALIZAÇÃO GLOBAL iniciada em {now_local}")
        print("=" * 80)

        clients = self.client_manager.list_clients()
        total = len(clients)
        success = 0
        errors = 0

        print(f"[SCHEDULER] Atualizando {total} cliente(s)...")

        # Marca todas as fotos como não-vistas antes de processar os clientes.
        # O cycle_end() no finally remove as que ficarem seen=0 (órfãs).
        photo_cache.cycle_start()

        try:
            for i, client in enumerate(clients, 1):
                try:
                    print(f"[SCHEDULER] [{i}/{total}] Processando '{client.name}' ({client.slug})...")
                    self._fetch_client(client.id)
                    success += 1
                except Exception as e:
                    errors += 1
                    print(f"[SCHEDULER] ❌ Erro ao processar '{client.name}': {e}")
        finally:
            # Roda mesmo se o loop explodir — remove arquivos de fotos órfãs do disco e do SQLite.
            removed = photo_cache.cycle_end()
            if removed:
                print(f"[SCHEDULER] 🗑️  Fotos órfãs removidas: {removed}")

        print("=" * 80)
        print(f"[SCHEDULER] ✓ ATUALIZAÇÃO GLOBAL concluída!")
        print(f"[SCHEDULER]   - Total: {total} clientes")
        print(f"[SCHEDULER]   - Sucesso: {success}")
        print(f"[SCHEDULER]   - Erros: {errors}")
        print(f"[SCHEDULER]   - Próxima atualização: {datetime.now(self.timezone) + timedelta(hours=2)}")
        print("=" * 80)

    def add_client_job(self, client_id: str, run_now: bool = True) -> None:
        """Adds a new client. Optionally triggers an immediate fetch."""
        # Não precisamos mais agendar jobs individuais
        # O job global já vai pegar este cliente na próxima execução
        if run_now:
            self.trigger_now(client_id)
        print(f"[SCHEDULER] Cliente adicionado. Será incluído na próxima atualização global.")

    def remove_client_job(self, client_id: str) -> None:
        """Removes a client. No action needed since we use a global job."""
        # Não precisamos mais remover jobs individuais
        print(f"[SCHEDULER] Cliente removido. Será excluído da próxima atualização global.")

    def trigger_now(self, client_id: str) -> None:
        """Triggers an immediate fetch for a client (redeploy)."""
        print(f"[SCHEDULER] Redeploy imediato para cliente {client_id}")
        # Marca como pending imediatamente para o frontend não exibir o erro antigo
        self.client_manager.update_client_status(client_id=client_id, status="pending")
        # Execute diretamente em background thread (mais confiável que date job)
        thread = threading.Thread(target=self._fetch_client, args=[client_id], daemon=True)
        thread.start()
        print(f"[SCHEDULER] Thread de fetch iniciada para cliente {client_id}")

    def _fetch_client(self, client_id: str) -> None:
        """Actual fetch logic for a single client."""
        client = self.client_manager.get_client(client_id)
        if not client:
            print(f"[SCHEDULER] ❌ Cliente {client_id} não encontrado, pulando fetch")
            return
        output_path = self.client_manager.get_client_data_path(client.slug)

        try:
            # Parse custom URLs if provided
            urls_to_fetch = []
            if client.custom_urls:
                # Parse KEY=VALUE format
                for line in client.custom_urls.strip().split('\n'):
                    line = line.strip()
                    if '=' in line and line.startswith(('XML_URL', 'URL')):
                        url = line.split('=', 1)[1].strip()
                        if url:
                            urls_to_fetch.append(url)
            
            # Use source_url if no custom URLs
            if not urls_to_fetch and client.source_url:
                urls_to_fetch.append(client.source_url)
            
            if not urls_to_fetch:
                raise ValueError("Nenhuma URL configurada (source_url ou custom_urls)")
            
            # Fetch from all URLs and combine results
            all_vehicles = []
            parser_used = "unknown"
            
            for url in urls_to_fetch:
                print(f"[SCHEDULER] Processando URL: {url}")
                result = fetch_for_client(url, output_path)
                all_vehicles.extend(result.get("veiculos", []))
                if result.get("_parser_used"):
                    parser_used = result.get("_parser_used")

            # Resolve URLs de fotos para URLs curtas via Photo Cache.
            # No-op se PHOTO_CACHE_ENABLED=false ou PHOTO_DIR não existir.
            from photo_cache import photo_cache  # import lazy
            if photo_cache.is_enabled():
                all_vehicles = photo_cache.resolve_all_vehicles_sync(all_vehicles)

            # Save combined result
            from xml_fetcher import UnifiedVehicleFetcher
            fetcher = UnifiedVehicleFetcher()
            stats = fetcher._generate_stats(all_vehicles)
            
            combined_result = {
                "veiculos": all_vehicles,
                "_updated_at": datetime.now().isoformat(),
                "_total_count": len(all_vehicles),
                "_sources_processed": len(urls_to_fetch),
                "_parser_used": parser_used,
                "_statistics": stats
            }
            
            import json
            data_file = output_path / "data.json"
            with open(data_file, "w", encoding="utf-8") as f:
                json.dump(combined_result, f, ensure_ascii=False, indent=2)
            
            vehicle_count = len(all_vehicles)
            self.client_manager.update_client_status(
                client_id=client_id,
                status="running",
                parser_used=parser_used,
                vehicle_count=vehicle_count,
            )
            print(f"[SCHEDULER] ✓ Cliente '{client.name}': {vehicle_count} veículos de {len(urls_to_fetch)} fonte(s), parser={parser_used}")

        except Exception as e:
            error_msg = str(e)
            self.client_manager.update_client_status(
                client_id=client_id,
                status="error",
                error=error_msg,
            )
            print(f"[SCHEDULER] ✗ Erro no cliente '{client.name}': {error_msg}")

    def shutdown(self) -> None:
        """Gracefully shuts down the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
