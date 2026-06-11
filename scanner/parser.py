"""
GSMTAP PCAP Message Parser for gsm-neighbor-scanner.

This module reads PCAP files using pyshark, filters for GSMTAP/GSM A-Interface
Radio Resource (RR) messages, and decodes System Information (SI) messages
to extract serving and neighbor cell details.
"""

from datetime import datetime
import logging
import pathlib
import re
from typing import Any, Optional

import pyshark

from scanner.sdr_config import arfcn_to_freq_mhz

logger = logging.getLogger(__name__)


def clean_int(val: Any) -> Optional[int]:
    """
    Safely converts a field value to an integer, supporting hex and decimal string formats.
    """
    if val is None:
        return None
    val_str = str(val).strip()
    if val_str.lower().startswith("0x"):
        try:
            return int(val_str, 16)
        except ValueError:
            pass
    # Match any digit sequence
    digits = re.findall(r"\d+", val_str)
    if digits:
        try:
            return int(digits[0])
        except ValueError:
            pass
    return None


def decode_ba_list(bitmask_hex: str, band: int) -> list[int]:
    """
    Decodes the BCCH Allocation (BA) neighbor cell ARFCN list from the 16-byte
    Neighbour Cell Description bitmask hex string defined in 3GPP TS 44.018 Section 10.5.2.22.

    Args:
        bitmask_hex: Hexadecimal string representing the 16-byte field.
        band: The active GSM band (used as metadata).

    Returns:
        Sorted list of neighbor ARFCNs.
    """
    if not bitmask_hex:
        return []

    # Keep only hex characters
    clean_hex = "".join(c for c in bitmask_hex if c.isalnum())

    # Standard Neighbour Cell Description is 16 bytes (32 hex characters)
    # If the capture includes an IEI header byte (34 hex characters), strip it
    if len(clean_hex) == 34:
        clean_hex = clean_hex[2:]
    elif len(clean_hex) < 32:
        clean_hex = clean_hex.ljust(32, "0")
    else:
        clean_hex = clean_hex[:32]

    try:
        byte_data = bytes.fromhex(clean_hex)
    except ValueError:
        logger.error(f"Failed to parse hex string for BA list decoding: {bitmask_hex}")
        return []

    arfcn_list = []

    # Bitmap 0 format:
    # Byte 0 (Octet 2 of IE): Format ID in bits 8 and 7 (should be 00).
    # Bit 6 is EXT-IND, Bit 5 is BA-IND.
    # Bits 4, 3, 2, 1 correspond to ARFCN 124, 123, 122, 121.
    # Bytes 1-15 (Octets 3-17) contain 8 bits each, representing ARFCN 120 down to 1.
    for i in range(16):
        if i >= len(byte_data):
            break
        b = byte_data[i]
        if i == 0:
            # First byte: only the lowest 4 bits are ARFCNs
            for bit_pos in range(4):
                if b & (1 << bit_pos):
                    arfcn_list.append(121 + bit_pos)
        else:
            # Remaining 15 bytes: all 8 bits represent ARFCNs
            # Bit 7 (MSB) to Bit 0 (LSB) mapping to ARFCNs:
            # For byte index i, MSB represents ARFCN: 120 - 8*(i-1)
            # LSB represents ARFCN: 120 - 8*(i-1) - 7 = 113 - 8*(i-1)
            for bit_pos in range(8):
                if b & (1 << bit_pos):
                    arfcn_list.append(113 - 8 * (i - 1) + bit_pos)

    # Remove duplicates and sort
    arfcn_list = sorted(list(set(arfcn_list)))
    logger.debug(f"Decoded BA list bitmap '{clean_hex}' -> ARFCNs: {arfcn_list}")
    return arfcn_list


