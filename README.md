# Web App Opname Aset Railway

## Header Wajib

`ROLE`

```text
NAMA USER | ID USER | ROLE | AREA | AREA SCORECARD
```

Role valid: `SUPER ADMIN`, `SUPER ADMIN, PIC ASET`, dan `PIC ASET`.

- `SUPER ADMIN` tidak masuk Score Board.
- `SUPER ADMIN, PIC ASET` masuk Score Board.
- `PIC ASET` masuk Score Board dan hanya mengakses AREA yang ditugaskan.
- `AREA = ALL` memberikan akses seluruh area.
- `AREA` dan `AREA SCORECARD` dapat berisi beberapa area yang dipisahkan koma.
- `AREA SCORECARD` menentukan target area penilaian Score Board. Jika kosong, sistem menggunakan `AREA`.
- Login wajib cocok antara `NAMA USER` dan `ID USER`.
- ROLE dan AREA dinormalisasi dengan trim dan uppercase.

`MASTER_ASET`

```text
NOMOR ASSET | TYPE | NO LAYOUT | USER | OPNAME | KONDISI | LOKASI DETAIL | AREA | KONDISI TERAKHIR | STATUS TERAKHIR | TANGGAL OPNAME TERAKHIR | KETERANGAN TERAKHIR | DOKUMENTASI TERAKHIR
```

`LOG_OPNAME`

```text
TIMESTAMP | NOMOR ASSET | TYPE | NO LAYOUT | USER | OPNAME | KONDISI | LOKASI DETAIL | AREA | KONDISI TERAKHIR | STATUS TERAKHIR | TANGGAL OPNAME TERAKHIR | KETERANGAN TERAKHIR | DOKUMENTASI TERAKHIR | NAMA PETUGAS | ID USER | ROLE
```

`LOG_OPNAME` adalah sumber utama riwayat, status dashboard, kondisi terakhir, dan Score Board.

## Score Board Progress

Score Board tidak menggunakan penalti atau formula poin berbobot. Setiap PIC dinilai berdasarkan progress penyelesaian aset pada `AREA SCORECARD`:

- Total Aset: jumlah `NOMOR ASSET` unik pada `MASTER_ASET` sesuai AREA SCORECARD.
- Sudah Opname: jumlah `NOMOR ASSET` unik pada `LOG_OPNAME` sesuai AREA SCORECARD dan periode Score Board.
- Belum Opname: Total Aset dikurangi Sudah Opname.
- Progress: Sudah Opname dibagi Total Aset dikali 100%.
- Dokumentasi, keterangan, aset baik, dan aset rusak hanya informasi tambahan.
- `SUPER ADMIN` tidak mempunyai baris Score Board.
- `SUPER ADMIN, PIC ASET` dan `PIC ASET` mempunyai baris Score Board.
- Pilihan periode Score Board: Jan-Jun tahun berjalan, Jul-Des tahun berjalan, atau Semua Periode.

Status progress:

- `100%`: Selesai
- `90-99%`: Hampir Selesai
- `75-89%`: On Track
- `50-74%`: Dalam Proses
- `1-49%`: Perlu Dukungan
- `0%`: Belum Mulai

Saat submit berhasil:

- Header wajib `LOG_OPNAME` yang belum ada ditambahkan otomatis tanpa menghapus data.
- Baris `LOG_OPNAME` ditulis terlebih dahulu, baru `MASTER_ASET` diperbarui.
- `MASTER_ASET.OPNAME` menjadi `DONE`.
- `MASTER_ASET.KONDISI` dan `KONDISI TERAKHIR` mengikuti kondisi opname terbaru.
- `STATUS TERAKHIR` menjadi `SUDAH OPNAME JANUARI - JUNI` atau `SUDAH OPNAME JULI - DESEMBER` sesuai tanggal aktual.
- Foto dokumentasi bersifat opsional. Jika dipilih, Railway mengirim foto ke Google Apps Script upload relay dan URL Drive disimpan pada `DOKUMENTASI TERAKHIR`.
- Web kembali ke menu scan setelah penyimpanan berhasil.

## Perhitungan Dashboard

