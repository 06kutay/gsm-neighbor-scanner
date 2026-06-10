"""
GSM Neighbor Scanner CLI Tool.

This is the main entry point for gsm-neighbor-scanner. It parses CLI arguments,
runs grgsm_livemon_headless and tshark concurrently, decodes system information
messages, and outputs the results.
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
logger = logging.getLogger("gsm_scanner")


def main() -> None:
    """
    Main function to execute the CLI scan.
    """
    parser = argparse.ArgumentParser(
        description=(
            "gsm-neighbor-scanner: A CLI tool to tune an SDR to a GSM carrier, "
            "capture BCCH data, and decode SI2 messages to extract neighbor cell ARFCN lists."
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
        default=15,
        help="Capture duration in seconds (default: 15).",
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

    args = parser.parse_args()

    # Configure verbose logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled.")

    console = Console()

    # Determine list of ARFCNs to scan
    arfcn_list = []
    if args.arfcn is not None:
        arfcn_list.append(args.arfcn)
    else:
        logger.info(f"No target ARFCN provided. Initializing full-band discovery on band {args.band}...")
        # Map band number to grgsm_scanner band string representation
        band_str = f"GSM{args.band}"
        sdr_args = map_sdr_device(args.sdr)
        
        # Execute grgsm_scanner in a subprocess to find active ARFCN carriers
        cmd = ["grgsm_scanner", "-b", band_str, "-s", "4000000", "-g", str(args.gain), "-v", "--args", sdr_args, "--speed", "28"]
        logger.info(f"Running discovery: {' '.join(cmd)}")
        
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
    for current_arfcn in sorted(arfcn_list):
        logger.info(f"==================================================")
        logger.info(f"Starting neighbor scan for ARFCN {current_arfcn}")
        logger.info(f"==================================================")
        
        # 1. Map SDR device and convert ARFCN to frequency
        try:
            sdr_args = map_sdr_device(args.sdr)
            freq_hz = arfcn_to_freq_hz(current_arfcn, args.band)
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

        try:
            # Start tshark FIRST (100ms before gr-gsm) to ensure zero missed packets
            capturer.start()
            time.sleep(0.1)

            # Start gr-gsm
            runner.start()

            logger.info(f"Scan in progress. Capturing for {args.duration} seconds...")
            
            # Sleep in small increments to check for Ctrl+C and process health
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
                    
                time.sleep(0.5)

            logger.info("Duration elapsed. Shutting down capture...")

        except KeyboardInterrupt:
            console.print("\n[bold yellow]Scan interrupted by user.[/bold yellow]")
            interrupted = True
        except Exception as e:
            console.print(f"[bold red]Scanner Error:[/bold red] {e}")
            interrupted = True
        finally:
            runner.stop()
            if not interrupted:
                logger.info("Waiting 2-second grace period for packet flush...")
                time.sleep(2.0)
            capturer.stop()

        if interrupted:
            break

        # 6. Parse PCAP findings
        logger.info("Analyzing captured data...")
        scan_results = parse_pcap(
            pcap_path=str(pcap_path),
            sdr_name=args.sdr,
            serving_arfcn=current_arfcn,
            band=args.band,
            gain_db=args.gain,
            duration_sec=args.duration,
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

        # 8. Print table output
        print_rich_table(scan_results)

        for file_path in saved_files:
            logger.info(f"Log written to: {file_path}")

        if scan_results["neighbour_count"] == 0:
            console.print(
                "[yellow]No SI2 messages captured. Try increasing --duration or --gain.[/yellow]\n"
            )


if __name__ == "__main__":
    main()
