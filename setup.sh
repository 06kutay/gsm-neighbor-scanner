#!/usr/bin/env bash
#
# Turnkey Installer for gsm-neighbor-scanner.
# Supports Debian Bookworm, Ubuntu 22.04+, and Fedora 38+.
# Handles system dependencies, firmware downloads, wireshark privileges,
# and Python libraries.
#

set -e

# Log helper functions
log_info() {
    echo -e "\e[32m[INFO]\e[0m $1"
}

log_warn() {
    echo -e "\e[33m[WARN]\e[0m $1"
}

log_error() {
    echo -e "\e[31m[ERROR]\e[0m $1"
}

# Detect distribution
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_ID=$ID
    OS_VERSION_ID=$VERSION_ID
else
    log_error "Cannot detect OS distribution. /etc/os-release not found."
    exit 1
fi

log_info "Detected OS: $NAME ($OS_ID, Version: $OS_VERSION_ID)"

# 1. Install System Dependencies
if [[ "$OS_ID" == "ubuntu" || "$OS_ID" == "debian" ]]; then
    log_info "Updating package repositories..."
    sudo apt-get update

    log_info "Installing system dependencies..."
    # Set DEBIAN_FRONTEND=noninteractive to bypass wireshark non-root prompt hanging
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
        gnuradio \
        gnuradio-dev \
        tshark \
        python3-pip \
        uhd-host \
        libuhd-dev \
        soapysdr-tools \
        python3-soapysdr \
        git \
        cmake \
        build-essential

    # Purge Debian packaged gr-gsm to prevent libosmocore version conflicts
    log_info "Removing conflicting system gr-gsm package if present..."
    sudo apt-get purge -y gr-gsm || true
    sudo apt-get autoremove -y || true

    # Compile gr-gsm from source to avoid libosmocore version mismatches
    log_info "Compiling gr-gsm from source (GNU Radio 3.10 compatible fork)..."
    log_warn "This step may take 3-5 minutes."
    rm -rf gr-gsm-src
    git clone -b maint-3.10 https://github.com/bkerler/gr-gsm.git gr-gsm-src
    cd gr-gsm-src
    mkdir -p build && cd build
    cmake .. -DCMAKE_INSTALL_PREFIX=/usr
    make -j$(nproc)
    sudo make install
    sudo ldconfig
    cd ../..
    rm -rf gr-gsm-src

    # Download USRP firmware images if UHD is installed
    if command -v uhd_images_downloader &> /dev/null; then
        log_info "Downloading USRP UHD firmware images..."
        sudo uhd_images_downloader
    fi

elif [[ "$OS_ID" == "fedora" ]]; then
    log_info "Installing Fedora system dependencies..."
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
        python3-pip \
        gcc \
        gcc-c++

    # Download USRP firmware images
    if command -v uhd_images_downloader &> /dev/null; then
        log_info "Downloading USRP UHD firmware images..."
        sudo uhd_images_downloader
    fi

    # Compile gr-gsm from source on Fedora
    log_warn "Fedora does not package gr-gsm in the default repos."
    log_warn "We will compile gr-gsm from source. This process will take 5-10 minutes."
    
    # Check if grgsm_livemon_headless already exists before building
    if command -v grgsm_livemon_headless &> /dev/null; then
        log_info "gr-gsm is already compiled and present in PATH."
    else
        log_info "Cloning and building gr-gsm..."
        git clone https://github.com/osmocom/gr-gsm.git
        cd gr-gsm
        mkdir -p build && cd build
        cmake .. -DCMAKE_INSTALL_PREFIX=/usr
        make -j$(nproc)
        sudo make install
        sudo ldconfig
        cd ../..
        rm -rf gr-gsm
        log_info "gr-gsm source build completed successfully."
    fi

else
    log_error "Unsupported OS: $OS_ID. Manual installation of GNU Radio, gr-gsm, and tshark required."
    exit 1
fi

# 2. Configure Wireshark non-root execution permissions
log_info "Configuring tshark permissions..."
if getent group wireshark > /dev/null; then
    sudo usermod -aG wireshark "$USER"
    log_info "Added user '$USER' to 'wireshark' group."
    log_warn "IMPORTANT: You must restart your terminal session or run 'newgrp wireshark' for group changes to take effect."
else
    # On some systems, the group might be named wireshark. If it doesn't exist, create it.
    sudo groupadd -f wireshark
    sudo usermod -aG wireshark "$USER"
    log_info "Created 'wireshark' group and added '$USER'."
fi

# Set dumpcap permissions
if [ -f /usr/bin/dumpcap ]; then
    sudo chgrp wireshark /usr/bin/dumpcap
    sudo chmod o-rx /usr/bin/dumpcap
    sudo setcap cap_net_raw,cap_net_admin=eip /usr/bin/dumpcap
fi

# 3. Install Python Dependencies
log_info "Installing Python dependencies from requirements.txt..."
# Check for PEP 668 managed environments (Ubuntu 23.04+, Debian 12+)
if pip3 install --help | grep -q "break-system-packages"; then
    pip3 install -r requirements.txt --break-system-packages
else
    pip3 install -r requirements.txt
fi

log_info "Installation completed successfully!"
echo -e "\n------------------------------------------------------------"
echo -e "To verify the installation, start a new shell session and run:"
echo -e "    python3 scan_gsm.py --help"
echo -e "------------------------------------------------------------\n"
