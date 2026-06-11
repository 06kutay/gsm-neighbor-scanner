"""
gr-gsm Subprocess Runner for gsm-neighbor-scanner.

This module provides the GrGsmRunner class to execute and manage the background
grgsm_livemon_headless process, capturing logs and handling graceful shutdown.
"""

import logging
import os
import pathlib
import shutil
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


class GrGsmRunner:
    """
    Manages the background execution of the grgsm_livemon_headless process.
    """

    def __init__(
        self,
        freq_hz: float,
        gain: float,
        ppm: int,
        device_string: str,
        output_dir: pathlib.Path,
    ) -> None:
        """
        Initializes the runner.

        Args:
            freq_hz: Frequency in Hz (e.g. 947000000.0).
            gain: RX Gain in dB (e.g. 30.0).
            ppm: Frequency correction in PPM.
            device_string: gr-osmosdr device arguments (e.g. 'uhd,type=b210').
            output_dir: Path to directory where logs/outputs are written.
        """
        self.freq_hz = freq_hz
        self.gain = gain
        self.ppm = ppm
        self.device_string = device_string
        self.output_dir = output_dir
        self.process: Optional[subprocess.Popen] = None
        self.log_file = self.output_dir / "grgsm_livemon.log"

    def start(self) -> None:
        """
        Starts the grgsm_livemon_headless process in the background.

        Raises:
            RuntimeError: If grgsm_livemon_headless binary is not installed or starts with error.
        """
        # Validate binary existence, prioritizing package-managed paths
        binary_path = None
        for path in ["/usr/bin/grgsm_livemon_headless", "/usr/local/bin/grgsm_livemon_headless"]:
            if os.path.exists(path) and os.access(path, os.X_OK):
                binary_path = path
                break

        if not binary_path:
            binary_path = shutil.which("grgsm_livemon_headless")

        if not binary_path:
            raise RuntimeError(
                "grgsm_livemon_headless not found in PATH.\n"
                "Please run the setup.sh script to compile and install gr-gsm and its dependencies."
            )

        # Build command list
        cmd = [
            binary_path,
            "-f",
            f"{self.freq_hz:.1f}",
            "-g",
            f"{self.gain:.1f}",
            "-p",
            str(self.ppm),
            "--args",
            self.device_string,
        ]

        logger.info(f"Starting grgsm_livemon_headless: {' '.join(cmd)}")

        # Ensure directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Open log file for stderr capturing
            self.stderr_log = open(self.log_file, "w")
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=self.stderr_log,
                preexec_fn=os.setpgrp,  # Create process group for clean signal routing
            )
            logger.info(f"grgsm_livemon_headless process spawned with PID {self.process.pid}")
        except Exception as e:
            if hasattr(self, "stderr_log"):
                self.stderr_log.close()
            raise RuntimeError(f"Failed to launch grgsm_livemon_headless: {e}")

    def stop(self) -> None:
        """
        Gracefully terminates the background grgsm_livemon_headless process.
        """
        if not self.process:
            logger.warning("No active grgsm_livemon_headless process to stop.")
            return

        logger.info(f"Terminating grgsm_livemon_headless process (PID: {self.process.pid})")
        try:
            import signal
            # Try to terminate the entire process group
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except Exception:
                self.process.terminate()

            # Wait for it to clean up
            try:
                self.process.wait(timeout=5)
                logger.info("grgsm_livemon_headless terminated cleanly.")
            except subprocess.TimeoutExpired:
                logger.warning("grgsm_livemon_headless did not stop on SIGTERM. Killing process group...")
                try:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                except Exception:
                    self.process.kill()
                self.process.wait()
                logger.info("grgsm_livemon_headless force-killed.")
        except Exception as e:
            logger.error(f"Error stopping grgsm_livemon_headless process: {e}")
        finally:
            if hasattr(self, "stderr_log") and not self.stderr_log.closed:
                self.stderr_log.close()
            self.process = None
