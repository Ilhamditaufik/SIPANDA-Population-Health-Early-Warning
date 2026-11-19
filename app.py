import hmac
import os
import csv
import io
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file,
    session,
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
# Environment variables from the OS/deployment take precedence over .env.
load_dotenv(ENV_FILE, override=False)

from sqlalchemy.exc import SQLAlchemyError

from analytics import analyze_multisource
from gemini_service import generate_risk_insights


# ============================================================
# 1. KONFIGURASI APLIKASI
# ============================================================

app = Flask(__name__)

secret_key = os.getenv("SECRET_KEY")

if not secret_key:
    raise RuntimeError(
        f"SECRET_KEY belum terbaca. Pastikan file .env ada di folder: {BASE_DIR} "
        "dan baris pertamanya berbentuk SECRET_KEY=nilai_kunci_rahasia. "
        f"File .env ditemukan: {ENV_FILE.is_file()}"
    )

app.config["SECRET_KEY"] = secret_key


app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL",
    "sqlite:///sipanda.db",
)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("COOKIE_SECURE", "false").lower() == "true"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)
app.config["WTF_CSRF_TIME_LIMIT"] = 3600

# Rate limiting: memory:// cukup untuk prototipe lokal. Untuk produksi,
# atur RATELIMIT_STORAGE_URI ke penyimpanan bersama seperti Redis.
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
    strategy="fixed-window",
    headers_enabled=True,
)

db = SQLAlchemy(app)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Silakan login untuk mengakses halaman tersebut."
login_manager.login_message_category = "error"


@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


@app.errorhandler(429)
def too_many_requests(error):
    # Rate limit saat ini diterapkan pada POST /login. Respons tetap memakai
    # template login agar pengguna memperoleh pesan yang mudah dipahami.
    if request.endpoint == "login":
        flash(
            "Terlalu banyak percobaan login. Tunggu satu menit sebelum mencoba kembali.",
            "error",
        )
        return render_template("login.html"), 429
    return "Terlalu banyak permintaan. Coba beberapa saat lagi.", 429


# ============================================================
# 2. DAFTAR PILIHAN YANG DIIZINKAN
# ============================================================

ALLOWED_INDICATORS = {
    "gejala_pernapasan",
    "demam",
    "batuk",
    "diare",
    "keluhan_panas",
    "kelelahan",
    "keluhan_pernapasan",
    "keluhan_kesehatan",
    "cedera_kerja",
    "keluhan_lainnya",
}

DOMAIN_LABELS = {
    "population": "Kesehatan populasi",
    "workforce": "Kesehatan tenaga kerja",
}

INDICATOR_LABELS = {
    "gejala_pernapasan": "Gejala pernapasan",
    "demam": "Demam",
    "batuk": "Batuk",
    "diare": "Diare",
    "keluhan_panas": "Keluhan terkait panas",
    "kelelahan": "Kelelahan",
    "keluhan_pernapasan": "Keluhan pernapasan tenaga kerja",
    "keluhan_kesehatan": "Keluhan kesehatan umum",
    "cedera_kerja": "Cedera kerja",
    "keluhan_lainnya": "Keluhan lain (agregat)",
}


# ============================================================
# MODEL PENGGUNA DAN LOGIN
# ============================================================

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="petugas")
    active = db.Column(db.Boolean, nullable=False, default=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        # Flask-Login memakai properti ini untuk status aktif akun.
        return bool(self.active)


@login_manager.user_loader
def load_user(user_id):
    try:
        user = db.session.get(User, int(user_id))
        # Akun yang dinonaktifkan tidak boleh mempertahankan sesi lama.
        if user is None or not user.active:
            return None
        return user
    except (TypeError, ValueError):
        return None


def admin_required(view):
    from functools import wraps
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != "admin":
            flash("Halaman ini hanya dapat diakses administrator.", "error")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped


# ============================================================
# 3. MODEL DATABASE
# ============================================================

class HealthReport(db.Model):
    __tablename__ = "health_reports"

    id = db.Column(db.Integer, primary_key=True)

    report_date = db.Column(
        db.Date,
        nullable=False,
        default=date.today,
        index=True,
    )

    domain = db.Column(
        db.String(20),
        nullable=False,
        index=True,
    )

    region = db.Column(
        db.String(100),
        nullable=False,
        index=True,
    )

    indicator = db.Column(
        db.String(50),
        nullable=False,
        index=True,
    )

    count = db.Column(
        db.Integer,
        nullable=False,
        default=1,
    )

    notes = db.Column(
        db.String(500),
        nullable=True,
    )

    demo_record = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )


