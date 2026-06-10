# GSM Neighbor Scanner — Kolay Kurulum Rehberi 🐒

Bu rehber, projeyi başka bir temiz Linux makinede sıfırdan kurup çalıştırmanızı en basit adımlarla açıklar.

---

## Kurulum ve Çalıştırma Adımları

Sistemi yeni bir makinede çalıştıracak kişinin yapması gereken adımlar:

### 🍌 ADIM 1: Kodu Bilgisayara İndirin
Terminali açın ve repoyu bilgisayarınıza klonlayın:
```bash
git clone https://github.com/<kullanici-adi>/gsm-neighbor-scanner.git
```

### 🍌 ADIM 2: Proje Klasörüne Girin
```bash
cd gsm-neighbor-scanner
```

### 🍌 ADIM 3: Kurulumu Başlatın (Tek Komut)
Aşağıdaki komut işletim sisteminizi otomatik algılar, gerekli tüm anten sürücülerini (`gr-gsm`, `gnuradio`, `tshark`) kurar ve Python sanal ortamını hazırlar.
> **Önemli:** Bu komutu `root` (sudo) olarak **çalıştırmayın**. Normal kullanıcı olarak çalıştırın. Script gerektiğinde kendisi şifre isteyecektir.
```bash
chmod +x install.sh && ./install.sh
```

### 🍌 ADIM 4: Paket Yakalama Yetkisini Tanımlayın
Tshark yetkilerinin bilgisayarınızda aktif olması için terminale şu komutu yazın:
```bash
newgrp wireshark
```

### 🍌 ADIM 5: SDR Cihazınızı Takın ve Tarayın! 📡
SDR donanımınızı USB portuna taktıktan sonra tarama yapmaya hazırsınız:

* **Belirli bir GSM Kanalını Dinlemek İçin:**
  ```bash
  ./gsm-scan --arfcn 118 --band 900 --sdr b210 --gain 40 --duration 20
  ```

* **Tüm Bandı Otomatik Taramak İçin (ARFCN belirtmeden):**
  ```bash
  ./gsm-scan --band 900 --sdr b210 --gain 40 --duration 20
  ```

Tüm tarama raporları ekrana canlı olarak yansıtılacak ve ayrıca `logs/` klasörü altına kaydedilecektir.
