"""
Output Formatting and File Logging Module for gsm-neighbor-scanner.

This module formats scan results and presents them as a Rich terminal table
as well as writing structured log reports in JSON and CSV formats.
"""

import csv
import json
import logging
import pathlib
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

logger = logging.getLogger(__name__)


def print_rich_table(data: dict[str, Any]) -> None:
    """
    Constructs and prints a rich, structured table to stdout representing scan findings.

    Args:
        data: Dict containing the parsed scan results.
    """
    console = Console()

    # Retrieve serving cell info safely
    serving = data.get("serving_cell")
    mcc = serving.get("mcc", "N/A") if serving else "N/A"
    mnc = serving.get("mnc", "N/A") if serving else "N/A"
    lac = serving.get("lac", "N/A") if serving else "N/A"
    cid = serving.get("cid", "N/A") if serving else "N/A"
    pwr = serving.get("avg_signal_power_dbm", "N/A") if serving else "N/A"
    
    cell_barred = serving.get("cell_barred", "N/A") if serving else "N/A"
    reestablishment = serving.get("reestablishment", "N/A") if serving else "N/A"
    emergency_call = serving.get("emergency_call", "N/A") if serving else "N/A"
    rxlev_val = serving.get("rxlev_access_min_dbm", "N/A") if serving else "N/A"
    rxlev_access_min_dbm = f"{rxlev_val} dBm" if rxlev_val != "N/A" else "N/A"
    txpwr_val = serving.get("ms_txpwr_max_cch", "N/A") if serving else "N/A"
    ms_txpwr_max_cch = f"{txpwr_val} dBm" if txpwr_val != "N/A" else "N/A"
    gprs_supported = serving.get("gprs_supported", "N/A") if serving else "N/A"

    # Format metadata section
    meta_text = (
        f"[bold cyan]SDR Device:[/bold cyan] {data.get('sdr')}  |  "
        f"[bold cyan]Band:[/bold cyan] {data.get('band')} MHz  |  "
        f"[bold cyan]Duration:[/bold cyan] {data.get('duration_sec')}s  |  "
        f"[bold cyan]Time (UTC):[/bold cyan] {data.get('scan_time')}\n"
        f"[bold cyan]Serving ARFCN:[/bold cyan] {data.get('serving_arfcn')}  |  "
        f"[bold cyan]Serving Freq:[/bold cyan] {data.get('frequency_mhz'):.1f} MHz  |  "
        f"[bold cyan]Gain:[/bold cyan] {data.get('gain_db')} dB\n"
        f"[bold cyan]Serving Cell Identity:[/bold cyan] MCC={mcc}, MNC={mnc}, LAC={lac}, CID={cid} (Avg RX Power: {pwr} dBm)\n"
        f"[bold cyan]Cell Access Flags:[/bold cyan] Cell Barred: {cell_barred}  |  Re-establishment: {reestablishment}  |  Emergency Call: {emergency_call}\n"
        f"[bold cyan]Cell Parameters:[/bold cyan] Min RX Level: {rxlev_access_min_dbm}  |  Max Tx Power: {ms_txpwr_max_cch}  |  GPRS/EDGE: {gprs_supported}"
    )

    console.print()
    console.print(
        Panel(
            meta_text,
            title="[bold green]GSM NEIGHBOR SCAN REPORT[/bold green]",
            expand=False,
            border_style="green",
        )
    )

    # Initialize neighbors table
    table = Table(
        title=f"Detected Neighbor Cells ([bold green]{data.get('neighbour_count')}[/bold green] found)",
        header_style="bold cyan",
        show_lines=True,
    )
    table.add_column("ARFCN", justify="right", style="cyan")
    table.add_column("Frequency (MHz)", justify="right", style="magenta")
    table.add_column("Notes", justify="left")

    neighbours = data.get("neighbours", [])
    if not neighbours:
        table.add_row("-", "-", "[yellow]No neighbor cells found in capture.[/yellow]")
    else:
        for idx, n in enumerate(neighbours):
            arf = n.get("arfcn")
            freq = n.get("frequency_mhz")
            freq_str = f"{freq:.1f}" if freq is not None else "N/A"
            row_style = "white" if idx % 2 == 0 else "grey70"
            notes = "Neighbor cell carrier (C1/C0 Allocation)"
            table.add_row(str(arf), freq_str, notes, style=row_style)

    console.print(table)
    console.print()

    # Initialize LTE neighbors table
    lte_neighbours = data.get("lte_neighbours", [])
    if lte_neighbours:
        lte_table = Table(
            title=f"Detected LTE Neighbor Cells ([bold green]{data.get('lte_neighbour_count', 0)}[/bold green] found)",
            header_style="bold cyan",
            show_lines=True,
        )
        lte_table.add_column("EARFCN", justify="right", style="cyan")
        lte_table.add_column("Notes", justify="left")
        for idx, earfcn in enumerate(lte_neighbours):
            row_style = "white" if idx % 2 == 0 else "grey70"
            lte_table.add_row(str(earfcn), "E-UTRAN Carrier Frequency", style=row_style)
        console.print(lte_table)
        console.print()

    # Initialize UMTS neighbors table
    umts_neighbours = data.get("umts_neighbours", [])
    if umts_neighbours:
        umts_table = Table(
            title=f"Detected UMTS Neighbor Cells ([bold green]{data.get('umts_neighbour_count', 0)}[/bold green] found)",
            header_style="bold cyan",
            show_lines=True,
        )
        umts_table.add_column("UARFCN", justify="right", style="cyan")
        umts_table.add_column("Notes", justify="left")
        for idx, uarfcn in enumerate(umts_neighbours):
            row_style = "white" if idx % 2 == 0 else "grey70"
            umts_table.add_row(str(uarfcn), "UTRAN FDD Carrier Frequency", style=row_style)
        console.print(umts_table)
        console.print()