- Total aset: jumlah aset pada `MASTER_ASET` sesuai akses AREA.
- Sudah opname: jumlah `NOMOR ASSET` unik pada `LOG_OPNAME`.
- Belum opname: total aset dikurangi sudah opname.
- Aset baik: kondisi log terbaru bernilai `OK`, `BAIK`, atau `GOOD`.
- Aset rusak: kondisi log terbaru bernilai `RUSAK`, `BROKEN`, `MAINTENANCE`, atau `NOT OK`.
- Menghapus isi `LOG_OPNAME` akan mengubah dashboard dan Score Board pada refresh berikutnya.
- Sheet `DASHBOARD` hanya salinan tampilan, bukan sumber data.
- Filter tanggal awal/akhir hanya memfilter data opname dari `LOG_OPNAME`.
- Total aset tetap berasal dari `MASTER_ASET` dan tidak berubah ketika periode dipilih.
- Jika header `LOG_OPNAME` belum lengkap, Total Aset dan Belum Opname tetap tampil dari `MASTER_ASET`; metrik berbasis log menjadi nol dan web menampilkan peringatan.
- Pencarian aset dan form opname tetap tampil dari `MASTER_ASET` ketika header log belum lengkap. Riwayat menampilkan peringatan terpisah.
- Submit opname tetap membutuhkan seluruh header `LOG_OPNAME`; jalankan `/api/setup` untuk melengkapinya.

## Pemeriksaan Data

Menu **Pemeriksaan Data** hanya tampil untuk:

- `SUPER ADMIN`
- `SUPER ADMIN, PIC ASET`

Pemeriksaan membaca kolom berdasarkan nama header, bukan posisi kolom. Menu menyediakan:

- Nomor Aset Double pada `MASTER_ASET`.
- Belum Ada Nomor Aset, termasuk berbagai teks penanda nomor aset belum tersedia.
- AREA, LOKASI DETAIL, TYPE, dan USER/PIC kosong.
- Aset yang belum pernah muncul pada `LOG_OPNAME` di periode terpilih.
- Data opname tanpa dokumentasi.
- Aset rusak tanpa keterangan.
- Aset yang sudah opname pada periode terpilih.
- Aset rusak dengan keterangan untuk daftar tindak lanjut.

Pemeriksaan berbasis `LOG_OPNAME` dapat difilter untuk Semua Periode, Jan-Jun tahun berjalan, atau Jul-Des tahun berjalan. Klik kartu ringkasan untuk membuka detail sumber sheet dan nomor baris. Hasil kategori yang sedang dibuka dapat diunduh sebagai **Excel**, **PDF**, atau **PPT**. Laporan menggunakan wrap text agar keterangan panjang tetap rapi.

Endpoint:

```text
GET /api/data-quality?period=ALL
GET /api/data-quality/detail?category=duplicate_asset&period=ALL
GET /api/data-quality/export?category=duplicate_asset&period=ALL
```

Kategori endpoint:

```text
duplicate_asset
missing_asset_number
empty_area
empty_location
empty_type
empty_user
not_opnamed
empty_documentation
damaged_without_notes
completed_opname
damaged_with_notes
```

Format export:

```text
GET /api/data-quality/export?category=damaged_with_notes&period=JAN-JUN&format=XLSX
GET /api/data-quality/export?category=damaged_with_notes&period=JAN-JUN&format=PDF
GET /api/data-quality/export?category=damaged_with_notes&period=JAN-JUN&format=PPTX
```

Download semua kategori dalam satu laporan untuk periode terpilih:

```text
GET /api/data-quality/export-all?period=JAN-JUN&format=XLSX
GET /api/data-quality/export-all?period=JAN-JUN&format=PDF
GET /api/data-quality/export-all?period=JAN-JUN&format=PPTX
```

Laporan gabungan PDF dan PPT berisi ringkasan jumlah seluruh kategori serta detail tiap kategori.

## Deploy Railway

Tambahkan variables:

```text
GOOGLE_SHEET_ID=ID spreadsheet
GOOGLE_SERVICE_ACCOUNT_JSON=seluruh JSON Service Account dalam satu baris
SETUP_TOKEN=token rahasia
APP_SECRET_KEY=rangkaian acak panjang
APP_TIMEZONE=Asia/Jakarta
PHOTO_UPLOAD_SCRIPT_URL=https://script.google.com/macros/s/DEPLOYMENT_ID/exec
PHOTO_UPLOAD_SECRET=secret-upload-foto-yang-panjang
```

Service Account wajib dibagikan sebagai **Editor** pada Google Spreadsheet.
Service Account tidak memerlukan akses Google Drive karena upload foto dilakukan oleh Google Apps Script sebagai akun owner.

## Deploy Google Apps Script Upload Relay

