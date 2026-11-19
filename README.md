# SIPANDA — Sistem Peringatan Dini Kesehatan Populasi dan Tenaga Kerja

**Status:** prototipe demonstrasi. Bukan perangkat diagnosis, bukan sistem surveilans tervalidasi, dan belum siap untuk keputusan klinis atau operasional.

SIPANDA menggabungkan laporan kesehatan agregat, sinyal lingkungan, dan sinyal tenaga kerja untuk membantu petugas meninjau pola yang tidak biasa. Aplikasi menampilkan penjelasan indikator yang berkontribusi, peta risiko berbasis titik pusat wilayah, dan daftar tindakan dengan PIC yang ditetapkan pengguna.

## Pembaruan berdasarkan masukan reviewer

1. **Akses prototipe dan demonstrasi:** tersedia halaman showcase baca-saja di `/demo` yang hanya membaca record berlabel simulasi. Panduan video dan deployment berada di `docs/`.
2. **Deteksi anomali multi-sumber:** laporan kesehatan dipadukan dengan suhu/indeks kualitas udara dan indikator tenaga kerja. Isolation Forest dipakai jika tersedia cukup observasi lintas sumber; robust rolling z-score menjelaskan metrik yang menyimpang. Jika data belum cukup, aplikasi menyatakan keterbatasan dan memakai fallback statistik.
3. **Peta risiko dan tindakan:** Leaflet/OpenStreetMap menampilkan titik pusat wilayah agregat. Admin dapat memasukkan koordinat centroid dan PIC wilayah. Pengguna terautentikasi dapat membuat tindak lanjut, menetapkan PIC, batas waktu, dan status.

## Fitur utama

- Autentikasi Admin/Petugas, hash kata sandi, CSRF, pembatasan login, sesi terbatas, dan header keamanan dasar.
- Dashboard populasi dan tenaga kerja.
- Input laporan kesehatan agregat, riwayat, filter, dan ekspor CSV yang menetralkan formula berbahaya.
- Input pengamatan lingkungan dan tenaga kerja.
- Deteksi pola tidak biasa multi-sumber dengan baseline bergulir dan model Isolation Forest unsupervised saat data memadai.
- Penjelasan indikator penyumbang anomali, baseline pembanding, sumber data, dan skor prototipe.
- Peta risiko berdasarkan koordinat titik pusat wilayah, bukan koordinat individu.
- Penetapan tindakan, PIC, batas waktu, dan status tindak lanjut.
- Showcase publik `/demo` yang hanya menampilkan data sintetis.

## Teknologi

- Python, Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF, Flask-Limiter
- SQLite untuk lokal; PostgreSQL dapat digunakan melalui `DATABASE_URL`
- scikit-learn IsolationForest untuk deteksi anomali unsupervised
- Leaflet dan OpenStreetMap untuk visualisasi peta; memerlukan koneksi internet pada browser
- Chart.js untuk grafik dashboard

## Cara menjalankan di Windows

1. Ekstrak proyek ke folder kerja baru, atau salin file kode ke folder proyek lama setelah membuat backup database dan `.env`.
2. Pastikan Python tersedia. Jalankan `START_SIPANDA.bat`. Script membuat `.venv` dan `.env` lokal jika belum ada, menghasilkan `SECRET_KEY` acak, memasang dependensi, lalu menjalankan Flask.
3. Buka `http://127.0.0.1:5000`.
4. Pada database baru, aplikasi mengarahkan ke `/setup` untuk membuat Admin pertama. Pada database lama, gunakan akun yang sudah ada.
5. Showcase baca-saja dapat dibuka di `http://127.0.0.1:5000/demo`.

