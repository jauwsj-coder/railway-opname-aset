# Panduan Sheet Score Board

Score Board menampilkan progress penyelesaian stock opname setiap PIC ASET. Sistem tidak menggunakan poin berbobot atau penalti.

## 1. Sheet yang Digunakan

Score Board membaca data dari tiga sheet:

- `ROLE`: menentukan PIC dan area penilaian.
- `MASTER_ASET`: menentukan target total aset pada setiap area.
- `LOG_OPNAME`: menentukan aset yang sudah diopname pada periode terpilih.

Hasil Sync Sheet ditulis ke sheet `DASHBOARD`. Sheet tersebut adalah salinan hasil perhitungan, bukan sumber utama data.

## 2. Pengaturan Sheet ROLE

Gunakan header:

```text
NAMA USER | ID USER | ROLE | AREA | AREA SCORECARD
```

Arti kolom:

| Kolom | Kegunaan |
|---|---|
| NAMA USER | Nama petugas yang digunakan saat login dan ditampilkan pada Score Board. |
| ID USER | ID petugas yang wajib cocok saat login. |
| ROLE | Gunakan `SUPER ADMIN`, `SUPER ADMIN, PIC ASET`, atau `PIC ASET`. |
| AREA | Area yang boleh diakses, dicari, dan diproses oleh user. |
| AREA SCORECARD | Area yang menjadi target penilaian Score Board. Jika kosong, sistem menggunakan AREA. |

Contoh:

```text
NAMA USER | ID USER | ROLE                  | AREA                 | AREA SCORECARD
GA ADMIN  | 1001    | SUPER ADMIN           | ALL                  |
BUDI      | 1002    | PIC ASET              | GRAMERCY             |
SARI      | 1003    | PIC ASET              | FB, CARPOOL           | FB, CARPOOL
NIRWAN    | 1004    | SUPER ADMIN, PIC ASET | ALL                  | SYNERGY_LT.UG
```

Aturan penting:

- Pisahkan multi-area menggunakan koma.
- `AREA = ALL` memberikan akses ke seluruh area.
- `SUPER ADMIN` tidak mempunyai baris Score Board.
- `SUPER ADMIN, PIC ASET` dan `PIC ASET` mempunyai baris Score Board.
- Nama area harus sama dengan nilai kolom `AREA` pada `MASTER_ASET` dan `LOG_OPNAME`.

## 3. Cara Perhitungan

Untuk setiap PIC:

```text
Total Aset   = NOMOR ASSET unik di MASTER_ASET sesuai AREA SCORECARD
Sudah Opname = NOMOR ASSET unik di LOG_OPNAME sesuai AREA SCORECARD dan periode
Belum Opname = Total Aset - Sudah Opname
Progress %   = Sudah Opname / Total Aset x 100
```

Jika satu aset diopname lebih dari sekali pada periode yang sama, aset tersebut tetap dihitung satu kali.

Dokumentasi Ada, Keterangan Ada, Aset Baik, dan Aset Rusak hanya informasi tambahan. Data tersebut tidak menambah atau mengurangi Progress.

## 4. Status Progress

| Progress | Status |
|---|---|
| 100% | Selesai |
| 90% sampai kurang dari 100% | Hampir Selesai |
| 75% sampai kurang dari 90% | On Track |
| 50% sampai kurang dari 75% | Dalam Proses |
| Lebih dari 0% sampai kurang dari 50% | Perlu Dukungan |
| 0% | Belum Mulai |

## 5. Pilihan Periode

Pada menu **Score Board**, pilih salah satu periode:

- **Jan-Jun Tahun Berjalan**: menggunakan log tanggal 1 Januari sampai 30 Juni tahun berjalan.
- **Jul-Des Tahun Berjalan**: menggunakan log tanggal 1 Juli sampai 31 Desember tahun berjalan.
- **Semua Periode**: menggunakan seluruh data `LOG_OPNAME`.

Tekan **Tampilkan Progress** setelah memilih periode.

## 6. Sync ke Sheet DASHBOARD

Tombol **Sync Sheet** tersedia untuk SUPER ADMIN dengan akses `AREA = ALL`.

Langkah:

1. Buka menu **Score Board**.
2. Pilih periode.
3. Tekan **Tampilkan Progress**.
4. Tekan **Sync Sheet**.
5. Buka sheet `DASHBOARD` untuk melihat salinan hasil terbaru.

Sync Sheet akan menulis ringkasan dashboard dan tabel Score Board sesuai periode Score Board yang sedang dipilih.

## 7. Arti Kolom Hasil Score Board

| Kolom | Arti |
|---|---|
| NAMA PETUGAS | Nama PIC dari sheet ROLE. |
| ID USER | ID PIC dari sheet ROLE. |
| ROLE | Role PIC. |
| AREA SCORECARD | Area target penilaian. |
| TOTAL ASSET | Jumlah target aset unik. |
| SUDAH OPNAME | Jumlah aset unik yang sudah diopname. |
| BELUM OPNAME | Sisa aset yang belum diopname. |
| PROGRESS | Persentase penyelesaian. |
| STATUS | Status berdasarkan Progress. |
| DOKUMENTASI ADA | Jumlah aset dengan URL dokumentasi. |
| KETERANGAN ADA | Jumlah aset dengan keterangan. |
| ASET BAIK | Jumlah aset dengan kondisi terakhir baik. |
| ASET RUSAK | Jumlah aset dengan kondisi terakhir rusak. |

## 8. Jika Angka Tidak Sesuai

Periksa hal berikut:

1. Pastikan penulisan AREA sama pada `ROLE`, `MASTER_ASET`, dan `LOG_OPNAME`.
2. Pastikan `AREA SCORECARD` sudah benar atau dikosongkan agar memakai `AREA`.
3. Pastikan tanggal pada `LOG_OPNAME` masuk periode yang dipilih.
4. Pastikan `NOMOR ASSET` tersedia pada `MASTER_ASET`.
5. Jalankan `/api/setup` setelah penambahan header `AREA SCORECARD`.
6. Refresh web atau tekan **Sync Sheet** setelah perubahan data.
