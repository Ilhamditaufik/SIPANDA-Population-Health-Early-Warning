
"""Explainable multi-source anomaly analysis for the SIPANDA prototype.

Combines health-service, environmental, and workforce signals.
Isolation Forest is used only when sufficiently complete multivariate
observations are available. Robust rolling scores explain contributing
indicators. Results are review aids, not clinical predictions.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from math import isfinite
from statistics import median, pstdev
from typing import Any

FEATURES = (
    "health_reports",
    "temperature_c",
    "air_quality_index",
    "absenteeism_rate",
    "workplace_incidents",
)

FEATURE_META = {
    "health_reports": (
        "Layanan kesehatan",
        "Jumlah laporan kesehatan",
        "laporan",
    ),
    "temperature_c": (
        "Lingkungan",
        "Suhu lingkungan",
        "°C",
    ),
    "air_quality_index": (
        "Lingkungan",
        "Indeks kualitas udara",
        "AQI",
    ),
    "absenteeism_rate": (
        "Tenaga kerja",
        "Tingkat ketidakhadiran",
        "%",
    ),
    "workplace_incidents": (
        "Tenaga kerja",
        "Insiden tempat kerja",
        "kejadian",
    ),
}


def _robust_score(
    values: list[float],
    current: float,
    two_sided: bool = False,
) -> tuple[float | None, float | None, float | None]:
    """Return modified z-score, median baseline, and robust scale.

    By default, only unusually high values are considered.
    Temperature uses two-sided detection because unusually low
    temperatures can also be relevant environmental anomalies.
    """
    if len(values) < 5:
        return None, None, None

    centre = float(median(values))
    deviations = [abs(value - centre) for value in values]
    mad = float(median(deviations))
    scale = 1.4826 * mad

    if scale < 1e-9:
        scale = float(pstdev(values)) if len(values) > 1 else 0.0

    if scale < 1e-9:
        scale = max(abs(centre) * 0.05, 0.25)

    difference = float(current) - centre
    score = abs(difference) / scale if two_sided else max(0.0, difference / scale)

    return score, centre, scale


def analyze_multisource(
    records: list[dict[str, Any]],
    as_of: date | None = None,
) -> dict[str, Any]:
    """Analyze region-day observations and return alerts and map risks.

    Required record fields:
    region, observed_on, metric, value, source_type.

    Source groups are derived from the metric definition, not from
    arbitrary source_type text supplied by an individual record.
    """
    as_of = as_of or date.today()
    first_day = as_of - timedelta(days=34)

    daily_values: dict[tuple[str, date], dict[str, float]] = defaultdict(dict)
    daily_sources: dict[tuple[str, date], set[str]] = defaultdict(set)
    daily_demo: dict[tuple[str, date], bool] = defaultdict(bool)
    metric_history: dict[
        tuple[str, str], list[tuple[date, float]]
    ] = defaultdict(list)

    # Aggregate valid duplicate measurements by region, day, and metric.
    buckets: dict[tuple[str, date, str], list[float]] = defaultdict(list)

    for record in records:
        region = str(record.get("region", "")).strip()
        metric = str(record.get("metric", "")).strip()
        observed_on = record.get("observed_on")

        if not region or metric not in FEATURES:
            continue

        if not isinstance(observed_on, date):
            continue

        if observed_on < first_day or observed_on > as_of:
            continue

        try:
            value = float(record.get("value"))
        except (TypeError, ValueError, OverflowError):
            continue

        # Reject NaN and positive/negative infinity.
        if not isfinite(value):
            continue

        # Negative values are valid only for temperature.
        if metric != "temperature_c" and value < 0:
            continue

        key = (region, observed_on)
        buckets[(region, observed_on, metric)].append(value)

        # Canonical source group comes from the metric definition.
        source_group = FEATURE_META[metric][0]
        daily_sources[key].add(source_group)

        daily_demo[key] = (
            daily_demo[key] or bool(record.get("demo_record", False))
        )

    for (region, observed_on, metric), values in buckets.items():
        if not values:
            continue

        # Health report counts are summed; other measurements are averaged.
        if metric == "health_reports":
            aggregated = float(sum(values))
        else:
            aggregated = float(sum(values) / len(values))

        if not isfinite(aggregated):
            continue

        daily_values[(region, observed_on)][metric] = aggregated
        metric_history[(region, metric)].append(
            (observed_on, aggregated)
        )

    if not daily_values:
        return {
            "alerts": [],
            "risks": [],
            "model_name": "Belum cukup data",
            "model_ready": False,
            "observations": 0,
            "regions": 0,
        }

    for history in metric_history.values():
        history.sort(key=lambda item: item[0])

    matrix_rows = sorted(
        daily_values.items(),
        key=lambda item: (item[0][0], item[0][1]),
    )

    # Attempt Isolation Forest only with sufficiently complete observations.
    model_ready = False
    model_name = "Robust rolling z-score (fallback)"
    isolation_flags: dict[tuple[str, date], bool] = {}

    eligible_rows = [
        row
        for row in matrix_rows
        if len(daily_sources.get(row[0], set())) >= 2
        and len(row[1]) >= 2
    ]

    observed_source_count = len({
        source
        for sources in daily_sources.values()
        for source in sources
    })

    if len(eligible_rows) >= 20 and observed_source_count >= 2:
        try:
            import numpy as np
            from sklearn.ensemble import IsolationForest

            # Keep only features present in at least 80% of eligible rows.
            minimum_coverage = max(
                20,
                int(len(eligible_rows) * 0.80 + 0.999),
            )

            selected_features = [
                feature
                for feature in FEATURES
                if sum(
                    feature in values
                    and isfinite(values[feature])
                    for _, values in eligible_rows
                ) >= minimum_coverage
            ]

            if len(selected_features) >= 2:
                selected_rows = [
                    (key, values)
                    for key, values in eligible_rows
                    if all(
                        feature in values
                        and isfinite(values[feature])
                        for feature in selected_features
                    )
                ]

                # No synthetic median imputation: use complete rows only.
                if len(selected_rows) >= 20:
                    matrix = np.array(
                        [
                            [values[feature] for feature in selected_features]
                            for _, values in selected_rows
                        ],
                        dtype=float,
                    )

                    centres = np.median(matrix, axis=0)
                    q25 = np.percentile(matrix, 25, axis=0)
                    q75 = np.percentile(matrix, 75, axis=0)

                    scales = q75 - q25
                    standard_deviations = np.std(matrix, axis=0)
                    scales = np.where(
                        scales < 1e-9,
                        standard_deviations,
                        scales,
                    )
                    scales = np.where(scales < 1e-9, 1.0, scales)

                    normalized = (matrix - centres) / scales

                    model = IsolationForest(
                        n_estimators=150,
                        contamination=0.08,
                        random_state=42,
                    )

                    predictions = model.fit_predict(normalized)

                    isolation_flags = {
                        key: bool(prediction == -1)
                        for (key, _values), prediction
                        in zip(selected_rows, predictions)
                    }

                    model_ready = True
                    model_name = (
                        "Isolation Forest + robust rolling z-score"
                    )

        except Exception:
            # Keep the statistical fallback available if ML is unavailable.
            model_ready = False
            isolation_flags = {}

    recent_start = as_of - timedelta(days=6)
    daily_candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for (region, observed_on), values in matrix_rows:
        if observed_on < recent_start or observed_on > as_of:
            continue

        drivers = []
        max_z = 0.0

        for metric, current_value in values.items():
            history = [
                value
                for day, value in metric_history[(region, metric)]
                if observed_on - timedelta(days=28) <= day < observed_on
            ]

            z_score, baseline, _scale = _robust_score(
                history,
                current_value,
                two_sided=(metric == "temperature_c"),
            )

            if z_score is None:
                continue

            max_z = max(max_z, z_score)

            if z_score >= 2.5:
                source, label, unit = FEATURE_META[metric]
                drivers.append({
                    "metric": metric,
                    "source": source,
                    "label": label,
                    "value": round(current_value, 2),
                    "baseline": round(baseline, 2),
                    "unit": unit,
                    "z_score": round(z_score, 2),
                })

        model_flag = isolation_flags.get(
            (region, observed_on),
            False,
        )

        # Explain a multivariate anomaly using the strongest observed drivers.
        if not drivers and model_flag:
            ranked = []

            for metric, current_value in values.items():
                history = [
                    value
                    for day, value in metric_history[(region, metric)]
                    if observed_on - timedelta(days=28) <= day < observed_on
                ]

                z_score, baseline, _scale = _robust_score(
                    history,
                    current_value,
                    two_sided=(metric == "temperature_c"),
                )

                if z_score is not None:
                    ranked.append(
                        (z_score, metric, current_value, baseline)
                    )

            for z_score, metric, current_value, baseline in sorted(
                ranked,
                reverse=True,
            )[:2]:
                if z_score < 1.0:
                    continue

                source, label, unit = FEATURE_META[metric]

                drivers.append({
                    "metric": metric,
                    "source": source,
                    "label": label,
                    "value": round(current_value, 2),
                    "baseline": round(baseline, 2),
                    "unit": unit,
                    "z_score": round(z_score, 2),
                })

                max_z = max(max_z, z_score)

        if not drivers:
            continue

        source_names = sorted({
            driver["source"]
            for driver in drivers
        })

        daily_candidates[region].append({
            "date": observed_on,
            "drivers": drivers,
            "sources": source_names,
            "max_z": max_z,
            "model_flag": model_flag,
            "demo_record": daily_demo[(region, observed_on)],
        })

    alerts = []
    risks = []

    all_regions = sorted({
        region
        for region, _day in daily_values
    })

    candidates_by_region = {
        region: sorted(
            items,
            key=lambda item: item["date"],
            reverse=True,
        )
        for region, items in daily_candidates.items()
    }

    for region in all_regions:
        items = candidates_by_region.get(region, [])
        latest_anomaly = items[0]["date"] if items else None

        # Multi-source confirmation uses the same rolling seven-day
        # review window displayed by the application.
        cluster_items = [
            item
            for item in items
            if latest_anomaly
            and 0 <= (latest_anomaly - item["date"]).days <= 6
        ]

        unique_drivers = {}
        unique_sources = set()

        for item in cluster_items:
            for driver in item["drivers"]:
                key = (driver["metric"], driver["source"])
                unique_drivers[key] = driver
                unique_sources.add(driver["source"])

        is_multi = len(unique_sources) >= 2

        max_z = max(
            (item["max_z"] for item in cluster_items),
            default=0.0,
        )

        model_flag = any(
            item["model_flag"]
            for item in cluster_items
        )

        drivers = sorted(
            unique_drivers.values(),
            key=lambda item: (-item["z_score"], item["source"]),
        )

        source_coverage = sorted({
            source
            for (record_region, observed_on), sources
            in daily_sources.items()
            if record_region == region
            and observed_on >= recent_start
            for source in sources
        })

        # Defaults are set independently for every region.
        level = "Belum terindikasi"
        risk_score = 0

        if items:
            level = (
                "Tinggi"
                if is_multi and (
                    max_z >= 3.5 or len(drivers) >= 3
                )
                else "Waspada"
            )

            # Heuristic score, not a calibrated probability.
            risk_score = min(
                100,
                round(
                    max_z * 12
                    + len(unique_sources) * 12
                    + (10 if model_flag else 0)
                ),
            )

            
            # Rekomendasi tindakan berdasarkan indikator penyumbang anomali.
            
            guidance = {
                "temperature_c": (
                    "Verifikasi sensor suhu, periksa ventilasi, "
                    "dan evaluasi paparan panas sesuai prosedur K3."
                ),
                "air_quality_index": (
                    "Verifikasi sensor kualitas udara dan periksa "
                    "kemungkinan sumber polutan di lingkungan."
                ),
                "absenteeism_rate": (
                    "Validasi rekap absensi agregat dan koordinasikan "
                    "pemeriksaan tren keluhan dengan petugas kesehatan "
                    "atau SDM."
                ),
                "workplace_incidents": (
                    "Verifikasi catatan insiden dan lakukan investigasi "
                    "K3 sesuai prosedur."
                ),
                "health_reports": (
                    "Verifikasi laporan kesehatan agregat dengan petugas "
                    "kesehatan serta periksa kemungkinan duplikasi laporan."
                ),
            }

            recommendations = list(dict.fromkeys(
                guidance[driver["metric"]]
                for driver in drivers
                if driver["metric"] in guidance
            ))


            recommendations = list(dict.fromkeys(
                guidance.get(
                    driver["metric"],
                    "Verifikasi indikator dengan pemilik data dan "
                    "petugas terkait sebelum mengambil tindakan.",
                )
                for driver in drivers[:6]
            ))[:4]

            
            alerts.append({
                "region": region,
                "date": latest_anomaly,
                "level": level,
                "risk_score": risk_score,
                "risk_score_type": "Heuristik",
                "score_note": (
                    "Skor heuristik untuk membantu prioritas peninjauan, "
                    "bukan probabilitas kejadian atau diagnosis kesehatan."
                ),
                "sources": sorted(unique_sources),
                "source_coverage": source_coverage,
                "drivers": drivers[:6],
                "max_z": round(max_z, 2),
                "model_flag": model_flag,
                "detection_method": (
                    "Isolation Forest + robust rolling z-score"
                    if model_flag
                    else "Robust rolling z-score"
                ),
                "is_multi_source": is_multi,
                "demo_record": any(
                    item["demo_record"]
                    for item in cluster_items
                ),
                "recommendations": recommendations[:5],
                "verification_note": (
                    "Temuan merupakan hasil analisis pola data agregat, "
                    "bukan diagnosis atau keputusan epidemiologis. "
                    "Verifikasi oleh petugas kesehatan dan/atau K3 "
                    "tetap diperlukan sebelum tindakan."
                ),
                "explanation": (
                    (
                        f"Anomali terindikasi pada {len(drivers)} indikator "
                        f"dari {len(unique_sources)} kelompok sumber dalam "
                        "jendela pemeriksaan tujuh hari. Sistem menggunakan "
                        "Isolation Forest untuk mendeteksi pola multivariat "
                        "dan robust rolling z-score untuk menjelaskan "
                        "indikator penyumbang."
                    )
                    if is_multi and model_flag
                    else (
                        f"Anomali terindikasi pada {len(drivers)} indikator "
                        f"dari {len(unique_sources)} kelompok sumber. "
                        "Indikator penyumbang perlu diperiksa dan "
                        "diverifikasi silang."
                    )
                    if is_multi
                    else (
                        "Pola menyimpang terdeteksi, tetapi bukti saat ini "
                        "masih berasal dari satu kelompok sumber. "
                        "Tambahkan verifikasi dari sumber lain."
                    )
                ),
            })


        risks.append({
            "region": region,
            "level": level,
            "risk_score": risk_score,
            "sources": source_coverage,
            "anomaly_count": len(items),
            "has_multi_source": is_multi if items else False,
            "last_anomaly": latest_anomaly,
            "demo_record": any(
                daily_demo[(record_region, observed_on)]
                for record_region, observed_on in daily_demo
                if record_region == region
            ),
        })

    alerts.sort(
        key=lambda item: (
            0 if item["level"] == "Tinggi" else 1,
            -item["risk_score"],
            item["region"],
        )
    )

    risks.sort(
        key=lambda item: (
            -item["risk_score"],
            item["region"],
        )
    )

    return {
        "alerts": alerts,
        "risks": risks,
        "model_name": model_name,
        "model_ready": model_ready,
        "observations": len(matrix_rows),
        "regions": len(all_regions),
    }
