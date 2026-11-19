# Catatan validasi lokal untuk rilis penyempurnaan reviewer

Pemeriksaan yang telah dijalankan pada salinan kerja:

- Sintaks Python (`app.py`, `analytics.py`, serta test) berhasil dikompilasi.
- Seluruh template Jinja (`about`, `alerts`, `base`, `dashboard`, `demo`, `login`, `reports`, `risk_map`, `setup`, `signals`, `users`) berhasil diparse.
- Enam pengujian unit/integrasi lulus: deteksi lonjakan lintas sumber, riwayat tidak cukup data, akses demo tanpa login, proteksi halaman privat, isolasi data demo dari data non-demo, input sinyal, penetapan PIC, serta pembatasan fungsi admin terhadap Petugas.
- Uji aplikasi menggunakan database sementara: halaman utama, laporan, sinyal, peringatan, peta risiko, dan tentang merespons HTTP 200 setelah login; halaman privat mengarahkan pengguna anonim ke login.
- Uji upgrade pada salinan database yang dikirim: akun dan laporan awal tetap ada setelah `db.create_all()` dan seeding demo. Tidak ada tabel lama yang dihapus atau diubah.
- Dataset sintetis menghasilkan contoh anomali multi-sumber untuk demonstrasi. Ini hanya membuktikan alur teknis bekerja pada data contoh, bukan akurasi pada data lapangan.

Belum dilakukan:

- Deployment ke domain/hosting publik dan uji tautan dari jaringan eksternal.
- Perekaman video demonstrasi aktual; paket hanya menyediakan storyboard/naskah.
- Uji penetrasi, audit keamanan independen, validasi klinis/epidemiologis, validasi ahli K3, dan pilot lapangan.
- Integrasi otomatis ke sensor, sistem rumah sakit, laboratorium, atau sistem absensi.

Sebelum membagikan tautan kepada reviewer, lakukan deployment pada database demo terpisah, uji semua halaman, dan rekam video sesuai `VIDEO_DEMO_SCRIPT.md`.
