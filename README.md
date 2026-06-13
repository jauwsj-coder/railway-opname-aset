# Web App Opname Aset Railway

## Header Wajib

`ROLE`

```text
NAMA USER | ID USER | ROLE | AREA
```

Role valid: `SUPER ADMIN`, `SUPER ADMIN, PIC ASET`, dan `PIC ASET`.

- `SUPER ADMIN` tidak masuk Score Card.
- `SUPER ADMIN, PIC ASET` masuk Score Card.
- `PIC ASET` masuk Score Card dan hanya mengakses AREA yang ditugaskan.
- `AREA = ALL` memberikan akses seluruh area.
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

`LOG_OPNAME` adalah sumber utama riwayat, status dashboard, kondisi terakhir, dan Score Card.

Saat submit berhasil:

- Header wajib `LOG_OPNAME` yang belum ada ditambahkan otomatis tanpa menghapus data.
- Baris `LOG_OPNAME` ditulis terlebih dahulu, baru `MASTER_ASET` diperbarui.
- `MASTER_ASET.OPNAME` menjadi `DONE`.
- `MASTER_ASET.KONDISI` dan `KONDISI TERAKHIR` mengikuti kondisi opname terbaru.
- `STATUS TERAKHIR` menjadi `SUDAH OPNAME JANUARI - JUNI` atau `SUDAH OPNAME JULI - DESEMBER` sesuai tanggal aktual.
- Foto dokumentasi diunggah ke Google Drive dan URL disimpan pada `DOKUMENTASI TERAKHIR`.
- Web kembali ke menu scan setelah penyimpanan berhasil.

## Perhitungan Dashboard

- Total aset: jumlah aset pada `MASTER_ASET` sesuai akses AREA.
- Sudah opname: jumlah `NOMOR ASSET` unik pada `LOG_OPNAME`.
- Belum opname: total aset dikurangi sudah opname.
- Aset baik: kondisi log terbaru bernilai `OK`, `BAIK`, atau `GOOD`.
- Aset rusak: kondisi log terbaru bernilai `RUSAK`, `BROKEN`, `MAINTENANCE`, atau `NOT OK`.
- Menghapus isi `LOG_OPNAME` akan mengubah dashboard dan Score Card pada refresh berikutnya.
- Sheet `DASHBOARD` hanya salinan tampilan, bukan sumber data.
- Filter tanggal awal/akhir hanya memfilter data opname dari `LOG_OPNAME`.
- Total aset tetap berasal dari `MASTER_ASET` dan tidak berubah ketika periode dipilih.
- Jika header `LOG_OPNAME` belum lengkap, Total Aset dan Belum Opname tetap tampil dari `MASTER_ASET`; metrik berbasis log menjadi nol dan web menampilkan peringatan.
- Pencarian aset dan form opname tetap tampil dari `MASTER_ASET` ketika header log belum lengkap. Riwayat menampilkan peringatan terpisah.
- Submit opname tetap membutuhkan seluruh header `LOG_OPNAME`; jalankan `/api/setup` untuk melengkapinya.

## Deploy Railway

Tambahkan variables:

```text
GOOGLE_SHEET_ID=ID spreadsheet
GOOGLE_SERVICE_ACCOUNT_JSON=seluruh JSON Service Account dalam satu baris
SETUP_TOKEN=token rahasia
APP_SECRET_KEY=rangkaian acak panjang
APP_TIMEZONE=Asia/Jakarta
GOOGLE_DRIVE_PHOTO_FOLDER_ID=1FJKbL7ZniWiR1vHRzKnC7_v1vaKWK5wv
```

Service Account wajib dibagikan sebagai **Editor** pada Google Spreadsheet.
Bagikan juga folder Google Drive dokumentasi sebagai **Editor** kepada email Service Account. Folder default:

```text
https://drive.google.com/drive/folders/1FJKbL7ZniWiR1vHRzKnC7_v1vaKWK5wv
```

Foto dokumentasi wajib dipilih saat opname, dengan format JPG/PNG/WEBP dan ukuran maksimal 10 MB.

## Auto Housekeeping Foto Drive

Foto selalu disimpan pada subfolder periode berjalan di bawah `GOOGLE_DRIVE_PHOTO_FOLDER_ID`:

```text
YYYY-Jan-Jun
YYYY-Jul-Des
```

Sistem mempertahankan dua folder periode terbaru. Folder periode yang lebih lama otomatis dipindahkan ke Trash, bukan dihapus permanen. Folder lain yang namanya tidak mengikuti pola periode tidak disentuh.

Cleanup otomatis dijalankan satu kali sehari selama aplikasi Railway aktif. Cleanup manual:

```text
GET https://DOMAIN-RAILWAY-ANDA/api/cleanup-drive-photos?token=SETUP_TOKEN
```

Respons cleanup berisi periode yang dipertahankan, folder yang dipindahkan ke Trash, serta jumlah file/folder terdampak.

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
