# Panduan Apps Script Fasilitas Aset

Script ini hanya berjalan pada Google Sheets dan tidak mengubah web app Railway.

## Pemasangan

1. Buka spreadsheet database aset.
2. Pilih **Extensions > Apps Script**.
3. Buat project Apps Script yang terikat pada spreadsheet tersebut.
4. Buka file `Code.gs`, hapus contoh kode bawaan, lalu paste seluruh isi file `apps-script-fasilitas/Code.gs`.
5. Klik **Save**.
6. Pilih fungsi `onOpen`, lalu klik **Run** satu kali.
7. Berikan izin akses Google Sheets saat diminta.
8. Kembali ke Google Sheets dan refresh halaman.
9. Menu **Fasilitas Aset** akan tampil.
10. Jalankan **Fasilitas Aset > Setup Sheet Fasilitas**.

`Setup Sheet Fasilitas` membuat atau melengkapi sheet `ASET_RUSAK`, `ASET_DISPOSAL`, dan `LOG_FASILITAS_ASET` tanpa menghapus data existing.

## Cara Penggunaan

1. Jalankan **Sync Aset Rusak** untuk menyalin aset rusak dari `MASTER_ASET` ke `ASET_RUSAK`.
2. Isi `STATUS PERBAIKAN`, `PIC FOLLOW UP`, `CATATAN PERBAIKAN`, dan `DOKUMENTASI PERBAIKAN`.
3. Jalankan **Proses Update Perbaikan**.
4. Untuk aset yang masuk disposal, lengkapi data pada `ASET_DISPOSAL`, lalu ubah `STATUS DISPOSAL`.
5. Jalankan **Proses Disposal**.
6. Gunakan **Refresh Semua** untuk menjalankan setup, sync, proses perbaikan, dan proses disposal sekaligus.

## Nilai Status Yang Diproses

- `STATUS PERBAIKAN`: `SELESAI DIPERBAIKI` atau `TIDAK BISA DIPERBAIKI`.
- `STATUS DISPOSAL`: `SELESAI DISPOSAL` atau `BATAL DISPOSAL`.

Script membaca kolom berdasarkan nama header, mencegah duplikat `NOMOR ASSET`, dan tidak menambahkan log yang sama ketika kondisi akhir di `MASTER_ASET` sudah sesuai.
