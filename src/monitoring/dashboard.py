"""Rich CLI dashboard."""
import logging
from typing import Dict, Any, List

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich import box
from rich.text import Text

console = Console()
logger = logging.getLogger(__name__)


def render_dashboard(
    risk_summary: Dict[str, Any],
    open_positions: Dict[str, Dict],
    funding_snapshots: Dict[str, Any],
    paper_mode: bool,
) -> None:
    """Render the current bot status to the terminal."""
    console.clear()

    mode_text = "[bold yellow]PAPER MODE[/bold yellow]" if paper_mode else "[bold red]LIVE MODE[/bold red]"
    status = risk_summary.get("status", "UNKNOWN")
    status_color = "green" if status == "RUNNING" else "red"
    status_text = f"[bold {status_color}]{status}[/bold {status_color}]"

    # Header panel
    header = f"Funding Rate Arbitrage Bot  |  Mode: {mode_text}  |  Status: {status_text}"
    console.print(Panel(header, box=box.DOUBLE_EDGE))

    # Equity / PnL table
    eq_table = Table(title="Equity & P&L", box=box.SIMPLE)
    eq_table.add_column("Metric")
    eq_table.add_column("Value", justify="right")
    eq_table.add_row("Current Equity", f"${risk_summary.get('current_equity', 0):,.2f}")
    eq_table.add_row("Total P&L", f"${risk_summary.get('total_pnl', 0):,.2f} ({risk_summary.get('total_pnl_pct', 0):.2f}%)")
    eq_table.add_row("Daily P&L", f"${risk_summary.get('daily_pnl', 0):,.2f}")
    eq_table.add_row("Peak Equity", f"${risk_summary.get('peak_equity', 0):,.2f}")
    eq_table.add_row("Drawdown from Peak", f"{risk_summary.get('drawdown_from_peak_pct', 0):.2f}%")
    eq_table.add_row("Funding Collected", f"${risk_summary.get('total_funding_collected', 0):,.2f}")
    eq_table.add_row("Trade Count", str(risk_summary.get('trade_count', 0)))

    # Positions table
    pos_table = Table(title="Open Positions", box=box.SIMPLE)
    pos_table.add_column("Asset")
    pos_table.add_column("Qty", justify="right")
    pos_table.add_column("Entry Spot", justify="right")
    pos_table.add_column("Notional", justify="right")
    pos_table.add_column("Current APR", justify="right")

    for asset, pos in open_positions.items():
        snap = funding_snapshots.get(asset)
        apr_str = f"{snap.annualized_apr:.2f}%" if snap else "N/A"
        pos_table.add_row(
            asset,
            f"{pos.get('qty', 0):.5f}",
            f"${pos.get('entry_spot', 0):,.2f}",
            f"${pos.get('notional', 0):,.2f}",
            apr_str,
        )

    if not open_positions:
        pos_table.add_row("—", "—", "—", "—", "—")

    console.print(Columns([eq_table, pos_table]))

    if risk_summary.get("halt_reason"):
        console.print(f"[bold red]HALT REASON: {risk_summary['halt_reason']}[/bold red]")
