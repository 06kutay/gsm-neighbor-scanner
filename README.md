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
# 1. Run standard scan:
./gsm-scan --arfcn 60 --band 900 --sdr b210 --gain 40 --duration 25

# 2. Run optimized fast scan with dynamic early termination:
./gsm-scan-fast --arfcn 118 --band 900 --sdr b210 --gain 60 --duration 25

# 3. Run recursive topological sweep to scan all discovered neighbor cells:
./gsm-scan-fast --arfcn 118 --band 900 --sdr b210 --gain 60 --duration 25 --sweep
```

## Fast Scanner & Recursive Sweep

### Dynamic Early Termination
The fast scanner (`gsm-scan-fast`) polls the capture output every second. As soon as the serving cell identity and the neighbor cell allocation are fully resolved, it terminates the SDR and packet capture processes immediately. On typical cells, this reduces scan times from 25s to **3 - 4 seconds**.

### Recursive Sweep (`--sweep`)
When `--sweep` is passed, the tool maps the local network topology dynamically:
1. It scans the starting ARFCN.
2. It parses the neighbor cell allocation (SI2 list).
3. It pushes all newly discovered unique neighbor ARFCNs into a dynamic queue.
4. It sequentially scans each neighbor, implementing a 2-second SDR cooldown between targets to allow USB interfaces to re-settle.

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

### Terminal Table Output (Single Scan)
Regardless of the file formats saved, `gsm-neighbor-scanner` renders a beautiful, structured table report to stdout:

```text
╭────────────────────────── GSM NEIGHBOR SCAN REPORT ──────────────────────────╮
│ 📶 SDR Device: b210  |  📡 Band: 900 MHz  |  ⏱️ Duration: 4s  |  🕒 Time     │
│ (UTC): 2026-06-11T11:44:03Z                                                  │
│ 🎯 Serving ARFCN: 118  |  🎛️ Serving Freq: 958.6 MHz  |  📈 Gain: 60.0 dB    │
│ ──────────────────────────────────────────────────────────────────────       │
│ 🆔 Serving Cell ID: MCC=286, MNC=02, LAC=50602, CID=16527 (Avg Power: -36.7  │
│ dBm)                                                                         │
│ 🔓 Cell Access: Cell Barred: Not Barred  |  Re-establishment: Allowed  |     │
│ Emergency Call: Allowed                                                      │
│ ⚙️ Parameters: Min RX Level: -110 dBm  |  Max Tx Power: 5 dBm  |  GPRS/EDGE: │
│ Supported                                                                    │
╰──────────────────────────────────────────────────────────────────────────────╯
                       Detected Neighbor Cells (9 found)                        
┏━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Type ┃   Channel ID ┃ Frequency (MHz) ┃ Notes / Details                      ┃
┡━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ GSM  │   ARFCN: 119 │           958.8 │ Neighbor cell carrier (C1/C0         │
│      │              │                 │ Allocation)                          │
├──────┼──────────────┼─────────────────┼──────────────────────────────────────┤
│ LTE  │    EARFCN: 1 │             N/A │ E-UTRAN Neighbor Carrier Frequency   │
└──────┴──────────────┴─────────────────┴──────────────────────────────────────┘
```

### Sweep Summary Output (`--sweep`)
When running a recursive topological sweep, a consolidated 7-column report is generated at the end:

```text
                            GSM SWEEP SUMMARY REPORT                            
┏━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┓
┃          ┃          ┃           ┃          ┃ Cell      ┃          ┃          ┃
┃ Carrier  ┃ Cell ID  ┃ Power     ┃ Features ┃ Config    ┃          ┃ Neighbo… ┃
┃ (ARFCN/… ┃ (MCC-MN… ┃ (Avg)     ┃ (Access… ┃ (MinRx/T… ┃ Status   ┃ (GSM/LT… ┃
┡━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━┩
│ 118      │ 286-02 / │ -36.7 dBm │ Allowed  │ Min:-110… │ Resolved │ 119,     │
│ (958.6   │ 50602 /  │           │ / GPRS   │ Tx:5dBm | │          │ 120,     │
│ MHz)     │ 16527    │           │          │ Emerg:Yes │          │ L:1,     │
│          │          │           │          │ Reest:Yes │          │ L:3725   │
└──────────┴──────────┴───────────┴──────────┴───────────┴──────────┴──────────┘
```

### JSON Log Example (`logs/scan_arfcn118_20260611_114358.json`)
```json
{
  "scan_time": "2026-06-11T11:44:03Z",
  "sdr": "b210",
  "serving_arfcn": 118,
  "band": 900,
  "frequency_mhz": 958.6,
  "gain_db": 60.0,
  "duration_sec": 4,
  "serving_cell": {
    "arfcn": 118,
    "mcc": "286",
    "mnc": "02",
    "lac": 50602,
    "cid": 16527,
    "avg_signal_power_dbm": -36.7,
    "cell_barred": "Not Barred",
    "gprs_supported": "Supported",
    "rxlev_access_min_dbm": -110,
    "ms_txpwr_max_cch": 5,
    "emergency_call": "Allowed",
    "reestablishment": "Allowed"
  },
  "neighbours": [
    {"arfcn": 119, "frequency_mhz": 958.8}
  ],
  "lte_neighbours": [1, 276, 3725],
  "umts_neighbours": [],
  "raw_pcap": "logs/scan_arfcn118_20260611_114358.pcap"
}
```

## Troubleshooting

### `grgsm_livemon_headless` not found
This indicates that `gr-gsm` was not installed properly or is not in your shell's `PATH`.
* **Fix:** Re-run `./install.sh` and watch for compilation warnings. On Fedora, make sure the compilation did not fail during `cmake` or `make`. Confirm you can launch it manually: `grgsm_livemon_headless --help`.

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
