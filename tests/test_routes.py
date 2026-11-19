"""Minimal integration checks; uses a disposable SQLite database."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import date

TEST_DB = Path(tempfile.gettempdir()) / "sipanda_routes_test.sqlite"
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ["SECRET_KEY"] = "test-only-secret-key-not-for-deployment-123456789"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["LOAD_DEMO_DATA"] = "false"
os.environ["FLASK_DEBUG"] = "false"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app import (  # noqa: E402
    app, db, User, HealthReport, SignalObservation,
    RegionProfile, ActionAssignment, seed_review_demo_data,
)


class SipandaRouteTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        with app.app_context():
            db.session.remove()
            db.drop_all()
            db.create_all()
            admin = User(username="admin_test", role="admin", active=True)
            admin.set_password("StrongAdminPassword123!")
            db.session.add(admin)
            db.session.commit()
        self.client = app.test_client()

    def login_admin(self):
        response = self.client.post("/login", data={
            "username": "admin_test",
            "password": "StrongAdminPassword123!",
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

    def test_public_demo_is_read_only_and_protected_pages_require_login(self):
        response = self.client.get("/demo")
        self.assertEqual(response.status_code, 200)
        for path in ("/", "/laporan", "/sinyal", "/peringatan", "/peta-risiko", "/pengguna"):
            self.assertIn(self.client.get(path).status_code, (302, 303))

    def test_signal_and_action_workflows(self):
        self.login_admin()
        stamp = date.today().isoformat()
        response = self.client.post("/sinyal", data={
            "observed_on": stamp, "region": "Wilayah Integrasi Uji",
            "metric": "temperature_c", "value": "33.5",
            "source_name": "Sensor simulasi integrasi",
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Sinyal tambahan berhasil disimpan", response.data)

        response = self.client.post("/tindak-lanjut/tambah", data={
            "region": "Wilayah Integrasi Uji", "title": "Verifikasi sinyal",
            "recommended_action": "Cocokkan data dengan sumber dan SOP.",
            "assigned_to": "Petugas Uji", "owner_role": "K3",
            "due_date": stamp,
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        with app.app_context():
            self.assertEqual(ActionAssignment.query.filter_by(region="Wilayah Integrasi Uji").count(), 1)

    def test_public_demo_never_displays_non_demo_region(self):
        with app.app_context():
            seed_review_demo_data()
            db.session.add(SignalObservation(
                observed_on=date.today(), region="PRIVATE_REAL_REGION_TEST",
                source_type="environment", metric="temperature_c",
                value=31.0, unit="°C", source_name="Private source",
                demo_record=False,
            ))
            db.session.add(HealthReport(
                report_date=date.today(), domain="population",
                region="PRIVATE_REAL_REGION_TEST", indicator="demam",
                count=1, demo_record=False,
            ))
            db.session.commit()
        response = self.client.get("/demo")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"PRIVATE_REAL_REGION_TEST", response.data)
        self.assertIn(b"Zona Simulasi Utara", response.data)

    def test_petugas_cannot_access_admin_only_pages(self):
        self.login_admin()
        response = self.client.post("/pengguna", data={
            "username": "petugas_test", "password": "StrongPetugas123!", "role": "petugas",
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.client.post("/logout", follow_redirects=True)
        response = self.client.post("/login", data={
            "username": "petugas_test", "password": "StrongPetugas123!",
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.client.get("/pengguna").status_code, (302, 303))
        self.assertIn(self.client.post("/wilayah/simpan", data={
            "region": "Tidak Diizinkan", "latitude": "-1", "longitude": "100",
        }).status_code, (302, 303))


if __name__ == "__main__":
    unittest.main()