def save_json(data: dict[str, Any], output_dir: pathlib.Path, timestamp: str) -> pathlib.Path:
    """
    Saves scan results as a pretty-printed JSON file.

    Args:
        data: Dict containing results.
        output_dir: Path to write the log files.
        timestamp: File name timestamp string (YYYYMMDD_HHMMSS).

    Returns:
        Path to the saved JSON file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"scan_{timestamp}.json"
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved JSON log: {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"Failed to write JSON log to {file_path}: {e}")
        raise


def save_csv(data: dict[str, Any], output_dir: pathlib.Path, timestamp: str) -> pathlib.Path:
    """
    Saves scan results in flat CSV format.

    Args:
        data: Dict containing results.
        output_dir: Path to write the log files.
        timestamp: File name timestamp.

    Returns:
        Path to the saved CSV file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"scan_{timestamp}.csv"

    headers = [
        "scan_time",
        "sdr",
        "serving_arfcn",
        "band",
        "mcc",
        "mnc",
        "lac",
        "cid",
        "cell_barred",
        "reestablishment",
        "emergency_call",
        "rxlev_access_min_dbm",
        "ms_txpwr_max_cch",
        "gprs_supported",
        "neighbour_arfcn",
        "neighbour_freq_mhz",
    ]

    serving = data.get("serving_cell") or {}
    mcc = serving.get("mcc", "")
    mnc = serving.get("mnc", "")
    lac = serving.get("lac", "")
    cid = serving.get("cid", "")
    cell_barred = serving.get("cell_barred", "")
    reestablishment = serving.get("reestablishment", "")
    emergency_call = serving.get("emergency_call", "")
    rxlev_access_min_dbm = serving.get("rxlev_access_min_dbm", "")
    ms_txpwr_max_cch = serving.get("ms_txpwr_max_cch", "")
    gprs_supported = serving.get("gprs_supported", "")

    neighbours = data.get("neighbours", [])

    try:
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)

            if not neighbours:
                # Log serving cell even if no neighbors were found
                writer.writerow(
                    [
                        data.get("scan_time"),
                        data.get("sdr"),
                        data.get("serving_arfcn"),
                        data.get("band"),
                        mcc,
                        mnc,
                        lac,
                        cid,
                        cell_barred,
                        reestablishment,
                        emergency_call,
                        rxlev_access_min_dbm,
                        ms_txpwr_max_cch,
                        gprs_supported,
                        "",
                        "",
                    ]
                )
            else:
                for n in neighbours:
                    writer.writerow(
                        [
                            data.get("scan_time"),
                            data.get("sdr"),
                            data.get("serving_arfcn"),
                            data.get("band"),
                            mcc,
                            mnc,
                            lac,
                            cid,
                            cell_barred,
                            reestablishment,
                            emergency_call,
                            rxlev_access_min_dbm,
                            ms_txpwr_max_cch,
                            gprs_supported,
                            n.get("arfcn"),
                            n.get("frequency_mhz"),
                        ]
                    )
        logger.info(f"Saved CSV log: {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"Failed to write CSV log to {file_path}: {e}")
        raise
