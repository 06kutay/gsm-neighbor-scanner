# gsm-neighbor-scanner

`gsm-neighbor-scanner` is a standalone, turnkey open-source CLI tool designed for SDR engineers and security researchers to scan and analyze local GSM base station allocations. By tuning a compatible Software Defined Radio (SDR) to a target GSM downlink Broadcast Control Channel (BCCH) ARFCN, the tool decodes System Information Type 2 (SI2) messages to extract the full allocation of neighboring cell carriers. It runs gr-gsm and tshark captures concurrently, extracts serving cell details (MCC, MNC, LAC, CID) from SI3/SI4, and logs the captured measurements to rich console tables, CSV files, and JSON formats for offline mapping.

## Prerequisites

| Requirement | Supported Version(s) | Description |
| :--- | :--- | :--- |
| **Operating System** | Ubuntu 22.04+, Debian 11+ (Bookworm), Fedora 38+ | Standard Linux environments with USB/UHD driver access |
| **Python** | Python 3.10+ | Requires standard `pip3` with type hinting |
| **GNU Radio** | GNU Radio 3.8 / 3.10 | Core SDR signal processing framework |
| **gr-gsm** | Master / Headless compatible | Software library to demodulate and decode GSM frames |
| **tshark** | Wireshark package (CLI) | Packet capture utility to tap GSMTAP frames over UDP |

## Quick Start

```bash
git clone https://github.com/06kutay/gsm-neighbor-scanner.git
cd gsm-neighbor-scanner
chmod +x install.sh && ./install.sh

# After install completes:
./gsm-scan --arfcn 60 --band 900 --sdr b210 --gain 40 --duration 25
```

## CLI Reference

| Argument | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `--arfcn` | `int` | **Yes** | — | Target GSM ARFCN number to tune to. |
| `--band` | `int` | **Yes** | — | GSM band: `850`, `900` (includes EGSM), `1800` (DCS), `1900` (PCS). |
| `--gain` | `float` | No | `30.0` | SDR RX gain in dB. |
| `--sdr` | `str` | **Yes** | — | SDR hardware: `b200`, `b205` (mini), `b210`, `limesdr`. |
| `--duration`| `int` | No | `15` | Capture duration in seconds. |
| `--ppm` | `int` | No | `0` | Frequency correction error in PPM. |
| `--output-dir`| `str` | No | `./logs`| Location to save PCAP and generated log outputs. |
| `--format` | `str` | No | `all` | Saved log format: `json`, `csv`, `table` (none), or `all`. |
| `--verbose` | `flag`| No | `False` | Print raw GSMTAP packet details and debug logs. |

## Supported SDR Hardware

| Device Name | gr-osmosdr device string | CLI `--sdr` value | Drivers Required | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **USRP B200** | `uhd,type=b200` | `b200` | UHD Driver | Standard USRP receiver |
| **USRP B205mini**| `uhd,type=b205mini` | `b205` | UHD Driver | Compact single-channel USRP |
| **USRP B210** | `uhd,type=b210` | `b210` | UHD Driver | Dual-channel transceiver |
| **LimeSDR Mini 2.0**| `soapy,driver=lime` | `limesdr` | SoapySDR + LimeSuite | LimeSuite RF frontend |

## Output Examples

### Terminal Table Output
Regardless of the file formats saved, `gsm-neighbor-scanner` always renders a clean table to stdout:

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        GSM NEIGHBOR SCAN REPORT                                        │
│ SDR Device: b210  |  Band: 900 MHz  |  Duration: 15s  |  Time (UTC): 2026-06-10T12:00:00Z  │
│ Serving ARFCN: 60  |  Serving Freq: 947.0 MHz  |  Gain: 40.0 dB                        │
│ Serving Cell Identity: MCC=286, MNC=01, LAC=12345, CID=6789 (Avg RX Power: -68.4 dBm)  │
└────────────────────────────────────────────────────────────────────────────────────────┘

Detected Neighbor Cells (2 found)
┌───────┬─────────────────┬──────────────────────────────────────────┐
│ ARFCN │ Frequency (MHz) │ Notes                                    │
├───────┼─────────────────┼──────────────────────────────────────────┤
│    55 │           946.0 │ Neighbor cell carrier (C1/C0 Allocation) │
│    62 │           947.4 │ Neighbor cell carrier (C1/C0 Allocation) │
└───────┴─────────────────┴──────────────────────────────────────────┘
```

### JSON Log Example (`logs/scan_20260610_120000.json`)
```json
{
  "scan_time": "2026-06-10T12:00:00Z",
  "sdr": "b210",
  "serving_arfcn": 60,
  "band": 900,
  "frequency_mhz": 947.0,
  "gain_db": 40.0,
  "duration_sec": 15,
  "serving_cell": {
    "arfcn": 60,
    "mcc": "286",
    "mnc": "01",
    "lac": 12345,
    "cid": 6789,
    "avg_signal_power_dbm": -68.4
  },
  "neighbours": [
    {"arfcn": 55, "frequency_mhz": 946.0},
    {"arfcn": 62, "frequency_mhz": 947.4}
  ],
  "neighbour_count": 2,
  "raw_pcap": "logs/scan_20260610_120000.pcap"
}
```

### CSV Log Example (`logs/scan_20260610_120000.csv`)
```csv
scan_time,sdr,serving_arfcn,band,mcc,mnc,lac,cid,neighbour_arfcn,neighbour_freq_mhz
2026-06-10T12:00:00Z,b210,60,900,286,01,12345,6789,55,946.0
2026-06-10T12:00:00Z,b210,60,900,286,01,12345,6789,62,947.4
```

## Troubleshooting

### `grgsm_livemon_headless` not found
This indicates that `gr-gsm` was not installed properly or is not in your shell's `PATH`.
* **Fix:** Re-run `./setup.sh` and watch for compilation warnings. On Fedora, make sure the compilation did not fail during `cmake` or `make`. Confirm you can launch it manually: `grgsm_livemon_headless --help`.

### No packets captured / 0 neighbours found
The scanner captured 0 packets on port 4729. This typically happens when:
* **The carrier is inactive:** Ensure the target ARFCN has an active BCCH carrier in your area.
* **Insufficient Gain:** Try increasing the RX gain using `--gain 45` or `--gain 50`.
* **Insufficient Duration:** System Information Type 2 messages are broadcast in multiframe cycles. Try increasing the scan time with `--duration 30` or `--duration 60`.
* **Lacking Antenna:** Ensure correct RF antennas are connected to the RX port of your SDR.

### USRP device not detected
* **Fix:** Verify the hardware connection via USB. Run:
  ```bash
  uhd_find_devices
  ```
  If this commands returns no devices, check if you have permissions to access the USB bus. You may need to copy the UHD udev rules:
  ```bash
  sudo cp /usr/lib/uhd/utils/uhd-usrp.rules /etc/udev/rules.d/
  sudo udevadm control --reload-rules
  sudo udevadm trigger
  ```

### LimeSDR not detected
* **Fix:** Check that the SoapySDR utilities can locate your LimeSDR:
  ```bash
  SoapySDRUtil --find
  ```
  If not found, ensure LimeSuite and SoapyLMS7 drivers are installed and running.

### tshark permission error
If the tool crashes with a raw socket permission or interface access error:
* **Fix:** Ensure your user belongs to the `wireshark` group:
  ```bash
  sudo usermod -aG wireshark $USER
  ```
  Then reload your group membership in the current terminal:
  ```bash
  newgrp wireshark
  ```

## License

This project is licensed under the MIT License - see the LICENSE file for details.