Alternatif manual PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
# Isi SECRET_KEY di .env dengan output acak di atas, lalu:
python app.py
```

Jangan memakai nilai placeholder `SECRET_KEY`. Jangan pernah mengirim file `.env` kepada reviewer atau mengunggahnya ke Git.

## Memperbarui database lama dengan aman

- Hentikan server Flask terlebih dahulu.
- Buat salinan cadangan `instance/sipanda.db` dan `.env`.
- Salin file kode/template/static dari rilis ini ke folder proyek lama; jangan menghapus `instance/sipanda.db`.
- `db.create_all()` menambahkan tabel baru (`signal_observations`, `region_profiles`, `action_assignments`) tanpa menghapus tabel lama. Perubahan kolom pada tabel lama tidak dilakukan oleh paket ini.
- Karena file `.env` dari arsip awal pernah dibagikan, buat `SECRET_KEY` baru. Ini akan mengakhiri sesi login yang lama, tetapi tidak mengubah password/hash akun atau isi database.
- Saat pertama dijalankan dengan `LOAD_DEMO_DATA=true`, aplikasi menambahkan data sintetis berlabel `demo_record=true` untuk fitur demonstrasi. Data asli tidak dihapus atau diubah. Data sintetis tetap muncul di beberapa ringkasan internal tetapi selalu diberi label Simulasi; untuk hosting publik, gunakan database demo terpisah.

## Cara menggunakan fitur reviewer

1. **Sinyal Multi-sumber:** buka menu `Sinyal Multi-sumber` dan tambahkan data agregat lingkungan/tenaga kerja. Laporan kesehatan yang sudah dicatat menjadi sumber layanan kesehatan.
2. **Peringatan Dini:** buka menu tersebut untuk melihat wilayah yang memiliki metrik menyimpang, nilai pengamatan, baseline, robust z-score, dan apakah model Isolation Forest menandai region-day tersebut.
3. **Peta Risiko:** buka `Peta Risiko & Tindakan`. Admin dapat mendaftarkan centroid wilayah dan PIC. Gunakan titik pusat agregat, jangan masukkan alamat rumah atau koordinat individu.
4. **Tindak lanjut:** buat tindakan, isi PIC serta perannya, tentukan batas waktu, dan perbarui statusnya.
5. **Demo Publik:** bagikan URL domain-deployment + `/demo`. Halaman ini hanya memperlihatkan record sintetis yang ditandai demo; halaman tidak membuka akun maupun laporan privat.

## Interpretasi model dan batasan

- Isolation Forest merupakan metode unsupervised untuk menandai observasi yang tampak berbeda dari pola data yang dianalisis. Ia tidak membuktikan kejadian kesehatan, penyebab, wabah, atau hubungan sebab-akibat.
- Robust z-score memakai median dan median absolute deviation (MAD) pada jendela historis hingga 28 hari per wilayah/indikator. Nilai z membantu menjelaskan penyimpangan, bukan menetapkan ambang klinis.
- Label `Tinggi`/`Waspada` adalah prioritas tinjauan prototipe, bukan tingkat bahaya medis.
- Analisis membutuhkan riwayat yang memadai. Data sedikit, tidak lengkap, tidak representatif, atau sumber yang tidak selaras dapat menghasilkan false alarm maupun missed signal.
- Demonstrasi memuat koordinat wilayah ilustratif dan data sintetis; jangan menafsirkannya sebagai kondisi atau lokasi aktual.
- Rekomendasi tindakan merupakan prompt verifikasi umum. Setiap tindakan nyata harus ditetapkan tenaga berwenang sesuai SOP dan konteks lokal.
- Tidak ada integrasi sensor otomatis pada rilis ini. Sinyal lingkungan/tenaga kerja dimasukkan sebagai ringkasan agregat oleh pengguna yang terautentikasi.

## Akses publik dan deployment

Halaman `/demo` adalah showcase publik baca-saja dan bukan akses terbuka ke dashboard operasional. Untuk publikasi:

- Gunakan host HTTPS, PostgreSQL, `SECRET_KEY` baru dari environment/secret manager, `COOKIE_SECURE=true`, dan `RATELIMIT_STORAGE_URI` berbasis Redis atau penyimpanan bersama.
- Jangan deploy dengan database pribadi yang berisi akun/laporan sebenarnya. Gunakan database demo terpisah berisi data sintetis.
- Jalankan aplikasi WSGI menggunakan Gunicorn (Procfile tersedia untuk platform Linux yang mendukungnya).
- Atur backup, logging, monitoring, retensi, penghapusan, akses minimum, penilaian privasi, dan uji keamanan sebelum penggunaan nyata.
- Peta menggunakan tile OpenStreetMap melalui internet dan memerlukan atribusi pada tampilan.

Lihat `docs/DEPLOYMENT_PUBLIC_DEMO.md` dan `docs/VIDEO_DEMO_SCRIPT.md`.

## Pengujian

```powershell
python -m unittest discover -s tests -v
```

Pengujian yang disediakan memeriksa fungsi analitik dan rute demo/otorisasi dasar. Ini bukan pengganti penetration test, validasi eksternal, uji klinis, atau evaluasi oleh ahli kesehatan masyarakat/K3.
