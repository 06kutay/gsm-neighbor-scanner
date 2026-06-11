"""
GSM Fast Neighbor Scanner CLI Tool.

This is an optimized version of scan_gsm.py. It includes:
1. High-speed, high-bandwidth carrier discovery (8 MHz, Speed 29).
2. Dynamic Early Termination: Polls the captured PCAP file every second.
   As soon as serving cell details and neighbor cells are resolved, it terminates
   the capture immediately, saving up to 80% of scanning time.
"""

import argparse
from datetime import datetime
import logging
import pathlib
import re
import subprocess
import sys
import time

from rich.console import Console

from scanner.capture import TsharkCapturer, find_loopback_interface
from scanner.grgsm_runner import GrGsmRunner
from scanner.output import print_rich_table, save_csv, save_json
from scanner.parser import parse_pcap
from scanner.sdr_config import arfcn_to_freq_hz, map_sdr_device

# Set up logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("gsm_fast_scanner")


def print_sweep_summary(results: list) -> None:
    """
    Renders a unified summary table for all scanned ARFCNs in a sweep.
    """
    from rich.table import Table
    console = Console()
    
    table = Table(
        title="[bold cyan]GSM SWEEP SUMMARY REPORT[/bold cyan]",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("ARFCN", style="cyan", justify="right")
    table.add_column("Frequency", style="green")
    table.add_column("MCC-MNC", style="yellow")
    table.add_column("LAC", style="blue")
    table.add_column("CID", style="blue")
    table.add_column("Power (Avg)", style="magenta")
    table.add_column("Status", style="bold")
    table.add_column("Neighbors (GSM/LTE/UMTS)", style="white")
    
    for res in results:
        arfcn = res.get("serving_arfcn", "N/A")
        freq = f"{res.get('frequency_mhz', 0.0):.1f} MHz"
        serving = res.get("serving_cell")
        
        if serving:
            mcc = serving.get("mcc", "N/A")
            mnc = serving.get("mnc", "N/A")
            mcc_mnc = f"{mcc}-{mnc}" if mcc != "N/A" else "N/A"
            lac = str(serving.get("lac") or "N/A")
            cid = str(serving.get("cid") or "N/A")
            power = f"{serving.get('avg_signal_power_dbm', 0.0):.1f} dBm" if serving.get('avg_signal_power_dbm') is not None else "N/A"
            status = "[green]Resolved[/green]"
        else:
            mcc_mnc = "N/A"
            lac = "N/A"
            cid = "N/A"
            power = "N/A"
            status = "[yellow]Unresolved[/yellow]"
            
        # Compile neighbor lists
        gsm_neighs = [str(n.get("arfcn")) for n in res.get("neighbours", []) if n.get("arfcn") is not None]
        lte_neighs = [f"L:{e}" for e in res.get("lte_neighbours", [])]
        umts_neighs = [f"U:{u}" for u in res.get("umts_neighbours", [])]
        
        all_neighs = gsm_neighs + lte_neighs + umts_neighs
        neighbors_str = ", ".join(all_neighs) if all_neighs else "None"
        
        table.add_row(
            str(arfcn),
            freq,
            mcc_mnc,
            lac,
            cid,
            power,
            status,
            neighbors_str
        )
        
    console.print("\n")
    console.print(table)
    console.print("\n")


def main() -> None:
    """
    Main function to execute the CLI scan.
    """
    parser = argparse.ArgumentParser(
        description=(
            "gsm-neighbor-scanner (FAST): An optimized CLI tool to tune an SDR to a GSM carrier, "
            "capture BCCH data, and decode SI2/3/4 messages with dynamic early termination."
        )
    )

    parser.add_argument(
        "--arfcn",
        type=int,
        required=False,
        default=None,
        help="GSM ARFCN number to tune to (e.g. 60). If not provided, scans the entire band.",
    )
    parser.add_argument(
        "--band",
        type=int,
        required=True,
        choices=[850, 900, 1800, 1900],
        help="GSM Band: 850, 900, 1800, 1900.",
    )
    parser.add_argument(
        "--gain",
        type=float,
        default=30.0,
        help="SDR RX gain in dB (default: 30.0).",
    )
    parser.add_argument(
        "--sdr",
        type=str,
        required=True,
        choices=["b200", "b205", "b210", "limesdr"],
        help="SDR hardware type: b200, b205, b210, limesdr.",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=25,
        help="Maximum capture duration in seconds (default: 25). Early termination will stop sooner if possible.",
    )
    parser.add_argument(
        "--ppm",
        type=int,
        default=0,
        help="Frequency correction in PPM (default: 0).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./logs",
        help="Directory to save PCAP and structured log files (default: ./logs).",
    )
    parser.add_argument(
        "--format",
        type=str,
        default="all",
        choices=["json", "csv", "table", "all"],
        help="Log file format output: json, csv, table, all (default: all).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output (sets logging level to DEBUG).",
    )
    parser.add_argument(
        "--no-early-terminate",
        action="store_true",
        help="Disable dynamic early termination and capture for the full duration.",
    )
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="Recursively scan all detected neighbor cells in a sweep.",
    )

    args = parser.parse_args()

    # Configure verbose logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled.")
    elif args.sweep:
        # Suppress info logging during sweeps to keep terminal clean
        logging.getLogger().setLevel(logging.WARNING)

    console = Console()

    # Determine list of ARFCNs to scan
    arfcn_list = []
    if args.arfcn is not None:
        arfcn_list.append(args.arfcn)
    else:
        logger.info(f"No target ARFCN provided. Initializing high-speed full-band discovery on band {args.band}...")
        # Map band number to grgsm_scanner band string representation
        band_str = f"GSM{args.band}"
        sdr_args = map_sdr_device(args.sdr)
        
        # Execute grgsm_scanner in a subprocess to find active ARFCN carriers
        # Optimized: 8 MHz sample rate (-s 8000000) and Speed 29
        cmd = ["grgsm_scanner", "-b", band_str, "-s", "8000000", "-g", str(args.gain), "-v", "--args", sdr_args, "--speed", "29"]
        logger.info(f"Running optimized discovery: {' '.join(cmd)}")
        
        import os
        import select
        
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                bufsize=1
            )
            
            output_lines = []
            start_time = time.time()
            timeout = 100  # 100 seconds timeout for full scan is extremely safe
            
            while True:
                # Check for overall timeout
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    logger.warning("Discovery timeout reached. Terminating process...")
                    proc.terminate()
                    break
                
                # Check if process is still running
                poll_res = proc.poll()
                
                # Use select to check if output is available (timeout 0.5 seconds)
                rlist, _, _ = select.select([proc.stdout], [], [], 0.5)
                if rlist:
                    line = proc.stdout.readline()
                    if not line:  # EOF reached
                        break
                    output_lines.append(line)
                    # Strip and log the line to console
                    line_stripped = line.strip()
                    if line_stripped:
                        logger.info(f"[grgsm_scanner] {line_stripped}")
                    continue
                
                # If no data is available and process is done, we can exit the loop
                if poll_res is not None:
                    break
                    
            # Wait for cleanup and ensure process is terminated
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Process did not exit. Killing it...")
                proc.kill()
                proc.wait()
                
            output = "".join(output_lines)
        except Exception as e:
            console.print(f"[bold red]Discovery Error:[/bold red] Failed to execute grgsm_scanner: {e}")
            sys.exit(1)

        try:
            # Find ARFCN values in the output
            discovered_arfcs = re.findall(r"ARFCN:\s*(\d+)", output, re.IGNORECASE)
            discovered_arfcs.extend(re.findall(r"arfcn:\s*(\d+)", output, re.IGNORECASE))
            
            # Filter and deduplicate
            seen = set()
            for arf_str in discovered_arfcs:
                arf_val = int(arf_str)
                if arf_val not in seen:
                    seen.add(arf_val)
                    arfcn_list.append(arf_val)
                    
            if not arfcn_list:
                # If regex parsing fails, try to capture any numbers listed under scanning results
                logger.warning("No ARFCNs parsed with regex. Checking fallback pattern...")
                for line in output.splitlines():
                    if "Cid:" in line or "LAC:" in line:
                        match = re.search(r"\b\d+\b", line)
                        if match:
                            val = int(match.group(0))
                            if val not in seen and val < 1024:
                                seen.add(val)
                                arfcn_list.append(val)
                                
            # Fallback if no carriers detected
            if not arfcn_list:
                console.print(f"[bold yellow]No active carriers discovered on band {args.band}.[/bold yellow]")
                sys.exit(0)
                
            logger.info(f"Active carriers discovered: {sorted(arfcn_list)}")
        except Exception as e:
            console.print(f"[bold red]Discovery Parsing Error:[/bold red] {e}")
            sys.exit(1)

    # Output directory preparation
    output_dir_path = pathlib.Path(args.output_dir).resolve()
    output_dir_path.mkdir(parents=True, exist_ok=True)
    loopback_iface = None

    # Run neighbor cell sweep for each target ARFCN
    scanned_arfcs = set()
    to_scan = list(sorted(arfcn_list))
    sweep_results = []

    while to_scan:
        current_arfcn = to_scan.pop(0)
        if current_arfcn in scanned_arfcs:
            continue
        scanned_arfcs.add(current_arfcn)

        # 1. Map SDR device and convert ARFCN to frequency
        try:
            sdr_args = map_sdr_device(args.sdr)
            freq_hz = arfcn_to_freq_hz(current_arfcn, args.band)
            if args.sweep:
                console.print(f"[bold cyan]>>> Scanning ARFCN {current_arfcn}[/bold cyan] ({freq_hz/1e6:.1f} MHz) | Queue: {len(to_scan)} remaining")
            else:
                logger.info(f"==================================================")
                logger.info(f"Starting FAST neighbor scan for ARFCN {current_arfcn}")
                logger.info(f"==================================================")
                logger.info(f"Target frequency: {freq_hz / 1e6:.3f} MHz (ARFCN {current_arfcn}, Band {args.band})")
        except ValueError as e:
            console.print(f"[bold red]Configuration Error for ARFCN {current_arfcn}:[/bold red] {e}")
            continue

        # 2. Detect loopback interface dynamically (if not already done)
        if loopback_iface is None:
            try:
                loopback_iface = find_loopback_interface()
            except RuntimeError as e:
                console.print(f"[bold red]Interface Error:[/bold red] {e}")
                sys.exit(1)

        # 3. Setup output file paths
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pcap_path = output_dir_path / f"scan_arfcn{current_arfcn}_{timestamp}.pcap"

        # 4. Instantiate runners
        runner = GrGsmRunner(
            freq_hz=freq_hz,
            gain=args.gain,
            ppm=args.ppm,
            device_string=sdr_args,
            output_dir=output_dir_path,
        )
        capturer = TsharkCapturer(interface=loopback_iface, output_pcap=pcap_path)

        # 5. Concurrent Subprocess Execution
        logger.info("Initializing scan. Starting subprocesses...")
        interrupted = False
        early_terminated = False
        scan_failed = False
        elapsed_sec = args.duration

        try:
            # Start tshark FIRST (100ms before gr-gsm) to ensure zero missed packets
            capturer.start()
            time.sleep(0.1)

            # Start gr-gsm
            runner.start()

            logger.info(f"Scan in progress. Capturing (Max {args.duration}s)...")
            
            # Sleep and poll loop
            start_time = time.time()
            while time.time() - start_time < args.duration:
                # Check if processes crashed prematurely
                if runner.process and runner.process.poll() is not None:
                    exit_code = runner.process.poll()
                    raise RuntimeError(
                        f"grgsm_livemon_headless exited prematurely with exit code {exit_code}. "
                        "Check logs/grgsm_livemon.log for details."
                    )
                if capturer.process and capturer.process.poll() is not None:
                    exit_code = capturer.process.poll()
                    raise RuntimeError(f"tshark exited prematurely with exit code {exit_code}.")
                
                # Check for Early Termination criteria
                elapsed = time.time() - start_time
                if not args.no_early_terminate and elapsed >= 3.0:
                    try:
                        # Parse the temporary pcap file written by tshark
                        # (tshark is writing to /tmp/scan_arfcn... which capturer.temp_pcap exposes)
                        temp_pcap = capturer.temp_pcap
                        if temp_pcap and temp_pcap.exists() and temp_pcap.stat().st_size > 24:
                            scan_results = parse_pcap(
                                pcap_path=str(temp_pcap),
                                sdr_name=args.sdr,
                                serving_arfcn=current_arfcn,
                                band=args.band,
                                gain_db=args.gain,
                                duration_sec=int(elapsed),
                            )
                            
                            # Conditions for full decode:
                            # 1. Serving cell identity (MCC, MNC, LAC, CID) resolved
                            # 2. Neighbor cell count > 0 (SI2 captured)
                            serving = scan_results.get("serving_cell")
                            has_serving = serving and serving.get("mcc") and serving.get("mnc") and serving.get("lac") and serving.get("cid")
                            has_neighbors = scan_results.get("neighbour_count", 0) > 0
                            
                            if has_serving and has_neighbors:
                                if args.sweep:
                                    console.print(f"    [green]✓[/green] Resolved in {elapsed:.1f}s")
                                else:
                                    logger.info(f"[Optimizer] Early termination triggered at {elapsed:.1f}s: all parameters resolved!")
                                early_terminated = True
                                elapsed_sec = int(elapsed)
                                break
                    except Exception as e:
                        logger.debug(f"Early termination check error: {e}")

                time.sleep(1.0)

            if not early_terminated:
                                if args.sweep:
                                    console.print(f"    [yellow]⚠[/yellow] Timeout reached ({args.duration}s)")
                                else:
                                    logger.info("Maximum duration elapsed. Shutting down capture...")

        except KeyboardInterrupt:
            console.print("\n[bold yellow]Scan interrupted by user.[/bold yellow]")
            interrupted = True
        except Exception as e:
            if args.sweep:
                console.print(f"    [red]✗[/red] Scanner Error: {e}")
            else:
                console.print(f"[bold red]Scanner Error on ARFCN {current_arfcn}:[/bold red] {e}")
            scan_failed = True
        finally:
            runner.stop()
            capturer.stop()
            # Cooldown to allow SDR hardware to release USB locks before the next scan
            if not interrupted and to_scan:
                logger.info("Waiting 2-second SDR cooldown/reset period...")
                time.sleep(2.0)

        if interrupted:
            break

        if scan_failed:
            continue

        # 6. Parse final PCAP findings
        logger.info("Analyzing final captured data...")
        scan_results = parse_pcap(
            pcap_path=str(pcap_path),
            sdr_name=args.sdr,
            serving_arfcn=current_arfcn,
            band=args.band,
            gain_db=args.gain,
            duration_sec=elapsed_sec,
        )

        scan_results["scan_time"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

        # 7. Write Logs
        save_format = args.format.lower()
        saved_files = []
        try:
            if save_format in ["json", "all"]:
                json_file = save_json(scan_results, output_dir_path, f"arfcn{current_arfcn}_{timestamp}")
                saved_files.append(str(json_file))
            if save_format in ["csv", "all"]:
                csv_file = save_csv(scan_results, output_dir_path, f"arfcn{current_arfcn}_{timestamp}")
                saved_files.append(str(csv_file))
        except Exception as e:
            console.print(f"[bold red]Logging Error:[/bold red] Failed to write output logs: {e}")

        # 8. Print table output / Save for summary
        if args.sweep:
            sweep_results.append(scan_results)
        else:
            print_rich_table(scan_results)
            for file_path in saved_files:
                logger.info(f"Log written to: {file_path}")
            if scan_results["neighbour_count"] == 0:
                console.print(
                    "[yellow]No SI2 messages captured. Try increasing --gain or adjusting antenna.[/yellow]\n"
                )

        # 9. Queue neighbor ARFCNs if sweep option is active
        if args.sweep:
            for neighbour in scan_results.get("neighbours", []):
                n_arfcn = neighbour.get("arfcn")
                if n_arfcn is not None and n_arfcn not in scanned_arfcs and n_arfcn not in to_scan:
                    logger.info(f"[Sweep] Queueing newly discovered neighbor ARFCN {n_arfcn} for scanning.")
                    to_scan.append(n_arfcn)

    # 10. Print final sweep summary report
    if args.sweep and sweep_results:
        print_sweep_summary(sweep_results)


if __name__ == "__main__":
    main()
