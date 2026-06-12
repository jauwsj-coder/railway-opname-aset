# Web App Opname Aset untuk Railway

Versi mandiri untuk Railway. Browser HP melakukan scan QR, sedangkan backend Flask membaca dan memperbarui Google Sheets melalui Service Account.

## Header Google Sheets

`MASTER_ASET`:

```text
NOMOR ASSET | TYPE | NO LAYOUT | USER | OPNAME | KONDISI | LOKASI DETAIL | KONDISI TERAKHIR | STATUS TERAKHIR | TANGGAL OPNAME TERAKHIR | KETERANGAN TERAKHIR
```

`LOG_OPNAME`:

```text
TIMESTAMP | NOMOR ASSET | TYPE | NO LAYOUT | USER | KONDISI | LOKASI DETAIL | KONDISI HASIL OPNAME | STATUS | TANGGAL OPNAME | DOKUMENTASI | KETERANGAN
```

## 1. Siapkan Google Service Account

1. Buka Google Cloud Console dan buat/pilih project.
2. Aktifkan **Google Sheets API** dan **Google Drive API**.
3. Buka **IAM & Admin > Service Accounts**, lalu buat Service Account.
4. Buat key dengan format JSON dan simpan secara aman.
5. Buka Google Sheet database, klik **Share**, lalu bagikan sebagai **Editor** kepada email Service Account yang ada di file JSON.
6. Salin Spreadsheet ID dari URL Google Sheets:
   `https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit`

Jangan memasukkan file JSON Service Account ke GitHub.

## 2. Deploy ke Railway

1. Buat repository GitHub baru dan unggah seluruh isi folder ini.
2. Di Railway, pilih **New Project > Deploy from GitHub repo**.
3. Pilih repository tersebut.
4. Buka tab **Variables**, lalu tambahkan:

```text
GOOGLE_SHEET_ID=ID spreadsheet
GOOGLE_SERVICE_ACCOUNT_JSON=seluruh isi file JSON Service Account dalam satu baris
SETUP_TOKEN=token rahasia bebas
APP_TIMEZONE=Asia/Jakarta
```

5. Buka **Settings > Networking > Generate Domain**.
6. Railway akan menyediakan URL HTTPS. HTTPS diperlukan agar kamera HP dapat digunakan.

## 3. Siapkan Header Sheet

Jika header belum sesuai, jalankan endpoint setup sekali menggunakan PowerShell:

```powershell
Invoke-RestMethod -Method Post `
  -Uri "https://DOMAIN-RAILWAY-ANDA/api/setup" `
  -Headers @{"X-Setup-Token"="TOKEN-RAHASIA-ANDA"}
```

Endpoint setup menulis header standar pada baris pertama tanpa menghapus data di baris berikutnya.

## 4. Gunakan dari HP

1. Buka domain Railway menggunakan Chrome HP.
2. Tekan **Scan QR dengan kamera** dan izinkan kamera.
3. Scan QR yang hanya berisi `NOMOR ASSET`, misalnya `AST-0001`.
4. Isi hasil opname lalu tekan **Simpan opname**.

## Menjalankan Lokal

```bash
python -m venv .venv
pip install -r requirements.txt
gunicorn app:app --bind 0.0.0.0:8080
```

Untuk Windows tanpa Gunicorn:

```powershell
$env:PORT="8080"
python app.py
```

Menjalankan pengujian:

```bash
python -m unittest discover -s tests
```