1. Buka [Google Apps Script](https://script.google.com/) memakai akun owner folder Drive.
2. Buat project baru.
3. Salin seluruh isi `apps-script/Code.gs` ke file `Code.gs`.
4. Buka **Project Settings** dan tambahkan Script Properties:

```text
PHOTO_FOLDER_ID=ID folder utama Google Drive owner
PHOTO_UPLOAD_SECRET=secret yang sama dengan variable Railway
```

5. Atur timezone project ke `Asia/Jakarta`.
6. Jalankan fungsi `createDailyCleanupTrigger` satu kali dari editor dan izinkan akses Drive. Ini memasang cleanup otomatis harian.
7. Klik **Deploy > New deployment > Web app**.
8. Pilih **Execute as: Me**.
9. Pilih **Who has access: Anyone**.
10. Deploy, izinkan akses, lalu salin URL `/exec` ke `PHOTO_UPLOAD_SCRIPT_URL` Railway.
11. Set `PHOTO_UPLOAD_SECRET` Railway dengan nilai yang sama, lalu redeploy Railway.

Foto opsional, dengan format JPG/PNG/WEBP dan ukuran maksimal 10 MB. Apps Script menyimpan foto menggunakan kuota Drive akun owner.

Tes upload relay setelah deploy:

```text
GET https://DOMAIN-RAILWAY-ANDA/api/test-photo-upload?token=SETUP_TOKEN
```

Endpoint mengirim gambar tes kecil dari Railway ke Apps Script. Apps Script membuat file, lalu langsung memindahkannya ke Trash.

## Auto Housekeeping Foto Drive

Apps Script selalu menyimpan foto pada subfolder periode berjalan di bawah folder `PHOTO_FOLDER_ID`:

```text
YYYY-Jan-Jun
YYYY-Jul-Des
```

Apps Script mempertahankan dua folder periode terbaru. Folder periode yang lebih lama otomatis dipindahkan ke Trash, bukan dihapus permanen. Folder lain yang namanya tidak mengikuti pola periode tidak disentuh.

Cleanup berjalan setiap upload dan melalui trigger harian Apps Script. Cleanup manual dari Railway:

```text
GET https://DOMAIN-RAILWAY-ANDA/api/cleanup-drive-photos?token=SETUP_TOKEN
```

Respons cleanup berisi periode yang dipertahankan, folder yang dipindahkan ke Trash, serta jumlah file/folder terdampak. Secret hanya dikirim server Railway ke Apps Script dan tidak pernah diberikan ke browser pengguna.

## Setup Header

Setelah deploy, jalankan:

```powershell
Invoke-RestMethod -Method Post `
  -Uri "https://DOMAIN-RAILWAY-ANDA/api/setup" `
  -Headers @{"X-Setup-Token"="TOKEN-RAHASIA-ANDA"}
```

`/api/setup` aman dijalankan berulang kali. Fungsi ini:

- Membuat sheet yang belum tersedia.
- Menambahkan header wajib yang belum tersedia.
- Tidak menghapus data existing.
- Tidak menimpa header atau data existing.

Setelah setup, pastikan header mengikuti struktur wajib. Header lama yang tidak digunakan boleh tetap ada sebagai kolom tambahan.

## Scanner HP

Gunakan domain Railway HTTPS. Izinkan kamera pada browser HP, lalu tekan **Scan QR dengan kamera** dan **Tangkap & Baca QR**. QR harus berisi `NOMOR ASSET`.

- Saat QR terbaca dari tayangan kamera, sistem otomatis menutup kamera dan mencari NOMOR ASSET tanpa menekan tombol Tangkap.
- Tombol **Tangkap & Baca QR** tetap tersedia sebagai cadangan jika QR sulit terbaca otomatis.
- Sistem meminta mode autofocus berkelanjutan ketika kamera mendukungnya.
- Ketuk area kamera untuk meminta fokus ulang ke QR.
- Gunakan tombol `−`, slider, atau tombol `+` untuk zoom out dan zoom in.
- Kontrol zoom hanya tampil jika kamera dan browser HP mendukung zoom.
- Dukungan tap-to-focus mengikuti kemampuan kamera dan browser HP.

## Edit Keterangan PIC

User dengan role `PIC ASET` atau `SUPER ADMIN, PIC ASET` melihat tombol pensil pada bagian **KETERANGAN TERAKHIR**.

Tekan tombol pensil untuk menyalin keterangan terakhir ke form opname, ubah teksnya, pilih kondisi aktual, lalu tekan **Simpan opname**. Perubahan tetap menggunakan alur submit opname yang sama agar `MASTER_ASET` dan `LOG_OPNAME` tetap sinkron.

## Upload dan Redeploy

1. Upload seluruh isi folder ini ke repository GitHub.
2. Commit dan push perubahan.
3. Railway akan redeploy otomatis.
4. Jalankan `/api/setup`.
5. Refresh web app dan login kembali.

## Pengujian

```bash
python -m unittest discover -s tests
```
