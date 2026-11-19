@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo [1/3] Membuat virtual environment...
  py -m venv .venv
  if errorlevel 1 goto :error
)
if not exist .env (
  echo [2/3] Membuat konfigurasi lokal dan SECRET_KEY acak...
  .venv\Scripts\python.exe -c "from pathlib import Path; import secrets; Path('.env').write_text('SECRET_KEY='+secrets.token_hex(32)+'\nDATABASE_URL=sqlite:///sipanda.db\nLOAD_DEMO_DATA=true\nFLASK_DEBUG=false\nCOOKIE_SECURE=false\nRATELIMIT_STORAGE_URI=memory://\n', encoding='utf-8')"
  if errorlevel 1 goto :error
)
if not exist .venv\sipanda_requirements_installed.marker (
  echo [3/3] Memasang dependensi yang diperlukan untuk pertama kali...
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto :error
  echo installed> .venv\sipanda_requirements_installed.marker
) else (
  echo Dependensi sudah terpasang. Hapus marker di .venv jika requirements berubah.
)
echo Menjalankan SIPANDA di http://127.0.0.1:5000
.venv\Scripts\python.exe app.py
goto :eof
:error
echo Terjadi kesalahan. Pastikan Python Launcher (py) tersedia dan koneksi internet aktif saat instalasi dependensi.
pause
