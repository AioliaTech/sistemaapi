"""
scheduler.py — Multi-tenant APScheduler manager.
Each client gets its own background job that runs every 2 hours.
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import JobLookupError
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from client_manager import ClientManager

from xml_fetcher import fetch_for_client


class MultiTenantScheduler:
    def __init__(self, client_manager: "ClientManager"):
        self.client_manager = client_manager
        self.scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")

    def start(self) -> None:
        """Starts the scheduler and schedules jobs for all existing clients."""
        self.scheduler.start()
        clients = self.client_manager.list_clients()
        print(f"[SCHEDULER] Iniciando com {len(clients)} cliente(s)")
        for client in clients:
            self._schedule_client(client.id)
        print("[SCHEDULER] Todos os jobs agendados")

    def _schedule_client(self, client_id: str) -> None:
        """Schedules a 2-hour interval job for a client."""
        job_id = f"fetch_{client_id}"
        # Remove existing job if any
        try:
            self.scheduler.remove_job(job_id)
        except JobLookupError:
            pass

        self.scheduler.add_job(
            self._fetch_client,
            "interval",
            hours=2,
            id=job_id,
            args=[client_id],
            replace_existing=True,
        )
        print(f"[SCHEDULER] Job agendado para cliente {client_id}")

    def add_client_job(self, client_id: str, run_now: bool = True) -> None:
        """Adds a new client job. Optionally triggers an immediate fetch."""
        self._schedule_client(client_id)
        if run_now:
            self.trigger_now(client_id)

    def remove_client_job(self, client_id: str) -> None:
        """Removes the job for a deleted client."""
        job_id = f"fetch_{client_id}"
        try:
            self.scheduler.remove_job(job_id)
            print(f"[SCHEDULER] Job removido para cliente {client_id}")
        except JobLookupError:
            pass

    def trigger_now(self, client_id: str) -> None:
        """Triggers an immediate fetch for a client (redeploy)."""
        print(f"[SCHEDULER] Redeploy imediato para cliente {client_id}")
        # Run in background thread via scheduler
        self.scheduler.add_job(
            self._fetch_client,
            "date",
            run_date=datetime.now(),
            args=[client_id],
            id=f"redeploy_{client_id}_{datetime.now().timestamp()}",
            replace_existing=False,
        )

    def _fetch_client(self, client_id: str) -> None:
        """Actual fetch logic for a single client."""
        client = self.client_manager.get_client(client_id)
        if not client:
            print(f"[SCHEDULER] Cliente {client_id} não encontrado, pulando fetch")
            return

        print(f"[SCHEDULER] Iniciando fetch para cliente '{client.name}' ({client.slug})")
        output_path = self.client_manager.get_client_data_path(client.slug)

        try:
            result = fetch_for_client(client.source_url, output_path)
            vehicle_count = result.get("_total_count", 0)
            parser_used = result.get("_parser_used", "unknown")

            self.client_manager.update_client_status(
                client_id=client_id,
                status="running",
                parser_used=parser_used,
                vehicle_count=vehicle_count,
            )
            print(f"[SCHEDULER] ✓ Cliente '{client.name}': {vehicle_count} veículos, parser={parser_used}")

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
