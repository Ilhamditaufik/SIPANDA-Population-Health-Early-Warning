# Deployment halaman demo publik

## Tujuan

Menyediakan URL yang dapat dibuka reviewer tanpa memberikan akses anonim ke data operasional. Setelah deployment, URL yang dibagikan adalah `https://<domain-anda>/demo`.

## Prinsip keamanan

1. Buat database deployment khusus demo yang hanya berisi record sintetis. Jangan mengunggah `instance/sipanda.db` lokal.
2. Atur `SECRET_KEY` melalui environment/secret manager, bukan file yang di-commit.
3. Gunakan HTTPS dan set `COOKIE_SECURE=true`.
4. Atur `LOAD_DEMO_DATA=true` hanya pada database demo.
5. Gunakan PostgreSQL dan storage bersama seperti Redis untuk rate limiter jika ada lebih dari satu worker.
6. Atur `DATABASE_URL`, `SECRET_KEY`, `COOKIE_SECURE`, `LOAD_DEMO_DATA`, dan `RATELIMIT_STORAGE_URI` pada dashboard platform.
7. Build command: `pip install -r requirements.txt`.
8. Start command: `gunicorn app:app --workers 2 --timeout 60` (Procfile tersedia).
9. Buat admin demo dengan password kuat melalui `/setup`; jangan tampilkan kredensial di video publik.
10. Uji `/demo` tanpa login dan pastikan hanya data simulasi yang tampil. Uji juga bahwa `/`, `/laporan`, `/sinyal`, `/pengguna`, dan `/peta-risiko` tetap memerlukan login.

## Catatan

Paket ini menyiapkan aplikasi untuk deployment, tetapi belum membuat akun hosting, domain, database cloud, atau URL publik. Pemilik proyek harus melakukan deployment pada akun hosting yang dikuasainya dan memeriksa biaya/ketentuan platform. Halaman peta menggunakan tile OpenStreetMap dan memerlukan akses internet browser.