def check_msg_type(packet: Any) -> Optional[int]:
    """
    Finds and extracts the message type integer from a packet.
    """
    for layer in packet.layers:
        if layer.layer_name in ["gsm_a_rr", "gsm_a", "gsm_a_ccch", "gsm_a.ccch"]:
            # Check common attribute naming styles in pyshark
            for attr in ["msg_rr_type", "msg_type", "message_type", "gsm_a_dtap_msg_rr_type"]:
                if hasattr(layer, attr):
                    return clean_int(getattr(layer, attr))

            # Scan internal field dictionary if direct access fails
            try:
                for k, v in layer._all_fields.items():
                    if "msg_rr_type" in k or "message_type" in k or "gsm_a_dtap_msg_rr_type" in k:
                        return clean_int(v.get_default_value())
            except Exception:
                pass
    return None


def extract_serving_cell_info(packet: Any) -> dict[str, Any]:
    """
    Extracts serving cell identity parameters (MCC, MNC, LAC, CID) from SI3/SI4.
    """
    info = {}
    for layer in packet.layers:
        if layer.layer_name in ["gsm_a_rr", "gsm_a", "gsm_a_ccch", "gsm_a.ccch"]:

            # 1. Extract MCC
            mcc = None
            for attr in ["mcc", "lai_mcc", "gsm_a_lai_mcc", "e212_lai_mcc"]:
                if hasattr(layer, attr):
                    mcc = str(getattr(layer, attr))
                    break
            if not mcc:
                try:
                    for k, v in layer._all_fields.items():
                        if k.endswith(".mcc") or k.endswith(".lai_mcc") or k.endswith(".e212_lai_mcc"):
                            mcc = str(v.get_default_value())
                            break
                except Exception:
                    pass
            if mcc:
                info["mcc"] = mcc

            # 2. Extract MNC
            mnc = None
            for attr in ["mnc", "lai_mnc", "gsm_a_lai_mnc", "e212_lai_mnc"]:
                if hasattr(layer, attr):
                    mnc = str(getattr(layer, attr))
                    break
            if not mnc:
                try:
                    for k, v in layer._all_fields.items():
                        if k.endswith(".mnc") or k.endswith(".lai_mnc") or k.endswith(".e212_lai_mnc"):
                            mnc = str(v.get_default_value())
                            break
                except Exception:
                    pass
            if mnc:
                # Ensure correct format (pad with leading zero if needed, e.g. "1" -> "01")
                if len(mnc) == 1:
                    mnc = "0" + mnc
                info["mnc"] = mnc

            # 3. Extract LAC (Location Area Code)
            lac = None
            for attr in ["lac", "lai_lac", "gsm_a_lai_lac", "gsm_a_lac"]:
                if hasattr(layer, attr):
                    lac = clean_int(getattr(layer, attr))
                    break
            if lac is None:
                try:
                    for k, v in layer._all_fields.items():
                        if k.endswith(".lac") or k.endswith(".lai_lac") or k.endswith(".gsm_a_lac"):
                            lac = clean_int(v.get_default_value())
                            break
                except Exception:
                    pass
            if lac is not None:
                info["lac"] = lac

            # 4. Extract Cell Identity (CID)
            cid = None
            for attr in ["cell_identity", "ci", "cell_id", "gsm_a_bssmap_cell_ci"]:
                if hasattr(layer, attr):
                    cid = clean_int(getattr(layer, attr))
                    break
            if cid is None:
                try:
                    for k, v in layer._all_fields.items():
                        if k.endswith(".cell_identity") or k.endswith(".ci") or k.endswith(".gsm_a_bssmap_cell_ci"):
                            cid = clean_int(v.get_default_value())
                            break
                except Exception:
                    pass
            if cid is not None:
                info["cid"] = cid

            # 5. Extract Cell Barred Access
            cell_barr = None
            for attr in ["cell_barr_access", "cell_barr", "gsm_a_rr_cell_barr_access"]:
                if hasattr(layer, attr):
                    cell_barr = clean_int(getattr(layer, attr))
                    break
            if cell_barr is None:
                try:
                    for k, v in layer._all_fields.items():
                        if k.endswith(".cell_barr_access") or k.endswith(".cell_barr"):
                            cell_barr = clean_int(v.get_default_value())
                            break
                except Exception:
                    pass
            if cell_barr is not None:
                info["cell_barred"] = "Barred" if cell_barr == 1 else "Not Barred"

            # 6. Extract Call Re-establishment
            re = None
            for attr in ["re", "reestablishment", "gsm_a_rr_re"]:
                if hasattr(layer, attr):
                    re = clean_int(getattr(layer, attr))
                    break
            if re is None:
                try:
                    for k, v in layer._all_fields.items():
                        if k.endswith(".re") or k.endswith(".reestablishment"):
                            re = clean_int(v.get_default_value())
                            break
                except Exception:
                    pass
            if re is not None:
                info["reestablishment"] = "Allowed" if re == 0 else "Not Allowed"

            # 7. Extract Emergency Call Allowed
            acc = None
            for attr in ["acc", "gsm_a_rr_acc", "access_control_class"]:
                if hasattr(layer, attr):
                    acc = getattr(layer, attr)
                    break
            if acc is None:
                try:
                    for k, v in layer._all_fields.items():
                        if k.endswith(".acc") or k.endswith(".access_control_class"):
                            acc = v.get_default_value()
                            break
                except Exception:
                    pass
            if acc is not None:
                try:
                    val_str = str(acc).strip()
                    if val_str.lower().startswith("0x"):
                        acc_val = int(val_str, 16)
                    else:
                        acc_val = int(val_str)
                    # Bit 10 represents ACC Class 10 (Emergency calls barred if 1, allowed if 0)
                    is_barred = (acc_val & 0x0400) != 0
                    info["emergency_call"] = "Not Allowed" if is_barred else "Allowed"
                except Exception:
                    pass

            # 8. Extract RXLEV-ACCESS-MIN
            rxlev = None
            for attr in ["rxlev_access_min", "rxlev", "gsm_a_rr_rxlev_access_min"]:
                if hasattr(layer, attr):
                    rxlev = clean_int(getattr(layer, attr))
                    break
            if rxlev is None:
                try:
                    for k, v in layer._all_fields.items():
                        if k.endswith(".rxlev_access_min") or k.endswith(".rxlev"):
                            rxlev = clean_int(v.get_default_value())
                            break
                except Exception:
                    pass
            if rxlev is not None:
                info["rxlev_access_min_dbm"] = -110 + rxlev

            # 9. Extract MS-TXPWR-MAX-CCH
            txpwr = None
            for attr in ["ms_txpwr_max_cch", "txpwr", "gsm_a_rr_ms_txpwr_max_cch"]:
                if hasattr(layer, attr):
                    txpwr = clean_int(getattr(layer, attr))
                    break
            if txpwr is None:
                try:
                    for k, v in layer._all_fields.items():
                        if k.endswith(".ms_txpwr_max_cch") or k.endswith(".txpwr"):
                            txpwr = clean_int(v.get_default_value())
                            break
                except Exception:
                    pass
            if txpwr is not None:
                info["ms_txpwr_max_cch"] = txpwr

            # 10. Extract GPRS Indicator
            gprs = None
            for attr in ["gprs_indicator", "gprs_support", "gsm_a_rr_gprs_indicator"]:
                if hasattr(layer, attr):
                    gprs = clean_int(getattr(layer, attr))
                    break
            if gprs is None:
                try:
                    for k, v in layer._all_fields.items():
                        if "gprs_indicator" in k or "gprs_support" in k or k.endswith(".gprs"):
                            gprs = clean_int(v.get_default_value())
                            break
                except Exception:
                    pass
            if gprs is not None:
                info["gprs_supported"] = "Supported" if gprs == 1 else "Not Supported"

    return info


