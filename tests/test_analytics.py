import unittest
import sys
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics import analyze_multisource


class MultiSourceAnalyticsTests(unittest.TestCase):
    def make_history(self):
        today = date.today()
        records = []
        regions = [
            "Zona Simulasi Utara",
            "Zona Simulasi Tengah",
            "Zona Simulasi Selatan",
        ]
        for index in range(35):
            observed = today - timedelta(days=34 - index)
            for region_index, region in enumerate(regions):
                values = {
                    "health_reports": 3 + ((index + region_index) % 3),
                    "temperature_c": 29 + ((index + region_index) % 5) * 0.22,
                    "air_quality_index": 42 + ((index * 2 + region_index) % 7) * 1.8,
                    "absenteeism_rate": 2 + ((index + region_index) % 4) * 0.18,
                    "workplace_incidents": 1 + ((index + 2 * region_index) % 3) * 0.15,
                }
                if index == 34 and region_index == 0:
                    values.update({
                        "health_reports": 24,
                        "temperature_c": 38.2,
                        "air_quality_index": 178,
                        "absenteeism_rate": 12.5,
                        "workplace_incidents": 7,
                    })
                for metric, value in values.items():
                    source = {
                        "health_reports": "Layanan kesehatan",
                        "temperature_c": "Lingkungan",
                        "air_quality_index": "Lingkungan",
                        "absenteeism_rate": "Tenaga kerja",
                        "workplace_incidents": "Tenaga kerja",
                    }[metric]
                    records.append({
                        "region": region,
                        "observed_on": observed,
                        "metric": metric,
                        "value": value,
                        "source_type": source,
                        "demo_record": True,
                    })
        return records

    def test_multisource_spike_is_explained(self):
        result = analyze_multisource(self.make_history(), date.today())
        north = next(
            item for item in result["alerts"]
            if item["region"] == "Zona Simulasi Utara"
        )
        self.assertTrue(north["is_multi_source"])
        self.assertIn("Layanan kesehatan", north["sources"])
        self.assertIn("Lingkungan", north["sources"])
        self.assertIn("Tenaga kerja", north["sources"])
        self.assertTrue(north["drivers"])
        self.assertGreater(north["risk_score"], 0)

    def test_insufficient_history_does_not_force_alert(self):
        today = date.today()
        records = [
            {
                "region": "Wilayah Uji",
                "observed_on": today - timedelta(days=offset),
                "metric": "temperature_c",
                "value": 30 + offset,
                "source_type": "Lingkungan",
                "demo_record": True,
            }
            for offset in range(4)
        ]
        result = analyze_multisource(records, today)
        self.assertFalse(result["model_ready"])
        self.assertEqual(result["alerts"], [])

    def test_region_without_anomaly_has_independent_status(self):
        result = analyze_multisource(self.make_history(), date.today())
        south = next(
            item for item in result["risks"]
            if item["region"] == "Zona Simulasi Selatan"
        )
        self.assertEqual(south["level"], "Belum terindikasi")
        self.assertEqual(south["risk_score"], 0)
        self.assertFalse(south["has_multi_source"])

    def test_negative_temperature_is_valid_and_detectable(self):
        today = date.today()
        records = []
        for offset in range(1, 30):
            records.append({
                "region": "Wilayah Suhu",
                "observed_on": today - timedelta(days=offset),
                "metric": "temperature_c",
                "value": 20.0,
                "source_type": "environment",
            })
        records.append({
            "region": "Wilayah Suhu",
            "observed_on": today,
            "metric": "temperature_c",
            "value": -5.0,
            "source_type": "environment",
        })
        result = analyze_multisource(records, today)
        alert = next(
            item for item in result["alerts"]
            if item["region"] == "Wilayah Suhu"
        )
        self.assertEqual(alert["drivers"][0]["unit"], "°C")
        self.assertGreater(alert["drivers"][0]["z_score"], 2.5)

    def test_non_finite_values_are_ignored(self):
        today = date.today()
        records = [{
            "region": "Wilayah Uji",
            "observed_on": today,
            "metric": "temperature_c",
            "value": float("nan"),
            "source_type": "Lingkungan",
        }]
        result = analyze_multisource(records, today)
        self.assertEqual(result["observations"], 0)
        self.assertEqual(result["alerts"], [])

    def test_source_group_is_derived_from_metric(self):
        today = date.today()
        records = []
        for offset in range(1, 8):
            observed = today - timedelta(days=offset)
            records.extend([
                {
                    "region": "Wilayah Sumber",
                    "observed_on": observed,
                    "metric": "temperature_c",
                    "value": 25.0,
                    # Deliberately incorrect label; metric remains environment.
                    "source_type": "workforce",
                },
                {
                    "region": "Wilayah Sumber",
                    "observed_on": observed,
                    "metric": "absenteeism_rate",
                    "value": 2.0,
                    "source_type": "environment",
                },
            ])
        result = analyze_multisource(records, today)
        self.assertFalse(result["model_ready"])
        self.assertEqual(result["risks"][0]["sources"], ["Lingkungan", "Tenaga kerja"])

    def test_duplicate_measurements_are_aggregated(self):
        today = date.today()
        records = []
        for offset in range(1, 8):
            observed = today - timedelta(days=offset)
            records.extend([
                {
                    "region": "Wilayah Duplikat",
                    "observed_on": observed,
                    "metric": "temperature_c",
                    "value": 20.0,
                    "source_type": "environment",
                },
                {
                    "region": "Wilayah Duplikat",
                    "observed_on": observed,
                    "metric": "temperature_c",
                    "value": 22.0,
                    "source_type": "environment",
                },
            ])
        result = analyze_multisource(records, today)
        self.assertEqual(result["observations"], 7)
        self.assertEqual(result["regions"], 1)


if __name__ == "__main__":
    unittest.main()
