# Pemetaan perbaikan terhadap masukan reviewer

| Masukan reviewer | Perubahan pada prototipe | Bukti yang dapat didemonstrasikan | Batasan yang perlu disampaikan |
|---|---|---|---|
| Tautan prototipe langsung dan video demonstrasi lebih jelas | Showcase publik baca-saja `/demo`, instruksi deployment, dan naskah video | Buka `/demo` tanpa login; rekam alur aplikasi terproteksi untuk memperlihatkan proses input dan pengelolaan | URL publik belum tersedia sampai aplikasi di-deploy oleh pemilik; belum ada video rekaman aktual di paket ini |
| Kembangkan threshold menjadi deteksi anomali AI multi-sumber dinamis | Integrasi laporan kesehatan, data lingkungan, dan data tenaga kerja; Isolation Forest unsupervised saat data mencukupi; robust rolling z-score untuk penjelasan | Tambah sinyal lingkungan dan tenaga kerja, buka Peringatan Dini, tunjukkan indikator, nilai, baseline, skor z, sumber, dan label multi-sumber | Ini model prototipe. Belum divalidasi pada dataset representatif, tidak membuktikan sebab-akibat, dan bukan prediksi/diagnosis klinis |
| Tambahkan peta risiko visual dan tindakan pencegahan dengan pemilik yang ditunjuk | Peta Leaflet/OpenStreetMap, profil wilayah dengan centroid dan PIC, daftar tindakan dengan PIC, tenggat, dan status | Buka Peta Risiko, tampilkan marker dan tabel, buat tindak lanjut, tetapkan PIC, ubah status | Koordinat demo bersifat ilustratif; tindakan hanya saran verifikasi umum dan harus mengikuti SOP serta otoritas setempat |

## Klaim yang aman untuk presentasi

"SIPANDA adalah prototipe pemantauan agregat multi-sumber yang menggunakan Isolation Forest untuk menandai pola tidak biasa ketika data mencukupi, lalu menampilkan metrik penyumbang melalui baseline statistik yang transparan. Sistem menyediakan peta titik pusat wilayah dan pencatatan tindak lanjut dengan PIC. Semua alert memerlukan verifikasi manusia dan belum divalidasi untuk keputusan klinis atau operasional."

Jangan mengklaim integrasi otomatis sensor, validasi klinis, akurasi prediksi, pengurangan penyakit, atau kesiapan produksi.
