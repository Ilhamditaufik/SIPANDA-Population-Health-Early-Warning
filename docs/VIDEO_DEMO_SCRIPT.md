# Naskah video demonstrasi SIPANDA (3–4 menit)

## Persiapan

- Gunakan data sintetis yang memang ditandai `Simulasi`.
- Pastikan tidak ada username pribadi, email, nomor telepon, secret, atau data kesehatan nyata terlihat.
- Gunakan resolusi layar 1920×1080 atau 1280×720, zoom browser 90–100%, dan mikrofon yang jelas.
- Buka halaman `/demo` untuk awal video. Untuk fitur pengelolaan, rekam dashboard lokal/protected app setelah login dengan akun demo.

## Storyboard

**0:00–0:20 — Masalah dan tujuan**

"SIPANDA adalah prototipe sistem peringatan dini untuk membantu pemantauan kesehatan populasi dan tenaga kerja. Tujuannya menyatukan sinyal agregat agar petugas dapat melihat pola yang tidak biasa lebih awal dan melakukan verifikasi."

**0:20–0:55 — Dashboard**

Tampilkan ringkasan laporan populasi/tenaga kerja, tren tujuh hari, dan peringatan. Tegaskan bahwa contoh menggunakan data simulasi.

**0:55–1:35 — Multi-source signals**

Tampilkan laporan kesehatan, lalu halaman Sinyal Multi-sumber. Jelaskan bahwa pengamatan lingkungan (suhu/AQI) dan tenaga kerja (absensi/insiden) dimasukkan sebagai data agregat dengan sumber dan tanggal yang jelas.

**1:35–2:20 — Deteksi anomali yang dapat dijelaskan**

Tampilkan Peringatan Dini. Jelaskan Isolation Forest sebagai model unsupervised untuk menandai pola tidak biasa saat observasi cukup, serta robust z-score/baseline 28 hari sebagai penjelasan indikator yang menyumbang. Tampilkan bahwa alert multi-sumber perlu diverifikasi manusia.

**2:20–3:05 — Peta risiko dan PIC**

Tampilkan Peta Risiko, marker wilayah, label data simulasi, profil PIC, lalu contoh tindakan pencegahan. Tunjukkan penetapan PIC, tenggat, dan perubahan status.

**3:05–3:30 — Batasan dan roadmap**

"Ini masih prototipe. Data demonstrasi sintetis, koordinat peta ilustratif, dan model belum divalidasi klinis/epidemiologis. Tahap berikutnya adalah pengujian dengan data sah, peninjauan ahli kesehatan masyarakat/K3, evaluasi false alarm dan missed signal, serta penilaian privasi dan keamanan sebelum pilot."

## Checklist sebelum mengunggah video

- [ ] Semua layar terbaca dan tidak ada data pribadi.
- [ ] Tanda `DATA SIMULASI` terlihat.
- [ ] Tidak menyebut alert sebagai diagnosis atau kepastian risiko.
- [ ] Perlihatkan tiga masukan reviewer dan fitur yang menjawabnya.
- [ ] Sertakan caption/subtitle bahasa Inggris bila memungkinkan.
- [ ] Video benar-benar direkam dan diputar ulang untuk memeriksa suara, transisi, serta durasinya.