def extract_inter_rat_neighbours(packet: Any) -> tuple[list[int], list[int]]:
    """
    Extracts LTE (EARFCN) and UMTS (UARFCN) neighbor lists from SI2ter/SI2quater.
    """
    lte = []
    umts = []
    for layer in packet.layers:
        if layer.layer_name in ["gsm_a_rr", "gsm_a_ccch", "gsm_a.ccch", "gsm_a"]:
            # Scan fields for uarfcn and earfcn
            try:
                for k, v in layer._all_fields.items():
                    if "earfcn" in k:
                        try:
                            val = int(v.get_default_value())
                            if val not in lte:
                                lte.append(val)
                        except Exception:
                            pass
                    elif "uarfcn" in k:
                        try:
                            val = int(v.get_default_value())
                            if val not in umts:
                                umts.append(val)
                        except Exception:
                            pass
            except Exception:
                pass
    return lte, umts


def extract_signal_dbm(packet: Any) -> Optional[float]:
    """
    Extracts the signal power (in dBm) from the GSMTAP header.
    """
    if hasattr(packet, "gsmtap"):
        layer = packet.gsmtap
        for attr in ["signal_dbm", "dbm", "signal_db", "signal_power"]:
            if hasattr(layer, attr):
                try:
                    return float(getattr(layer, attr))
                except ValueError:
                    pass
        # Scan fields
        try:
            for k, v in layer._all_fields.items():
                if "dbm" in k or "signal" in k:
                    try:
                        return float(v.get_default_value())
                    except ValueError:
                        pass
        except Exception:
            pass
    return None


