"""
SDR and GSM Band Configurations for gsm-neighbor-scanner.

This module maps SDR device keywords to gr-osmosdr device string parameters and
performs ARFCN-to-frequency conversions for GSM-850, GSM-900, EGSM-900,
DCS-1800, and PCS-1900 bands.
"""

import logging

logger = logging.getLogger(__name__)

# Map SDR type flags to gr-osmosdr device argument strings
SDR_MAP: dict[str, str] = {
    "b200": "uhd,type=b200",
    "b205": "uhd,type=b200",
    "b210": "uhd,type=b200",
    "limesdr": "soapy,driver=lime",
}


def map_sdr_device(sdr_name: str) -> str:
    """
    Maps the user-provided SDR type to the corresponding gr-osmosdr device string.

    Args:
        sdr_name: Name of the SDR type (b200, b205, b210, limesdr).

    Returns:
        The gr-osmosdr device arguments.

    Raises:
        ValueError: If the SDR type is unsupported.
    """
    sdr_clean = sdr_name.strip().lower()
    if sdr_clean in SDR_MAP:
        device_str = SDR_MAP[sdr_clean]
        logger.info(f"Mapped SDR '{sdr_name}' to gr-osmosdr string: '{device_str}'")
        return device_str
    else:
        raise ValueError(
            f"Unsupported SDR type: '{sdr_name}'. Supported options are: {', '.join(SDR_MAP.keys())}"
        )


def arfcn_to_freq_mhz(arfcn: int, band: int) -> float:
    """
    Calculates the downlink frequency in MHz for a given ARFCN and GSM band.

    Args:
        arfcn: The ARFCN (Absolute Radio Frequency Channel Number).
        band: The GSM frequency band (850, 900, 1800, 1900).

    Returns:
        The downlink carrier frequency in MHz.

    Raises:
        ValueError: If the ARFCN is out of range for the chosen band or if the band is unsupported.
    """
    if band == 900:
        if 1 <= arfcn <= 124:
            # GSM-900
            return 935.0 + 0.2 * arfcn
        elif 975 <= arfcn <= 1023:
            # EGSM-900
            return 935.0 + 0.2 * (arfcn - 1024)
        elif arfcn == 0:
            # EGSM-900 Channel 0 Special Case
            return 935.0
        else:
            raise ValueError(
                f"ARFCN {arfcn} is out of range for band 900. "
                "Valid GSM-900 ranges are 1-124, 975-1023, or 0."
            )
    elif band == 850:
        if 128 <= arfcn <= 251:
            return 869.2 + 0.2 * (arfcn - 128)
        else:
            raise ValueError(
                f"ARFCN {arfcn} is out of range for band 850. Valid range is 128-251."
            )
    elif band == 1800:
        if 512 <= arfcn <= 885:
            return 1805.2 + 0.2 * (arfcn - 512)
        else:
            raise ValueError(
                f"ARFCN {arfcn} is out of range for band 1800 (DCS-1800). Valid range is 512-885."
            )
    elif band == 1900:
        if 512 <= arfcn <= 810:
            return 1930.0 + 0.2 * (arfcn - 512)
        else:
            raise ValueError(
                f"ARFCN {arfcn} is out of range for band 1900 (PCS-1900). Valid range is 512-810."
            )
    else:
        raise ValueError(
            f"Unsupported GSM band: {band}. Supported bands are 850, 900, 1800, 1900."
        )


def arfcn_to_freq_hz(arfcn: int, band: int) -> float:
    """
    Calculates the downlink frequency in Hz for a given ARFCN and GSM band.

    Args:
        arfcn: The ARFCN.
        band: The GSM frequency band.

    Returns:
        The downlink carrier frequency in Hz as a float.
    """
    return arfcn_to_freq_mhz(arfcn, band) * 1_000_000.0