class RegionProfile(db.Model):
    """Wilayah dengan titik pusat agregat dan penanggung jawab."""
    __tablename__ = "region_profiles"

    id = db.Column(db.Integer, primary_key=True)
    region = db.Column(db.String(100), unique=True, nullable=False, index=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    pic_name = db.Column(db.String(120), nullable=True)
    pic_role = db.Column(db.String(120), nullable=True)
    location_note = db.Column(db.String(240), nullable=True)
    demo_location = db.Column(db.Boolean, nullable=False, default=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class SignalObservation(db.Model):
    """Sinyal agregat tambahan dari lingkungan dan tenaga kerja."""
    __tablename__ = "signal_observations"

    id = db.Column(db.Integer, primary_key=True)
    observed_on = db.Column(db.Date, nullable=False, index=True)
    region = db.Column(db.String(100), nullable=False, index=True)
    source_type = db.Column(db.String(30), nullable=False, index=True)
    metric = db.Column(db.String(50), nullable=False, index=True)
    value = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(30), nullable=False)
    source_name = db.Column(db.String(120), nullable=False)
    notes = db.Column(db.String(300), nullable=True)
    demo_record = db.Column(db.Boolean, nullable=False, default=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class ActionAssignment(db.Model):
    """Tindak lanjut risiko dengan penanggung jawab (PIC) yang ditetapkan."""
    __tablename__ = "action_assignments"

    id = db.Column(db.Integer, primary_key=True)
    region = db.Column(db.String(100), nullable=False, index=True)
    finding_key = db.Column(db.String(120), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    recommended_action = db.Column(db.Text, nullable=False)
    assigned_to = db.Column(db.String(120), nullable=False)
    owner_role = db.Column(db.String(120), nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="open", index=True)
    notes = db.Column(db.String(500), nullable=True)
    demo_record = db.Column(db.Boolean, nullable=False, default=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


SIGNAL_METRICS = {
    "temperature_c": {"source": "environment", "label": "Suhu lingkungan", "unit": "°C", "min": -20, "max": 60},
    "air_quality_index": {"source": "environment", "label": "Indeks kualitas udara", "unit": "AQI", "min": 0, "max": 500},
    "absenteeism_rate": {"source": "workforce", "label": "Tingkat ketidakhadiran", "unit": "%", "min": 0, "max": 100},
    "workplace_incidents": {"source": "workforce", "label": "Insiden tempat kerja", "unit": "kejadian", "min": 0, "max": 10000},
}


def collect_anomaly_records(demo_only=False):
    """Satukan laporan kesehatan dan sinyal tambahan tanpa mengambil catatan pribadi."""
    cutoff = date.today() - timedelta(days=34)
    health_query = HealthReport.query.filter(
        HealthReport.report_date >= cutoff,
        HealthReport.report_date <= date.today(),
    )
    signal_query = SignalObservation.query.filter(
        SignalObservation.observed_on >= cutoff,
        SignalObservation.observed_on <= date.today(),
    )
    if demo_only:
        health_query = health_query.filter(HealthReport.demo_record.is_(True))
        signal_query = signal_query.filter(SignalObservation.demo_record.is_(True))

    records = []
    for report in health_query.all():
        records.append({
            "region": report.region,
            "observed_on": report.report_date,
            "metric": "health_reports",
            "value": report.count,
            "source_type": "Layanan kesehatan",
            "demo_record": report.demo_record,
        })
    for signal in signal_query.all():
        records.append({
            "region": signal.region,
            "observed_on": signal.observed_on,
            "metric": signal.metric,
            "value": signal.value,
            "source_type": "Lingkungan" if signal.source_type == "environment" else "Tenaga kerja",
            "demo_record": signal.demo_record,
        })
    return records


def build_risk_context(demo_only=True):
    analysis = analyze_multisource(collect_anomaly_records(demo_only=demo_only))
    profile_query = RegionProfile.query
    action_query = ActionAssignment.query
    if demo_only:
        profile_query = profile_query.filter(RegionProfile.demo_location.is_(True))
        action_query = action_query.filter(ActionAssignment.demo_record.is_(True))
    profiles = {item.region: item for item in profile_query.all()}
    risks = []
    map_points = []
    for risk in analysis["risks"]:
        profile = profiles.get(risk["region"])
        item = dict(risk)
        item["latitude"] = profile.latitude if profile else None
        item["longitude"] = profile.longitude if profile else None
        item["pic_name"] = profile.pic_name if profile else None
        item["pic_role"] = profile.pic_role if profile else None
        item["location_note"] = profile.location_note if profile else None
        if profile and profile.latitude is not None and profile.longitude is not None:
            map_points.append({
                "region": risk["region"],
                "lat": profile.latitude,
                "lng": profile.longitude,
                "level": risk["level"],
                "score": risk["risk_score"],
                "sources": risk["sources"],
                "pic": profile.pic_name or "Belum ditetapkan",
                "demo": bool(profile.demo_location),
            })
        risks.append(item)
    actions = action_query.order_by(ActionAssignment.created_at.desc()).limit(50).all()
    return analysis, risks, map_points, actions, profiles



# ============================================================
# 4. FUNGSI FILTER LAPORAN
# Digunakan bersama oleh halaman laporan dan ekspor CSV.
# ============================================================

def csv_safe_text(value):
    """Netralisasi teks berpotensi menjadi formula saat dibuka di spreadsheet."""
    text = "" if value is None else str(value)
    first_non_space = text.lstrip(" \t\r\n")
    if text.startswith(("\t", "\r", "\n")) or first_non_space.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def get_filtered_reports():
    query = HealthReport.query

    search = request.args.get("q", "").strip()
    domain = request.args.get("domain", "").strip()
    start_raw = request.args.get("start_date", "").strip()
    end_raw = request.args.get("end_date", "").strip()

    start_date = None
    end_date = None
    filter_error = None

    if domain in DOMAIN_LABELS:
        query = query.filter(HealthReport.domain == domain)
    else:
        domain = ""

    if search:
        query = query.filter(
            HealthReport.region.ilike(f"%{search}%")
        )

    try:
        if start_raw:
            start_date = date.fromisoformat(start_raw)

        if end_raw:
            end_date = date.fromisoformat(end_raw)

        if start_date and end_date and start_date > end_date:
            filter_error = (
                "Tanggal mulai tidak boleh melewati tanggal akhir."
            )
            start_date = None
            end_date = None
            start_raw = ""
            end_raw = ""

    except ValueError:
        filter_error = "Format tanggal filter tidak valid."
        start_date = None
        end_date = None
        start_raw = ""
        end_raw = ""

    if start_date:
        query = query.filter(
            HealthReport.report_date >= start_date
        )

    if end_date:
        query = query.filter(
            HealthReport.report_date <= end_date
        )

    reports = query.order_by(
        HealthReport.report_date.desc(),
        HealthReport.id.desc(),
    ).all()

    return {
        "reports": reports,
        "search": search,
        "domain": domain,
        "start_date": start_raw,
        "end_date": end_raw,
        "filter_error": filter_error,
    }


# ============================================================
# 5. FUNGSI PERINGATAN DINI
# Aturan demo, bukan standar klinis tervalidasi.
# ============================================================

def evaluate_alerts(reports):
    today = date.today()
    start_date = today - timedelta(days=6)

    warning_threshold = 5
    high_threshold = 10

    totals = {}

    for report in reports:
        if not (start_date <= report.report_date <= today):
            continue

        if report.domain not in DOMAIN_LABELS:
            continue

        if report.indicator not in ALLOWED_INDICATORS:
            continue

        if report.count < 1:
            continue

        key = (
            report.domain,
            report.region,
            report.indicator,
        )

        totals[key] = totals.get(key, 0) + report.count

    alerts = []

    for (domain, region, indicator), total in totals.items():
        if total >= high_threshold:
            level = "Tinggi"
            message = (
                f"Total {total} laporan melewati ambang "
                f"demonstrasi ({high_threshold}) dalam 7 hari. "
                "Verifikasi oleh petugas berwenang diperlukan."
            )

        elif total >= warning_threshold:
            level = "Waspada"
            message = (
                f"Total {total} laporan mencapai ambang "
                f"demonstrasi ({warning_threshold}) dalam 7 hari. "
                "Tinjau kualitas data dan bandingkan dengan "
                "periode sebelumnya."
            )

        else:
            continue

        alerts.append({
            "level": level,
            "domain": DOMAIN_LABELS[domain],
            "region": region,
            "indicator": INDICATOR_LABELS.get(
                indicator,
                indicator.replace("_", " ").title(),
            ),
            "total": total,
            "message": message,
        })

    priority = {"Tinggi": 0, "Waspada": 1}

    alerts.sort(
        key=lambda item: (
            priority[item["level"]],
            -item["total"],
            item["region"],
            item["indicator"],
        )
    )

    return alerts


# ============================================================
# 6. DASHBOARD
# ============================================================

@app.route("/")
@login_required
def dashboard():
    today = date.today()
    week_ago = today - timedelta(days=6)

    reports = HealthReport.query.order_by(
        HealthReport.report_date.desc(),
        HealthReport.id.desc(),
    ).all()

    recent_reports = [
        report for report in reports
        if week_ago <= report.report_date <= today
    ]

    population_total = sum(
        report.count for report in recent_reports
        if report.domain == "population"
    )

    workforce_total = sum(
        report.count for report in recent_reports
        if report.domain == "workforce"
    )

    alerts = evaluate_alerts(reports)
    anomaly_analysis, _risk_rows, _map_points, _actions, _profiles = build_risk_context()

    regions = sorted({
        report.region for report in reports if report.region
    })

    chart_labels = []
    pop_values = []
    work_values = []

    for offset in range(6, -1, -1):
        current_day = today - timedelta(days=offset)
        chart_labels.append(current_day.strftime("%d %b"))

        pop_values.append(sum(
            report.count for report in reports
            if (
                report.report_date == current_day
                and report.domain == "population"
            )
        ))

        work_values.append(sum(
            report.count for report in reports
            if (
                report.report_date == current_day
                and report.domain == "workforce"
            )
        ))

    return render_template(
        "dashboard.html",
        population_total=population_total,
        workforce_total=workforce_total,
        alert_count=len(alerts) + len(anomaly_analysis["alerts"]),
        anomaly_alert_count=len(anomaly_analysis["alerts"]),
        anomaly_model_name=anomaly_analysis["model_name"],
        alerts=alerts[:6],
        latest=reports[:8],
        regions=regions,
        chart_labels=chart_labels,
        pop_values=pop_values,
        work_values=work_values,
        demo_mode=any(r.demo_record for r in reports),
    )


# ============================================================
# 7. INPUT, PENCARIAN, FILTER, DAN RIWAYAT LAPORAN
# ============================================================

@app.route("/laporan", methods=["GET", "POST"])
@login_required
def reports():
    if request.method == "POST":
        try:
            raw_date = request.form.get(
                "report_date", ""
            ).strip()

            domain = request.form.get("domain", "").strip()
            region = request.form.get("region", "").strip()
            indicator = request.form.get("indicator", "").strip()
            raw_count = request.form.get("count", "").strip()
            notes = request.form.get("notes", "").strip()

            if not raw_date:
                raise ValueError("Tanggal laporan wajib diisi.")

            report_date = date.fromisoformat(raw_date)

            if report_date > date.today():
                raise ValueError(
                    "Tanggal laporan tidak boleh di masa depan."
                )

            if domain not in DOMAIN_LABELS:
                raise ValueError("Jenis pemantauan tidak valid.")

            if not region or len(region) > 100:
                raise ValueError(
                    "Wilayah wajib diisi, maksimal 100 karakter."
                )

            if indicator not in ALLOWED_INDICATORS:
                raise ValueError("Indikator tidak valid.")

            if len(notes) > 500:
                raise ValueError("Catatan maksimal 500 karakter.")

            count = int(raw_count)

            if count < 1 or count > 100000:
                raise ValueError(
                    "Jumlah harus antara 1 dan 100000."
                )

            report = HealthReport(
                report_date=report_date,
                domain=domain,
                region=region,
                indicator=indicator,
                count=count,
                notes=notes[:500] or None,
                demo_record=False,
            )

            db.session.add(report)
            db.session.commit()

            flash("Laporan berhasil disimpan.", "success")
            return redirect(url_for("reports"))

        except (ValueError, TypeError):
            db.session.rollback()
            flash(
                "Data tidak valid. Periksa tanggal, jenis pemantauan, "
                "wilayah, indikator, dan jumlah laporan.",
                "error",
            )

        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Gagal menyimpan laporan.")
            flash(
                "Laporan belum berhasil disimpan karena masalah database.",
                "error",
            )

    result = get_filtered_reports()

    return render_template(
        "reports.html",
        reports=result["reports"][:100],
        total_filtered=len(result["reports"]),
        today=date.today().isoformat(),
        search=result["search"],
        selected_domain=result["domain"],
        start_date=result["start_date"],
        end_date=result["end_date"],
        filter_error=result["filter_error"],
    )


# ============================================================
# 8. EKSPOR CSV
# Menggunakan filter yang sama dengan halaman laporan.
# ============================================================

@app.route("/laporan/ekspor")
@login_required
def export_reports():
    result = get_filtered_reports()

    if result["filter_error"]:
        flash(result["filter_error"], "error")
        return redirect(url_for("reports"))

    output = io.StringIO()
    writer = csv.writer(output)

    # BOM membantu Excel mengenali UTF-8.
    output.write("\ufeff")

    writer.writerow([
        "Tanggal",
        "Jenis Pemantauan",
        "Wilayah / Unit Kerja",
        "Indikator",
        "Jumlah Laporan",
        "Sumber Data",
        "Catatan Agregat",
    ])

    for report in result["reports"]:
        writer.writerow([
            report.report_date.isoformat(),
            csv_safe_text(DOMAIN_LABELS.get(report.domain, report.domain)),
            csv_safe_text(report.region),
            csv_safe_text(INDICATOR_LABELS.get(
                report.indicator,
                report.indicator,
            )),
            report.count,
            csv_safe_text("Simulasi" if report.demo_record else "Input pengguna"),
            csv_safe_text(report.notes or ""),
        ])

    memory_file = io.BytesIO(output.getvalue().encode("utf-8"))
    memory_file.seek(0)

    filename = f"sipanda_laporan_{date.today().isoformat()}.csv"

    return send_file(
        memory_file,
        mimetype="text/csv; charset=utf-8",
        as_attachment=True,
        download_name=filename,
    )


# ============================================================
# 9. HALAMAN PERINGATAN DINI
# ============================================================

@app.route("/peringatan")
@login_required
def alerts_page():
    reports = HealthReport.query.all()
    alerts = evaluate_alerts(reports)
    anomaly_analysis, risk_rows, _map_points, _actions, _profiles = build_risk_context()
    return render_template(
        "alerts.html", alerts=alerts,
        anomaly_alerts=anomaly_analysis["alerts"],
        model_name=anomaly_analysis["model_name"],
        model_ready=anomaly_analysis["model_ready"],
        risk_rows=risk_rows,
    )


@app.route("/sinyal", methods=["GET", "POST"])
@login_required
def signals_page():
    if request.method == "POST":
        try:
            observed_on = date.fromisoformat(request.form.get("observed_on", "").strip())
            region = request.form.get("region", "").strip()
            metric = request.form.get("metric", "").strip()
            source_name = request.form.get("source_name", "").strip()
            notes = request.form.get("notes", "").strip()
            raw_value = request.form.get("value", "").strip().replace(",", ".")
            meta = SIGNAL_METRICS.get(metric)
            if not meta:
                raise ValueError("Indikator sinyal tidak valid.")
            if observed_on > date.today():
                raise ValueError("Tanggal pengamatan tidak boleh di masa depan.")
            if not region or len(region) > 100:
                raise ValueError("Nama wilayah wajib diisi (maksimal 100 karakter).")
            if not source_name or len(source_name) > 120:
                raise ValueError("Nama sumber data wajib diisi (maksimal 120 karakter).")
            if len(notes) > 300:
                raise ValueError("Catatan maksimal 300 karakter.")
            value = float(raw_value)
            if not (meta["min"] <= value <= meta["max"]):
                raise ValueError(f"Nilai {meta['label']} harus antara {meta['min']} dan {meta['max']}.")
            db.session.add(SignalObservation(
                observed_on=observed_on, region=region,
                source_type=meta["source"], metric=metric, value=value,
                unit=meta["unit"], source_name=source_name,
                notes=notes or None, demo_record=False,
                created_by_id=current_user.id,
            ))
            db.session.commit()
            flash("Sinyal tambahan berhasil disimpan dan akan dianalisis bersama laporan kesehatan.", "success")
            return redirect(url_for("signals_page"))
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            flash(str(exc) or "Data sinyal tidak valid.", "error")
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Gagal menyimpan sinyal tambahan.")
            flash("Sinyal belum berhasil disimpan karena masalah database.", "error")

    observations = SignalObservation.query.order_by(
        SignalObservation.observed_on.desc(), SignalObservation.id.desc()
    ).limit(100).all()
    return render_template(
        "signals.html", observations=observations,
        today=date.today().isoformat(), metrics=SIGNAL_METRICS,
    )


@app.route("/peta-risiko")
@login_required
def risk_map_page():
    analysis, risks, map_points, actions, profiles = build_risk_context()

    finding_options = []

    for alert in analysis.get("alerts", []):
        region = str(alert.get("region", "")).strip()
        alert_date = str(alert.get("date", ""))[:10]

        if not region or not alert_date:
            continue

        recommendations = alert.get("recommendations") or []

        finding_options.append({
            "finding_key": f"{region}:{alert_date}",
            "region": region,
            "date": alert_date,
            "level": alert.get("level", "Waspada"),
            "title": f"Verifikasi anomali kesehatan - {region}",
            "recommended_action": "\n".join(
                str(item) for item in recommendations
            )[:3000],
            "demo_record": bool(alert.get("demo_record", False)),
        })

    return render_template(
        "risk_map.html",
        risks=risks,
        map_points=map_points,
        actions=actions,
        model_name=analysis["model_name"],
        model_ready=analysis["model_ready"],
        observations=analysis["observations"],
        profiles=profiles,
        finding_options=finding_options,
    )


@app.route("/wilayah/simpan", methods=["POST"])
@admin_required
def save_region_profile():
    try:
        region = request.form.get("region", "").strip()
        lat = float(request.form.get("latitude", ""))
        lon = float(request.form.get("longitude", ""))
        pic_name = request.form.get("pic_name", "").strip()
        pic_role = request.form.get("pic_role", "").strip()
        location_note = request.form.get("location_note", "").strip()
        if not region or len(region) > 100:
            raise ValueError("Nama wilayah wajib diisi (maksimal 100 karakter).")
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Koordinat lintang/bujur tidak valid.")
        if len(pic_name) > 120 or len(pic_role) > 120 or len(location_note) > 240:
            raise ValueError("Nama PIC, peran, atau catatan lokasi terlalu panjang.")
        profile = RegionProfile.query.filter_by(region=region).first()
        if profile is None:
            profile = RegionProfile(region=region)
            db.session.add(profile)
        profile.latitude = lat
        profile.longitude = lon
        profile.pic_name = pic_name or None
        profile.pic_role = pic_role or None
        profile.location_note = location_note or "Titik pusat wilayah; bukan lokasi individu."
        profile.demo_location = False
        profile.updated_at = datetime.utcnow()
        db.session.commit()
        flash("Profil wilayah dan titik pusat agregat berhasil disimpan.", "success")
    except (ValueError, TypeError) as exc:
        db.session.rollback()
        flash(str(exc) or "Data wilayah tidak valid.", "error")
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Gagal menyimpan profil wilayah.")
        flash("Profil wilayah belum berhasil disimpan.", "error")
    return redirect(url_for("risk_map_page"))


@app.route("/tindak-lanjut/tambah", methods=["POST"])
@login_required
def add_action_assignment():
    try:
        region = request.form.get("region", "").strip()
        title = request.form.get("title", "").strip()
        action = request.form.get("recommended_action", "").strip()
        assigned_to = request.form.get("assigned_to", "").strip()
        owner_role = request.form.get("owner_role", "").strip()
        due_raw = request.form.get("due_date", "").strip()

        selected_finding_key = request.form.get(
            "finding_key", ""
        ).strip()

        is_ai_finding = bool(selected_finding_key)

        if is_ai_finding:
            current_analysis = analyze_multisource(
                collect_anomaly_records(demo_only=False)
            )

            selected_alert = None

            for alert in current_analysis.get("alerts", []):
                alert_region = str(
                    alert.get("region", "")
                ).strip()

                alert_date = str(
                    alert.get("date", "")
                )[:10]

                expected_key = f"{alert_region}:{alert_date}"

                if expected_key == selected_finding_key:
                    selected_alert = alert
                    break

            if selected_alert is None:
                raise ValueError(
                    "Temuan AI tidak ditemukan atau sudah berubah. "
                    "Silakan muat ulang halaman."
                )

            region = str(selected_alert["region"]).strip()

            # Judul dan tindakan wajib berasal dari hasil AI.
            title = (
                f"Verifikasi anomali kesehatan - {region}"
            )

            recommendations = (
                selected_alert.get("recommendations") or []
            )

            action = "\n".join(
                str(item).strip()
                for item in recommendations
                if str(item).strip()
            )

            finding_key = selected_finding_key

            if not action:
                raise ValueError(
                    "Temuan AI belum memiliki rekomendasi tindakan."
                )

        else:
            finding_key = (
                f"{region}:{date.today().isoformat()}"
            )

        if not all([
            region,
            title,
            action,
            assigned_to,
            owner_role,
        ]):
            raise ValueError(
                "Wilayah, ringkasan, tindakan, PIC, dan peran wajib diisi."
            )

        if len(region) > 100:
            raise ValueError("Nama wilayah maksimal 100 karakter.")

        if len(title) > 160:
            raise ValueError("Judul maksimal 160 karakter.")

        if len(action) > 3000:
            raise ValueError("Tindakan maksimal 3000 karakter.")

        if len(assigned_to) > 120:
            raise ValueError("Nama PIC maksimal 120 karakter.")

        if len(owner_role) > 120:
            raise ValueError("Peran PIC maksimal 120 karakter.")

        if len(finding_key) > 120:
            raise ValueError("Identitas temuan terlalu panjang.")

        due_date = (
            date.fromisoformat(due_raw)
            if due_raw
            else None
        )

        db.session.add(
            ActionAssignment(
                region=region,
                finding_key=finding_key,
                title=title,
                recommended_action=action,
                assigned_to=assigned_to,
                owner_role=owner_role,
                due_date=due_date,
                status="open",
                demo_record=False,
                created_by_id=current_user.id,
            )
        )

        db.session.commit()

        flash(
            (
                "Rekomendasi AI berhasil diteruskan menjadi "
                "tindak lanjut dan PIC telah ditetapkan."
            )
            if is_ai_finding
            else (
                "Tindak lanjut manual berhasil dibuat "
                "dan PIC telah ditetapkan."
            ),
            "success",
        )

    except (ValueError, TypeError) as exc:
        db.session.rollback()
        flash(
            str(exc) or "Data tindak lanjut tidak valid.",
            "error",
        )

    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception(
            "Gagal menyimpan tindak lanjut."
        )
        flash(
            "Tindak lanjut belum berhasil disimpan.",
            "error",
        )

    return redirect(url_for("risk_map_page"))


@app.route("/tindak-lanjut/<int:action_id>/status", methods=["POST"])
@login_required
def update_action_status(action_id):
    action = db.session.get(ActionAssignment, action_id)
    if action is None:
        flash("Tindak lanjut tidak ditemukan.", "error")
        return redirect(url_for("risk_map_page"))
    status = request.form.get("status", "")
    if status not in {"open", "in_progress", "done"}:
        flash("Status tindak lanjut tidak valid.", "error")
    else:
        action.status = status
        db.session.commit()
        flash("Status tindak lanjut diperbarui.", "success")
    return redirect(url_for("risk_map_page"))


@app.route("/demo")
def public_demo():
    """Read-only public showcase; strictly limited to records marked as demo."""
    analysis, risks, map_points, actions, _profiles = build_risk_context(demo_only=True)
    demo_reports = HealthReport.query.filter_by(demo_record=True).order_by(
        HealthReport.report_date.desc(), HealthReport.id.desc()
    ).limit(12).all()
    demo_signals = SignalObservation.query.filter_by(demo_record=True).order_by(
        SignalObservation.observed_on.desc(), SignalObservation.id.desc()
    ).limit(20).all()
    return render_template(
        "demo.html", risks=risks, map_points=map_points,
        anomaly_alerts=analysis["alerts"], model_name=analysis["model_name"],
        model_ready=analysis["model_ready"], observations=analysis["observations"],
        demo_reports=demo_reports, demo_signals=demo_signals,
        demo_actions=actions,
    )


# ============================================================
# GEMINI AI RISK INSIGHTS
# Penjelasan AI berdasarkan temuan anomali agregat.
# ============================================================

@app.route("/ai-insights", methods=["GET", "POST"])
@login_required
@limiter.limit("10 per hour", methods=["POST"])
def ai_insights_page():

    analysis, risks, _map_points, _actions, _profiles = (
        build_risk_context(demo_only=True)
    )

    alerts = analysis.get("alerts", [])
    ai_result = None
    ai_error = None

    if request.method == "POST":

        if not alerts:
            ai_error = (
                "Belum ada temuan anomali untuk dianalisis. "
                "Silakan periksa data pemantauan terlebih dahulu."
            )

        else:
            try:
                ai_result = generate_risk_insights(alerts)

            except Exception:
                app.logger.exception(
                    "Gemini AI gagal menghasilkan analisis."
                )

                ai_error = (
                    "Layanan Gemini AI belum dapat menghasilkan "
                    "analisis. Periksa koneksi API dan konfigurasi "
                    "GEMINI_API_KEY."
                )

    return render_template(
        "gemini_insights.html",
        alerts=alerts,
        risks=risks,
        ai_result=ai_result,
        ai_error=ai_error,
        model_name=os.getenv(
            "GEMINI_MODEL",
            "gemini-2.5-flash",
        ),
        detection_model=analysis.get(
            "model_name",
            "Multi-source anomaly detection",
        ),
        model_ready=analysis.get("model_ready", False),
        observations=analysis.get("observations", 0),
    )



# ============================================================
# 10. HALAMAN TENTANG SISTEM
# ============================================================

@app.route("/tentang")
@login_required
def about():
    return render_template("about.html")


# ============================================================
# 11. DATA DEMONSTRASI
# Hanya dimasukkan jika database masih kosong.
# ============================================================

def seed_demo_data():
    # Jangan menambahkan data demo berulang, tetapi jangan pula melewatkan
    # data demo hanya karena database lama sudah berisi laporan non-demo.
    if HealthReport.query.filter_by(demo_record=True).count() > 0:
        return

    today = date.today()

    examples = [
        (6, "population", "Kota Contoh", "gejala_pernapasan", 3),
        (5, "population", "Kota Contoh", "gejala_pernapasan", 4),
        (2, "population", "Kota Contoh", "gejala_pernapasan", 5),
        (1, "population", "Kabupaten Contoh", "demam", 2),
        (6, "workforce", "Unit Produksi A", "keluhan_panas", 2),
        (5, "workforce", "Unit Produksi A", "keluhan_panas", 2),
        (3, "workforce", "Unit Produksi A", "keluhan_panas", 3),
        (2, "workforce", "Unit Gudang B", "kelelahan", 2),
    ]

    for offset, domain, region, indicator, count in examples:
        db.session.add(HealthReport(
            report_date=today - timedelta(days=offset),
            domain=domain,
            region=region,
            indicator=indicator,
            count=count,
            notes="Data simulasi untuk demonstrasi",
            demo_record=True,
        ))

    db.session.commit()



def seed_review_demo_data():
    """Create clearly labelled synthetic multi-source data for reviewer demos."""
    if SignalObservation.query.filter_by(demo_record=True).count() > 0:
        return

    today = date.today()
    demo_regions = [
        ("Zona Simulasi Utara", -6.185, 106.825, "Koordinator Kesehatan", "Kesmas", "Koordinat ilustratif untuk demonstrasi"),
        ("Zona Simulasi Tengah", -6.205, 106.845, "Petugas K3 Demo", "K3", "Koordinat ilustratif untuk demonstrasi"),
        ("Zona Simulasi Selatan", -6.225, 106.815, "Koordinator Wilayah Demo", "Kesmas/K3", "Koordinat ilustratif untuk demonstrasi"),
    ]
    for region, lat, lon, pic, role, note in demo_regions:
        if not RegionProfile.query.filter_by(region=region).first():
            db.session.add(RegionProfile(
                region=region, latitude=lat, longitude=lon,
                pic_name=pic, pic_role=role, location_note=note,
                demo_location=True,
            ))

    for offset in range(34, -1, -1):
        observed = today - timedelta(days=offset)
        day_index = 34 - offset
        for idx, (region, *_rest) in enumerate(demo_regions):
            # Stable synthetic baselines with mild deterministic variation.
            temp = 29.0 + ((day_index + idx) % 5) * 0.22
            aqi = 42.0 + ((day_index * 2 + idx) % 7) * 1.8
            absence = 2.0 + ((day_index + idx) % 4) * 0.18
            incidents = 1.0 + ((day_index + 2 * idx) % 3) * 0.15
            health_count = 3 + ((day_index + idx) % 3)
            if offset == 0 and idx == 0:
                temp, aqi, absence, incidents, health_count = 38.2, 178.0, 12.5, 7.0, 24
            elif offset == 0 and idx == 1:
                aqi, absence, health_count = 98.0, 5.8, 12
            elif offset == 0 and idx == 2:
                health_count = 4

            values = [
                ("environment", "temperature_c", temp, "°C", "Sensor lingkungan demo"),
                ("environment", "air_quality_index", aqi, "AQI", "Feed kualitas udara simulasi"),
                ("workforce", "absenteeism_rate", absence, "%", "Rekap absensi simulasi"),
                ("workforce", "workplace_incidents", incidents, "kejadian", "Log insiden simulasi"),
            ]
            for source_type, metric, value, unit, source_name in values:
                db.session.add(SignalObservation(
                    observed_on=observed, region=region,
                    source_type=source_type, metric=metric, value=value,
                    unit=unit, source_name=source_name,
                    notes="DATA SIMULASI — bukan pengukuran atau laporan aktual.",
                    demo_record=True,
                ))
            db.session.add(HealthReport(
                report_date=observed, domain="population", region=region,
                indicator="keluhan_kesehatan", count=health_count,
                notes="DATA SIMULASI — bukan data pasien atau fasilitas kesehatan.",
                demo_record=True,
            ))

    if ActionAssignment.query.filter_by(demo_record=True).count() == 0:
        db.session.add(ActionAssignment(
            region="Zona Simulasi Utara",
            finding_key="demo-multisource-001",
            title="Verifikasi sinyal lintas sumber",
            recommended_action=(
                "Verifikasi kualitas laporan kesehatan, pembacaan lingkungan, dan rekap tenaga kerja; "
                "lakukan pemeriksaan lapangan sesuai prosedur institusi dan eskalasikan hanya setelah validasi manusia."
            ),
            assigned_to="Koordinator Kesehatan (Demo)",
            owner_role="Koordinator Kesmas/K3",
            due_date=today + timedelta(days=2),
            status="open", demo_record=True,
        ))
    db.session.commit()


# ============================================================
# SETUP AWAL, LOGIN, LOGOUT, DAN MANAJEMEN AKUN
# ============================================================


@app.route("/setup", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def setup():
    setup_token = os.getenv("ADMIN_SETUP_TOKEN", "")

    # Setup harus memiliki token rahasia dari environment.
    if not setup_token:
        return "Setup administrator dinonaktifkan.", 404

    # Setup hanya berlaku sebelum administrator pertama dibuat.
    if User.query.first():
        flash("Administrator sudah dibuat. Silakan login.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        submitted_token = request.form.get("setup_token", "")

        if not hmac.compare_digest(submitted_token, setup_token):
            flash("Token setup tidak valid.", "error")
            return render_template("setup.html"), 403

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if len(username) < 4 or len(username) > 80:
            flash("Username harus terdiri dari 4–80 karakter.", "error")
        elif len(password) < 12:
            flash("Kata sandi minimal 12 karakter.", "error")
        elif password != confirm:
            flash("Konfirmasi kata sandi tidak cocok.", "error")
        else:
            user = User(username=username, role="admin", active=True)
            user.set_password(password)

            db.session.add(user)
            db.session.commit()

            login_user(user)
            session.permanent = True

            flash(
                "Administrator berhasil dibuat. Simpan kata sandi dengan aman.",
                "success",
            )
            return redirect(url_for("dashboard"))

    return render_template("setup.html")

def setup():
    if User.query.first():
        flash("Administrator sudah dibuat. Silakan login.", "error")
        return redirect(url_for("login"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(username) < 4 or len(username) > 80:
            flash("Username harus terdiri dari 4–80 karakter.", "error")
        elif len(password) < 12:
            flash("Kata sandi minimal 12 karakter.", "error")
        elif password != confirm:
            flash("Konfirmasi kata sandi tidak cocok.", "error")
        else:
            user = User(username=username, role="admin", active=True)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            session.permanent = True
            flash("Administrator berhasil dibuat. Simpan kata sandi dengan aman.", "success")
            return redirect(url_for("dashboard"))
    return render_template("setup.html")


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if not User.query.first():
        return redirect(url_for("setup"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username, active=True).first()
        if user and user.check_password(password):
            login_user(user, remember=False, fresh=True)
            # Terapkan PERMANENT_SESSION_LIFETIME (30 menit) pada sesi login.
            session.permanent = True
            return redirect(url_for("dashboard"))
        flash("Username atau kata sandi tidak benar.", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Kamu berhasil keluar dari SIPANDA.", "success")
    return redirect(url_for("login"))


@app.route("/pengguna", methods=["GET", "POST"])
@admin_required
def users_page():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "")
        if len(username) < 4 or len(username) > 80:
            flash("Username harus terdiri dari 4–80 karakter.", "error")
        elif len(password) < 12:
            flash("Kata sandi pengguna minimal 12 karakter.", "error")
        elif role not in {"admin", "petugas"}:
            flash("Peran pengguna tidak valid.", "error")
        elif User.query.filter_by(username=username).first():
            flash("Username sudah digunakan.", "error")
        else:
            user = User(username=username, role=role, active=True)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash(f"Akun {role} berhasil dibuat.", "success")
            return redirect(url_for("users_page"))
    users = User.query.order_by(User.username.asc()).all()
    return render_template("users.html", users=users)


# ============================================================
# 12. INISIALISASI DATABASE DAN SERVER
# ============================================================

with app.app_context():
    db.create_all()

    if os.getenv("LOAD_DEMO_DATA", "true").lower() == "true":
        seed_demo_data()
        seed_review_demo_data()


if __name__ == "__main__":
    debug_mode = os.getenv(
        "FLASK_DEBUG", "false"
    ).lower() == "true"

    app.run(debug=debug_mode)
