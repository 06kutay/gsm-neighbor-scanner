#!/usr/bin/env bash
#
# Turnkey Installer for GSM Neighbor Scanner
#

set -e

# 1. Print banner
echo "========================================="
echo "GSM Neighbor Scanner — Turnkey Installer"
echo "========================================="
echo ""

# 2. Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo "Do not run as root. Run as your normal user. sudo will be called internally where needed."
    exit 1
fi

# 3. Detect OS from /etc/os-release
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_ID=$ID
    OS_VERSION=$VERSION_ID
    OS_NAME=$NAME
else
    echo "Error: Cannot detect OS (missing /etc/os-release)."
    exit 1
fi

echo "Detected OS: $OS_NAME ($OS_ID $OS_VERSION)"

SUPPORTED=false
if [ "$OS_ID" = "ubuntu" ]; then
    if [ "$OS_VERSION" = "22.04" ] || [ "$OS_VERSION" = "24.04" ]; then
        SUPPORTED=true
    fi
elif [ "$OS_ID" = "debian" ]; then
    if [ "$OS_VERSION" = "12" ]; then
        SUPPORTED=true
    fi
elif [ "$OS_ID" = "fedora" ]; then
    # Parse version as integer
    VER_INT=$(echo "$OS_VERSION" | cut -d. -f1)
    if [ "$VER_INT" -ge 38 ]; then
        SUPPORTED=true
    fi
fi

if [ "$SUPPORTED" = "false" ]; then
    echo "WARNING: Your operating system ($OS_NAME $OS_VERSION) is not officially supported by this turnkey installer."
    read -p "Do you want to continue anyway? [y/N]: " confirm
    if [[ ! "$confirm" =~ ^[yY](es)?$ ]]; then
        echo "Installation aborted."
        exit 1
    fi
fi

# 4. Check for required base tools: git, python3, pip3
echo "Checking base tools..."
MISSING_TOOLS=()
for tool in git python3; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        MISSING_TOOLS+=("$tool")
    fi
done

if ! command -v pip3 >/dev/null 2>&1 && ! python3 -m pip --version >/dev/null 2>&1; then
    MISSING_TOOLS+=("python3-pip")
fi

if [ ${#MISSING_TOOLS[@]} -ne 0 ]; then
    echo "Installing missing base tools: ${MISSING_TOOLS[*]}"
    if [ "$OS_ID" = "ubuntu" ] || [ "$OS_ID" = "debian" ]; then
        sudo apt-get update -y
        sudo apt-get install -y "${MISSING_TOOLS[@]}"
    elif [ "$OS_ID" = "fedora" ]; then
        sudo dnf install -y "${MISSING_TOOLS[@]}"
    else
        echo "Please install ${MISSING_TOOLS[*]} manually and run the script again."
        exit 1
    fi
fi

# 5. Install OS specific dependencies
if [ "$OS_ID" = "ubuntu" ] || [ "$OS_ID" = "debian" ]; then
    echo "Installing system dependencies for Ubuntu/Debian..."
    sudo apt-get update -y
    sudo apt-get install -y \
        gnuradio \
        gr-gsm \
        tshark \
        python3-pip \
        python3-pyshark \
        uhd-host \
        libuhd-dev \
        soapysdr-tools \
        python3-soapysdr \
        limesuite \
        limesuite-dev \
        cmake \
        build-essential

    echo "Downloading UHD firmware images..."
    sudo uhd_images_downloader || true

    echo "Configuring tshark permissions..."
    sudo usermod -aG wireshark "$USER" || true
    echo "NOTE: Log out and back in (or run 'newgrp wireshark') for tshark permissions to take effect."

elif [ "$OS_ID" = "fedora" ]; then
    echo "Installing system dependencies for Fedora..."
    sudo dnf install -y \
        gnuradio \
        gnuradio-devel \
        cmake \
        git \
        libosmocore \
        libosmocore-devel \
        wireshark-cli \
        uhd \
        uhd-devel \
        SoapySDR \
        SoapySDR-devel \
        limesuite \
        limesuite-devel \
        python3-pip

    echo "Building gr-gsm from source..."
    rm -rf /tmp/gr-gsm
    git clone https://github.com/osmocom/gr-gsm.git /tmp/gr-gsm
    cd /tmp/gr-gsm
    mkdir -p build
    cd build
    cmake .. -DCMAKE_INSTALL_PREFIX=/usr
    make -j$(nproc)
    sudo make install
    sudo ldconfig
    cd -

    echo "Configuring wireshark permissions..."
    sudo usermod -aG wireshark "$USER" || true
fi

# 7. Create virtual environment
echo "Setting up Python virtual environment..."
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# 8. Create wrapper scripts
echo "Creating wrapper scripts..."
cat > gsm-scan << 'EOF'
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/scan_gsm.py" "$@"
EOF
chmod +x gsm-scan

cat > gsm-scan-fast << 'EOF'
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/gsm_fast.py" "$@"
EOF
chmod +x gsm-scan-fast

# 9. Create logs/ directory
mkdir -p logs

# 10. Run self-test
echo "Running self-test..."
if .venv/bin/python scan_gsm.py --help >/dev/null 2>&1; then
    echo ""
    echo "Installation successful."
    echo ""
    # 11. Final usage instructions
    echo "Run a scan with:  ./gsm-scan --arfcn 60 --band 900 --sdr b210 --gain 40"
else
    echo "Installation failed. Check errors above."
    exit 1
fi
