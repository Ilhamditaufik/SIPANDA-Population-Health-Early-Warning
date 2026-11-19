
"""Gemini AI service for SIPANDA risk insights.

Gemini explains aggregate anomaly findings.
It does not diagnose disease or determine an outbreak.
"""

import os
import json
from pathlib import Path

from dotenv import load_dotenv
from google import genai


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=False)


def generate_risk_insights(alerts, model=None):
    """Generate an explanation from sanitized aggregate anomaly findings."""

    api_key = os.getenv("GEMINI_API_KEY")
    model_name = model or os.getenv(
        "GEMINI_MODEL",
        "gemini-2.5-flash",
    )

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY tidak ditemukan. Periksa file .env."
        )

    if not alerts:
        return (
            "Belum terdapat temuan anomali yang dapat dianalisis. "
            "Silakan periksa kembali data dan periode pemantauan."
        )

    # Allowlist fields: do not send personal data, notes, usernames,
    # PIC names, credentials, or individual-level information.
    safe_alerts = []

    for alert in alerts[:10]:
        safe_alerts.append({
            "region": str(alert.get("region", ""))[:100],
            "date": str(alert.get("date", ""))[:20],
            "level": str(alert.get("level", ""))[:30],
            "risk_score": alert.get("risk_score"),
            "sources": [
                str(item)[:60]
                for item in (alert.get("sources") or [])[:10]
            ],
            "drivers": [
                str(item)[:300]
                for item in (alert.get("drivers") or [])[:10]
            ],
            "recommendations": [
                str(item)[:300]
                for item in (alert.get("recommendations") or [])[:10]
            ],
            "detection_method": str(
                alert.get("detection_method", "")
            )[:100],
        })

    prompt = f"""
Kamu adalah asisten analisis SIPANDA
(Sistem Peringatan Dini Kesehatan Populasi dan Tenaga Kerja).

Tugasmu adalah membantu petugas memahami hasil deteksi anomali
berdasarkan data agregat yang diberikan.

DATA TEMUAN:
{json.dumps(safe_alerts, ensure_ascii=False, indent=2)}

Buat laporan dalam bahasa Indonesia dengan struktur:

1. RINGKASAN TEMUAN
Jelaskan kondisi yang terdeteksi secara singkat.

2. FAKTOR YANG PERLU DIPERHATIKAN
Jelaskan indikator dan sumber data yang berkontribusi.

3. REKOMENDASI VERIFIKASI
Berikan langkah pemeriksaan data dan tindak lanjut
yang realistis bagi petugas.

4. PRIORITAS TINDAKAN
Jelaskan temuan mana yang perlu diperiksa lebih dahulu
berdasarkan tingkat risiko yang tersedia.

ATURAN PENTING:
- Jangan membuat angka atau fakta yang tidak tersedia.
- Jangan menyimpulkan diagnosis penyakit.
- Jangan menyatakan bahwa wabah telah terjadi.
- Jangan menganggap korelasi sebagai hubungan sebab-akibat.
- Jangan mengubah hasil atau skor deteksi asli.
- Bedakan hasil algoritma dengan interpretasi AI.
- Semua rekomendasi harus diverifikasi manusia.
- Jika data simulasi, nyatakan bahwa hasilnya simulasi.
- Gunakan bahasa profesional, jelas, dan ringkas.
"""

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
    )

    result = getattr(response, "text", None)

    if not result or not result.strip():
        raise RuntimeError(
            "Gemini tidak menghasilkan teks analisis."
        )

    return result.strip()
