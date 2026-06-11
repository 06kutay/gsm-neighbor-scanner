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

    # Colorize serving cell values for maximum clarity
    barred_color = "red" if cell_barred == "Barred" else "green"
    cell_barred_formatted = f"[bold {barred_color}]{cell_barred}[/bold {barred_color}]"
    
    gprs_color = "green" if gprs_supported == "Supported" else "yellow"
    gprs_formatted = f"[bold {gprs_color}]{gprs_supported}[/bold {gprs_color}]"
    
    emerg_color = "green" if emergency_call == "Allowed" else "red"
    emerg_formatted = f"[bold {emerg_color}]{emergency_call}[/bold {emerg_color}]"

    reest_color = "green" if reestablishment == "Allowed" else "red"
    reest_formatted = f"[bold {reest_color}]{reestablishment}[/bold {reest_color}]"

    # Format metadata section with clean emojis and structure
    meta_text = (
        f"[bold cyan]📶 SDR Device:[/bold cyan] {data.get('sdr')}  |  "
        f"[bold cyan]📡 Band:[/bold cyan] {data.get('band')} MHz  |  "
        f"[bold cyan]⏱️ Duration:[/bold cyan] {data.get('duration_sec')}s  |  "
        f"[bold cyan]🕒 Time (UTC):[/bold cyan] {data.get('scan_time')}\n"
        f"[bold cyan]🎯 Serving ARFCN:[/bold cyan] {data.get('serving_arfcn')}  |  "
        f"[bold cyan]🎛️ Serving Freq:[/bold cyan] {data.get('frequency_mhz'):.1f} MHz  |  "
        f"[bold cyan]📈 Gain:[/bold cyan] {data.get('gain_db')} dB\n"
        f"{'─' * 70}\n"
        f"[bold yellow]🆔 Serving Cell ID:[/bold yellow] MCC={mcc}, MNC={mnc}, LAC={lac}, CID={cid} (Avg Power: {pwr} dBm)\n"
        f"[bold yellow]🔓 Cell Access:[/bold yellow] Cell Barred: {cell_barred_formatted}  |  Re-establishment: {reest_formatted}  |  Emergency Call: {emerg_formatted}\n"
        f"[bold yellow]⚙️ Parameters:[/bold yellow] Min RX Level: {rxlev_access_min_dbm}  |  Max Tx Power: {ms_txpwr_max_cch}  |  GPRS/EDGE: {gprs_formatted}"
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

    # Initialize unified neighbors table
    neighbours = data.get("neighbours", [])
    lte_neighbours = data.get("lte_neighbours", [])
    umts_neighbours = data.get("umts_neighbours", [])
    total_neighs = len(neighbours) + len(lte_neighbours) + len(umts_neighbours)

    table = Table(
        title=f"Detected Neighbor Cells ([bold green]{total_neighs}[/bold green] found)",
        header_style="bold cyan",
        show_lines=True,
    )
    table.add_column("Type", justify="center", style="bold")
    table.add_column("Channel ID", justify="right", style="cyan")
    table.add_column("Frequency (MHz)", justify="right", style="magenta")
    table.add_column("Notes / Details", justify="left")

    idx = 0
    # Add GSM Neighbors
    for n in neighbours:
        arf = n.get("arfcn")
        freq = n.get("frequency_mhz")
        freq_str = f"{freq:.1f}" if freq is not None else "N/A"
        row_style = "white" if idx % 2 == 0 else "grey70"
        table.add_row(
            "[bold cyan]GSM[/bold cyan]",
            f"ARFCN: {arf}",
            freq_str,
            "Neighbor cell carrier (C1/C0 Allocation)",
            style=row_style
        )
        idx += 1

    # Add LTE Neighbors
    for earfcn in lte_neighbours:
        row_style = "white" if idx % 2 == 0 else "grey70"
        table.add_row(
            "[bold magenta]LTE[/bold magenta]",
            f"EARFCN: {earfcn}",
            "N/A",
            "E-UTRAN Neighbor Carrier Frequency",
            style=row_style
        )
        idx += 1

    # Add UMTS Neighbors
    for uarfcn in umts_neighbours:
        row_style = "white" if idx % 2 == 0 else "grey70"
        table.add_row(
            "[bold yellow]UMTS[/bold yellow]",
            f"UARFCN: {uarfcn}",
            "N/A",
            "UTRAN FDD Neighbor Carrier Frequency",
            style=row_style
        )
        idx += 1

    if total_neighs == 0:
        table.add_row("-", "-", "-", "[yellow]No neighbor cells found in capture.[/yellow]")

    console.print(table)
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