def parse_pcap(
    pcap_path: str,
    sdr_name: str,
    serving_arfcn: int,
    band: int,
    gain_db: float,
    duration_sec: int,
) -> dict[str, Any]:
    """
    Reads a captured PCAP file, parses GSMTAP layers, and returns structured network info.

    Args:
        pcap_path: Path to the PCAP file.
        sdr_name: Configured SDR type.
        serving_arfcn: Serving carrier ARFCN.
        band: Serving band.
        gain_db: RX gain settings.
        duration_sec: Scan duration.

    Returns:
        Structured scan summary dict.
    """
    # Empty result blueprint
    result: dict[str, Any] = {
        "scan_time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sdr": sdr_name,
        "serving_arfcn": serving_arfcn,
        "band": band,
        "frequency_mhz": arfcn_to_freq_mhz(serving_arfcn, band),
        "gain_db": gain_db,
        "duration_sec": duration_sec,
        "serving_cell": None,
        "neighbours": [],
        "neighbour_count": 0,
        "raw_pcap": str(pcap_path),
    }

    pcap_file = pathlib.Path(pcap_path)
    if not pcap_file.exists() or pcap_file.stat().st_size == 0:
        logger.warning(f"PCAP file {pcap_path} is missing or empty.")
        return result

    cap = None
    neighbours_set: set[int] = set()
    lte_set: set[int] = set()
    umts_set: set[int] = set()
    serving_info: dict[str, Any] = {}
    signal_powers: list[float] = []

    # Reset asyncio event loop for this thread to prevent pyshark conflicts
    import asyncio
    created_loop = False
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        created_loop = True
    except Exception as e:
        logger.debug(f"Failed to setup event loop: {e}")

    try:
        # Load PCAP file, filtering at the tshark reader level for gsmtap
        cap = pyshark.FileCapture(str(pcap_file), display_filter="gsmtap")

        for packet in cap:
            # 1. Parse Signal Power
            sig = extract_signal_dbm(packet)
            if sig is not None:
                signal_powers.append(sig)

            # 2. Check if GSM Radio Resource or CCCH layer is present
            target_layer = None
            for layer in packet.layers:
                if layer.layer_name in ["gsm_a_rr", "gsm_a_ccch", "gsm_a.ccch", "gsm_a"]:
                    target_layer = layer
                    break

            if target_layer is not None:
                layer = target_layer
                msg_type = check_msg_type(packet)

                if msg_type == 26:  # 0x1a: System Information Type 2
                    bitmask_hex = None

                    # Attempt to extract Neighbour Cell Description hex string
                    for attr in [
                        "neighbour_cell_desc",
                        "neighbour_cell_description",
                        "ba_list",
                        "neighbour_cells",
                        "gsm_a_rr_arfcn_list",
                    ]:
                        if hasattr(layer, attr):
                            field_obj = getattr(layer, attr)
                            bitmask_hex = getattr(field_obj, "raw_value", str(field_obj))
                            break

                    # Fallback to field_names iteration on direct field failure
                    if not bitmask_hex:
                        try:
                            field_names = layer.field_names
                            logger.debug(
                                f"Direct field access failed for SI2 neighbor list. "
                                f"Available fields: {field_names}"
                            )
                            for fname in field_names:
                                if (
                                    "neighbour" in fname
                                    or "ba_list" in fname
                                    or "cell_desc" in fname
                                ):
                                    field_obj = getattr(layer, fname)
                                    bitmask_hex = getattr(field_obj, "raw_value", str(field_obj))
                                    logger.debug(
                                        f"Recovered neighbor bitmask from field: '{fname}' = {bitmask_hex}"
                                    )
                                    break
                        except Exception as e:
                            logger.debug(f"Failed to extract fields via field_names: {e}")

                    if bitmask_hex:
                        decoded_arfcs = decode_ba_list(bitmask_hex, band)
                        for arf in decoded_arfcs:
                            # Do not add serving ARFCN to neighbor list
                            if arf != serving_arfcn:
                                neighbours_set.add(arf)
                    else:
                        logger.warning("SI2 message received but Neighbour Cell Description field not found.")

                elif msg_type in [27, 28]:  # 0x1b / 0x1c: System Information Type 3 / 4
                    cell_data = extract_serving_cell_info(packet)
                    if cell_data:
                        serving_info.update(cell_data)

                elif msg_type in [6, 7]:  # 0x03 / 0x07: System Information Type 2ter / 2quater
                    lte_list, umts_list = extract_inter_rat_neighbours(packet)
                    lte_set.update(lte_list)
                    umts_set.update(umts_list)

    except Exception as e:
        logger.error(f"Error occurred during PCAP parsing: {e}")
    finally:
        if cap:
            try:
                cap.close()
            except Exception:
                pass
            try:
                del cap
            except Exception:
                pass
        if 'created_loop' in locals() and created_loop:
            try:
                loop.close()
            except Exception:
                pass

    # 3. Assemble and populate results
    # serving cell data
    if serving_info:
        # Default ARFCN to serving CLI param if not found
        serving_info.setdefault("arfcn", serving_arfcn)
        result["serving_cell"] = {
            "arfcn": serving_info.get("arfcn"),
            "mcc": serving_info.get("mcc", ""),
            "mnc": serving_info.get("mnc", ""),
            "lac": serving_info.get("lac"),
            "cid": serving_info.get("cid"),
            "cell_barred": serving_info.get("cell_barred"),
            "reestablishment": serving_info.get("reestablishment"),
            "emergency_call": serving_info.get("emergency_call"),
            "rxlev_access_min_dbm": serving_info.get("rxlev_access_min_dbm"),
            "ms_txpwr_max_cch": serving_info.get("ms_txpwr_max_cch"),
            "gprs_supported": serving_info.get("gprs_supported"),
        }
        if signal_powers:
            avg_power = sum(signal_powers) / len(signal_powers)
            result["serving_cell"]["avg_signal_power_dbm"] = round(avg_power, 1)

    # neighbor cell list
    neighbours_list = []
    for arf in sorted(list(neighbours_set)):
        try:
            freq_mhz = arfcn_to_freq_mhz(arf, band)
            neighbours_list.append({"arfcn": arf, "frequency_mhz": freq_mhz})
        except ValueError:
            # Handle situations where neighbor cell contains ARFCN invalid for the serving band
            # (e.g. multi-band reports decoded in SI2ter/SI2bis or mixed cells)
            logger.warning(
                f"Neighbor ARFCN {arf} is out of range for the chosen band {band}. "
                "Skipping frequency calculation."
            )
            neighbours_list.append({"arfcn": arf, "frequency_mhz": None})

    result["neighbours"] = neighbours_list
    result["neighbour_count"] = len(neighbours_list)
    result["lte_neighbours"] = sorted(list(lte_set))
    result["lte_neighbour_count"] = len(lte_set)
    result["umts_neighbours"] = sorted(list(umts_set))
    result["umts_neighbour_count"] = len(umts_set)

    return result
