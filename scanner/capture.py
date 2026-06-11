"""
tshark Packet Capture Module for gsm-neighbor-scanner.

This module detects the host loopback interface dynamically using tshark
and provides the TsharkCapturer class to run the tshark packet capture in parallel.
"""

import logging
import os
import pathlib
import shutil
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


def find_loopback_interface() -> str:
    """
    Executes 'tshark -D' to discover the local loopback interface name dynamically.

    Returns:
        The loopback interface name (e.g. 'lo', 'lo0').

    Raises:
        RuntimeError: If tshark is not installed, fails, or loopback is not found.
    """
    binary_path = shutil.which("tshark")
    if not binary_path:
        raise RuntimeError(
            "tshark not found in PATH.\n"
            "Please run setup.sh or run 'sudo apt-get install tshark' / 'sudo dnf install wireshark-cli'."
        )

    try:
        # Run tshark -D
        result = subprocess.run(
            [binary_path, "-D"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        lines = result.stdout.splitlines()
        logger.debug(f"tshark -D output:\n{result.stdout}")

        # Search for lines containing "loopback" or exact name match for common loopback interfaces
        for line in lines:
            line_lower = line.lower()
            parts = line.split(maxsplit=1)
            if len(parts) < 2:
                continue
            name_desc = parts[1]

            # Case 1: Description contains "loopback"
            if "loopback" in line_lower:
                # Extract the first word, stripping any brackets
                name = name_desc.split()[0].strip("()")
                logger.info(f"Dynamically selected loopback interface: '{name}' (via 'loopback' description)")
                return name

        # Case 2: Fallback to exact name checks "lo" or "lo0"
        for line in lines:
            parts = line.split(maxsplit=1)
            if len(parts) < 2:
                continue
            name = parts[1].split()[0].strip("()")
            if name.lower() in ["lo", "lo0"]:
                logger.info(f"Dynamically selected loopback interface: '{name}' (via name match)")
                return name

        raise RuntimeError(
            "Loopback interface could not be identified automatically.\n"
            f"tshark -D output:\n{result.stdout}"
        )
    except subprocess.SubprocessError as e:
        raise RuntimeError(f"Error executing 'tshark -D' to list network interfaces: {e}")


class TsharkCapturer:
    """
    Manages the background execution of the tshark packet capture process.
    """

    def __init__(self, interface: str, output_pcap: pathlib.Path) -> None:
        """
        Initializes the capturer.

        Args:
            interface: Name of the interface to capture on.
            output_pcap: Path to write the output .pcap file.
        """
        self.interface = interface
        self.output_pcap = output_pcap
        self.process = None
        self.log_file = None
        self.temp_pcap = None

    def start(self) -> None:
        """
        Starts the tshark packet capture in the background.

        Raises:
            RuntimeError: If tshark binary is missing or fails to launch.
        """
        binary_path = shutil.which("tshark")
        if not binary_path:
            raise RuntimeError(
                "tshark not found in PATH.\n"
                "Please run setup.sh to install dependencies."
            )

        # Use a temporary file path in /tmp to avoid permission issues when tshark drops privileges
        import tempfile
        self.temp_pcap = pathlib.Path(tempfile.gettempdir()) / self.output_pcap.name

        # Build tshark capture command
        # -i: interface
        # -f: capture filter (only UDP port 4729)
        # -w: output file path
        # -F pcap: capture in classic pcap format
        cmd = [
            binary_path,
            "-i",
            self.interface,
            "-f",
            "udp port 4729",
            "-w",
            str(self.temp_pcap),
            "-F",
            "pcap",
        ]

        logger.info(f"Starting tshark capture: {' '.join(cmd)}")

        try:
            log_file_path = self.output_pcap.parent / "tshark.log"
            self.log_file = open(log_file_path, "w")
            self.process = subprocess.Popen(
                cmd,
                stdout=self.log_file,
                stderr=self.log_file,
                preexec_fn=os.setpgrp,  # Create process group for clean signal routing
            )
            logger.info(f"tshark process spawned with PID {self.process.pid}")
        except Exception as e:
            if self.log_file:
                self.log_file.close()
                self.log_file = None
            raise RuntimeError(f"Failed to launch tshark: {e}")

    def stop(self) -> None:
        """
        Gracefully terminates the background tshark process.
        """
        if not self.process:
            logger.warning("No active tshark process to stop.")
            return

        logger.info(f"Terminating tshark process (PID: {self.process.pid})")
        try:
            import signal
            # Try to terminate the entire process group (kills tshark and child dumpcap)
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except Exception:
                self.process.terminate()

            try:
                self.process.wait(timeout=5)
                logger.info("tshark terminated cleanly.")
            except subprocess.TimeoutExpired:
                logger.warning("tshark did not stop on SIGTERM. Killing process group...")
                try:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                except Exception:
                    self.process.kill()
                self.process.wait()
                logger.info("tshark force-killed.")
        except Exception as e:
            logger.error(f"Error stopping tshark process: {e}")
        finally:
            self.process = None
            if self.log_file:
                self.log_file.close()
                self.log_file = None
            
            # Move the temporary capture file to the final destination
            if self.temp_pcap and self.temp_pcap.exists():
                try:
                    logger.info(f"Moving capture file from {self.temp_pcap} to {self.output_pcap}")
                    self.output_pcap.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(self.temp_pcap), str(self.output_pcap))
                except Exception as e:
                    logger.error(f"Failed to move capture file from temp to final destination: {e}")
