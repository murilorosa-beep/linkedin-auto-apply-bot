"""
Módulo de rastreamento e histórico de candidaturas e recrutadores em SQLite.
Garante que o bot nunca repita uma vaga, controle limites diários e mapeie a hiring team.
"""

import os
import sqlite3
import contextlib
from datetime import datetime, date
from typing import Optional, Dict, Any, List


class ApplicationTracker:
    def __init__(self, db_path: str = "data/applications.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    @contextlib.contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Cria as tabelas necessárias e executa migrações de schema se preciso."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 1. Tabela de Candidaturas
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS applications (
                    job_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    company TEXT,
                    location TEXT,
                    url TEXT,
                    status TEXT NOT NULL,  -- 'APPLIED', 'DRY_RUN', 'SKIPPED', 'FAILED'
                    notes TEXT,
                    match_score INTEGER DEFAULT 0,
                    applied_date TEXT NOT NULL,  -- YYYY-MM-DD
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Migrações suaves: verificar se colunas existem em bancos pré-existentes
            cursor.execute("PRAGMA table_info(applications)")
            columns = [row["name"] for row in cursor.fetchall()]
            if "match_score" not in columns:
                try:
                    cursor.execute("ALTER TABLE applications ADD COLUMN match_score INTEGER DEFAULT 0")
                except Exception:
                    pass
            if "is_latam_friendly" not in columns:
                try:
                    cursor.execute("ALTER TABLE applications ADD COLUMN is_latam_friendly INTEGER DEFAULT 0")
                except Exception:
                    pass
            if "has_visa_sponsorship" not in columns:
                try:
                    cursor.execute("ALTER TABLE applications ADD COLUMN has_visa_sponsorship INTEGER DEFAULT 0")
                except Exception:
                    pass

            # 2. Tabela de Recrutadores / Hiring Team
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS recruiters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT,
                    recruiter_name TEXT NOT NULL,
                    recruiter_title TEXT,
                    recruiter_profile_url TEXT NOT NULL,
                    company TEXT,
                    job_title TEXT,
                    outreach_note TEXT,
                    executive_pitch TEXT,
                    status TEXT DEFAULT 'PENDING',  -- 'PENDING', 'SENT', 'COPIED'
                    found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(job_id, recruiter_profile_url)
                )
            """)

            cursor.execute("PRAGMA table_info(recruiters)")
            rec_cols = [row["name"] for row in cursor.fetchall()]
            if "executive_pitch" not in rec_cols:
                try:
                    cursor.execute("ALTER TABLE recruiters ADD COLUMN executive_pitch TEXT")
                except Exception:
                    pass

            conn.commit()

    def is_already_processed(self, job_id: str) -> bool:
        """Verifica se uma vaga já foi processada anteriormente."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM applications WHERE job_id = ?", (str(job_id),))
            return cursor.fetchone() is not None

    def record_job(
        self,
        job_id: str,
        title: str,
        company: str,
        location: str,
        url: str,
        status: str,
        notes: str = "",
        match_score: int = 0,
        is_latam_friendly: bool = False,
        has_visa_sponsorship: bool = False
    ):
        """Registra ou atualiza o status e o match score de uma vaga com flags de visto e contratação internacional."""
        today_str = date.today().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO applications (job_id, title, company, location, url, status, notes, match_score, is_latam_friendly, has_visa_sponsorship, applied_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status = excluded.status,
                    notes = excluded.notes,
                    match_score = excluded.match_score,
                    is_latam_friendly = excluded.is_latam_friendly,
                    has_visa_sponsorship = excluded.has_visa_sponsorship,
                    applied_at = CURRENT_TIMESTAMP
            """, (str(job_id), title, company, location, url, status, notes, int(match_score), int(is_latam_friendly), int(has_visa_sponsorship), today_str))
            conn.commit()

    def save_recruiter(self, recruiter_data: Dict[str, Any]) -> bool:
        """Salva ou atualiza os dados de um recrutador mapeado na vaga com nota e pitch executivo."""
        if not recruiter_data or not recruiter_data.get("recruiter_profile_url") and not recruiter_data.get("profile_url"):
            return False

        job_id = str(recruiter_data.get("job_id", ""))
        name = recruiter_data.get("recruiter_name") or recruiter_data.get("name", "")
        title = recruiter_data.get("recruiter_title") or recruiter_data.get("title", "Hiring Team")
        profile_url = recruiter_data.get("recruiter_profile_url") or recruiter_data.get("profile_url", "")
        company = recruiter_data.get("company", "")
        job_title = recruiter_data.get("job_title", "")
        outreach_note = recruiter_data.get("outreach_note", "")
        executive_pitch = recruiter_data.get("executive_pitch", "")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO recruiters (job_id, recruiter_name, recruiter_title, recruiter_profile_url, company, job_title, outreach_note, executive_pitch)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id, recruiter_profile_url) DO UPDATE SET
                    recruiter_title = excluded.recruiter_title,
                    outreach_note = excluded.outreach_note,
                    executive_pitch = excluded.executive_pitch
            """, (job_id, name, title, profile_url, company, job_title, outreach_note, executive_pitch))
            conn.commit()
            return True

    def get_recruiters(self, status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Retorna lista de recrutadores mapeados, com filtro opcional por status."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute("""
                    SELECT id, job_id, recruiter_name, recruiter_title, recruiter_profile_url, company, job_title, outreach_note, status, found_at
                    FROM recruiters
                    WHERE status = ?
                    ORDER BY found_at DESC
                    LIMIT ?
                """, (status, limit))
            else:
                cursor.execute("""
                    SELECT id, job_id, recruiter_name, recruiter_title, recruiter_profile_url, company, job_title, outreach_note, status, found_at
                    FROM recruiters
                    ORDER BY found_at DESC
                    LIMIT ?
                """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def update_recruiter_status(self, recruiter_id: int, new_status: str):
        """Atualiza o status de contato com o recrutador ('PENDING', 'COPIED', 'SENT')."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE recruiters SET status = ? WHERE id = ?", (new_status, int(recruiter_id)))
            conn.commit()

    def get_recruiter_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas dos recrutadores mapeados."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, COUNT(*) as count FROM recruiters GROUP BY status")
            rows = cursor.fetchall()
            stats = {"total": 0, "pending": 0, "copied": 0, "sent": 0}
            for row in rows:
                st_name = row["status"].lower()
                count = row["count"]
                stats["total"] += count
                if st_name in stats:
                    stats[st_name] = count
            return stats

    def get_applications_today_count(self) -> int:
        """Retorna quantas candidaturas foram feitas hoje (contando APPLIED e DRY_RUN)."""
        today_str = date.today().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM applications 
                WHERE applied_date = ? AND status IN ('APPLIED', 'DRY_RUN')
            """, (today_str,))
            return cursor.fetchone()[0]

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas gerais do histórico de candidaturas."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, COUNT(*) as count FROM applications GROUP BY status")
            rows = cursor.fetchall()
            
            stats = {
                "total": 0,
                "applied": 0,
                "dry_run": 0,
                "skipped": 0,
                "failed": 0,
                "today_applied": self.get_applications_today_count()
            }
            
            for row in rows:
                status = row["status"].lower()
                count = row["count"]
                stats["total"] += count
                if status in stats:
                    stats[status] = count

            # Média de Match Score
            cursor.execute("SELECT AVG(match_score) as avg_score FROM applications WHERE match_score > 0")
            avg_row = cursor.fetchone()
            stats["avg_match_score"] = int(avg_row["avg_score"]) if avg_row and avg_row["avg_score"] else 75
                    
            return stats

    def get_recent_applications(self, limit: int = 15) -> List[Dict[str, Any]]:
        """Retorna as candidaturas mais recentes."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT job_id, title, company, location, status, match_score, applied_at, notes
                FROM applications
                ORDER BY applied_at DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def display_statistics(self, console=None):
        """Exibe as estatísticas e histórico recente formatados com tabelas Rich."""
        from rich.console import Console
        from rich.table import Table

        c = console or Console()
        stats = self.get_stats()
        rec_stats = self.get_recruiter_stats()

        c.print("\n[bold cyan][Estatisticas de Candidaturas & Outreach][/bold cyan]")
        table_stats = Table(show_header=True, header_style="bold magenta")
        table_stats.add_column("Metrica", style="dim")
        table_stats.add_column("Quantidade", justify="right")

        table_stats.add_row("Hoje (Candidaturas/Simulacoes)", str(stats["today_applied"]))
        table_stats.add_row("Total Aplicadas (Modo Real)", f"[green]{stats['applied']}[/green]")
        table_stats.add_row("Total em Simulacao (Dry Run)", f"[yellow]{stats['dry_run']}[/yellow]")
        table_stats.add_row("Recrutadores Mapeados", f"[bold cyan]{rec_stats['total']}[/bold cyan]")
        table_stats.add_row("Match Score Medio", f"[magenta]{stats.get('avg_match_score', 0)}%[/magenta]")
        table_stats.add_row("Puladas (Nao Easy Apply)", f"[dim]{stats['skipped']}[/dim]")
        table_stats.add_row("Falhas / Incompativeis", f"[red]{stats['failed']}[/red]")
        table_stats.add_row("Total de Vagas Analisadas", f"[bold]{stats['total']}[/bold]")
        c.print(table_stats)

        recent = self.get_recent_applications(limit=10)
        if recent:
            c.print("\n[bold cyan][Ultimas 10 Vagas Processadas][/bold cyan]")
            table_recent = Table(show_header=True, header_style="bold cyan")
            table_recent.add_column("Cargo")
            table_recent.add_column("Empresa")
            table_recent.add_column("Match")
            table_recent.add_column("Status")
            table_recent.add_column("Data/Hora", style="dim")
            table_recent.add_column("Observacoes", style="dim")

            for r in recent:
                status_style = "green" if r["status"] == "APPLIED" else ("yellow" if r["status"] == "DRY_RUN" else "dim")
                match_val = f"{r.get('match_score', 0)}%" if r.get('match_score') else "-"
                table_recent.add_row(
                    r["title"][:28],
                    r["company"][:18] if r["company"] else "-",
                    match_val,
                    f"[{status_style}]{r['status']}[/{status_style}]",
                    str(r["applied_at"])[:16],
                    (r["notes"] or "")[:30]
                )
            c.print(table_recent)
        else:
            c.print("[dim]Nenhuma vaga registrada ainda no banco de dados.[/dim]\n")
