"""
scheduler.py — Multi-tenant APScheduler manager.
Each client gets its own background job that runs every 2 hours.
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
        """Starts the scheduler and schedules a single job that updates ALL clients every 2 hours."""
        now_local = datetime.now(self.timezone)
        print(f"[SCHEDULER] ⚡ Método start() chamado em {now_local}")
        self.scheduler.start()
        print(f"[SCHEDULER] ✓ BackgroundScheduler.start() executado, running={self.scheduler.running}")
        
        clients = self.client_manager.list_clients()
        print(f"[SCHEDULER] Iniciando com {len(clients)} cliente(s)")
        
        if len(clients) == 0:
            print("[SCHEDULER] ⚠️  AVISO: Nenhum cliente encontrado!")
        
        # Agendar UM ÚNICO JOB que atualiza TODOS os clientes a cada 2 horas
        self._schedule_all_clients_job()
        
        # Executar IMEDIATAMENTE a primeira vez
        print(f"[SCHEDULER] ⚡ Executando atualização inicial de TODOS os clientes...")
        self._fetch_all_clients()
        
        # Log all scheduled jobs
        jobs = self.scheduler.get_jobs()
        print(f"[SCHEDULER] ✓ Total de jobs agendados: {len(jobs)}")
        for job in jobs:
            print(f"[SCHEDULER]   - Job: {job.id}, próxima execução: {job.next_run_time}")
        
        print("[SCHEDULER] Todos os jobs agendados")

    def _schedule_all_clients_job(self) -> None:
        """Schedules a single job that updates ALL clients every 2 hours."""
        job_id = "fetch_all_clients"
        # Remove existing job if any
        try:
            self.scheduler.remove_job(job_id)
            print(f"[SCHEDULER] Job existente removido: {job_id}")
        except JobLookupError:
            pass
        
        job = self.scheduler.add_job(
            self._fetch_all_clients,
            "interval",
            hours=2,
            id=job_id,
            replace_existing=True,
        )
        print(f"[SCHEDULER] ✓ Job global agendado: atualizar TODOS os clientes a cada 2 horas")
        print(f"[SCHEDULER]   - Job ID: {job.id}")
        print(f"[SCHEDULER]   - Intervalo: 2 horas")
        print(f"[SCHEDULER]   - Próxima execução: {job.next_run_time}")
    
    def _fetch_all_clients(self) -> None:
        """Fetches data for ALL clients at once."""
        now_local = datetime.now(self.timezone)
        print("=" * 80)
        print(f"[SCHEDULER] 🔄 ATUALIZAÇÃO GLOBAL iniciada em {now_local}")
        print("=" * 80)
        
        clients = self.client_manager.list_clients()
        total = len(clients)
        success = 0
        errors = 0
        
        print(f"[SCHEDULER] Atualizando {total} cliente(s)...")
        
        for i, client in enumerate(clients, 1):
            try:
                print(f"[SCHEDULER] [{i}/{total}] Processando '{client.name}' ({client.slug})...")
                self._fetch_client(client.id)
                success += 1
            except Exception as e:
                errors += 1
                print(f"[SCHEDULER] ❌ Erro ao processar '{client.name}': {e}")
        
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
