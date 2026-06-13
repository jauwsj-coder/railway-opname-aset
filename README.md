# Web App Opname Aset untuk Railway

Web app mobile untuk scan QR, opname aset, login petugas dari sheet `ROLE`, Score Card per role, serta sinkronisasi dashboard ke Google Sheets.

## Struktur Sheet

`MASTER_ASET`:

```text
NOMOR ASSET | TYPE | NO LAYOUT | USER | OPNAME | KONDISI | AREA | LOKASI DETAIL | KONDISI TERAKHIR | STATUS TERAKHIR | TANGGAL OPNAME TERAKHIR | KETERANGAN TERAKHIR
```

`LOG_OPNAME`:

```text
TIMESTAMP | NOMOR ASSET | TYPE | NO LAYOUT | USER | KONDISI | LOKASI DETAIL | AREA | KONDISI HASIL OPNAME | STATUS | TANGGAL OPNAME | DOKUMENTASI | KETERANGAN | NAMA PETUGAS | ID USER | ROLE
```

Tiga kolom terakhir diperlukan agar sistem dapat mengetahui petugas dan menghitung Score Card berdasarkan `ROLE`.

`ROLE`:

```text
NAMA USER | ID USER | ROLE | AREA
```

Contoh:

```text
GA CORPORATE | 1001 | SUPER ADMIN | ALL
PIC ASET 1 | 1006 | PIC ASET | GRAMERCY
```

Aturan akses area:

- User dengan `ROLE` yang mengandung `SUPER ADMIN` dan `AREA` bernilai `ALL` dapat melihat dashboard, mencari, dan memproses aset dari seluruh area.
- User selain itu hanya dapat melihat dashboard, Score Card, mencari, dan memproses aset dengan `AREA` yang sama seperti pada sheet `ROLE`.
- Role gabungan seperti `SUPER ADMIN, PIC ASET` tetap dianggap Super Admin.

`DASHBOARD` dibuat dan diperbarui otomatis. Isinya ringkasan aset dan Score Card per role.

## Konfigurasi Google

1. Aktifkan **Google Sheets API** dan **Google Drive API** di Google Cloud.
2. Buat Service Account dan key JSON.
3. Bagikan Google Spreadsheet sebagai **Editor** kepada email Service Account.
4. Jangan memasukkan file JSON Service Account ke GitHub.

## Deploy Railway

Upload seluruh isi folder ini ke repository GitHub, lalu deploy repository tersebut di Railway.

Tambahkan Railway Variables:

```text
GOOGLE_SHEET_ID=ID spreadsheet
GOOGLE_SERVICE_ACCOUNT_JSON=seluruh isi JSON Service Account dalam satu baris
SETUP_TOKEN=token rahasia bebas
APP_SECRET_KEY=rangkaian acak panjang untuk token sesi
APP_TIMEZONE=Asia/Jakarta
```

Generate domain melalui **Settings > Networking > Generate Domain**. Kamera hanya berfungsi pada domain HTTPS.

## Setup atau Migrasi Header

Jalankan sekali setelah deploy:

```powershell
Invoke-RestMethod -Method Post `
  -Uri "https://DOMAIN-RAILWAY-ANDA/api/setup" `
  -Headers @{"X-Setup-Token"="TOKEN-RAHASIA-ANDA"}
```

Isi sheet `ROLE` setelah setup. Endpoint setup menulis header standar di baris pertama dan tidak menghapus data baris berikutnya.

## Score Card dan Sheet Dashboard

- Score Card menghitung persentase jumlah opname berdasarkan `ROLE` petugas yang login.
- Urutan ditampilkan dari persentase tertinggi ke terendah.
- Sheet `DASHBOARD` otomatis diperbarui setelah submit opname.
- Sheet `DASHBOARD` selalu berisi ringkasan seluruh area, termasuk saat submit dilakukan PIC area tertentu.
- Tombol **Sync Sheet** hanya tersedia untuk `SUPER ADMIN` dengan `AREA` bernilai `ALL`.

## Scanner Tidak Berfungsi

1. Pastikan web app dibuka melalui domain Railway `https://`, bukan alamat HTTP.
2. Izinkan kamera untuk domain Railway pada pengaturan Chrome HP.
3. Gunakan Chrome/Safari terbaru dan pilih kamera belakang bila browser meminta pilihan.
4. Pastikan QR hanya berisi `NOMOR ASSET`, misalnya `AST-0001`.
5. Pesan penyebab kegagalan kamera akan muncul di bawah area scanner.

Saat kamera aktif, tekan **Tangkap & Baca QR**. Aplikasi mengambil frame kamera, membaca QR dari hasil tangkapan, mengisi kolom `NOMOR ASSET`, lalu otomatis menjalankan pencarian aset. Scan real-time juga tetap aktif.

## Pengujian

```bash
python -m unittest discover -s tests
```
