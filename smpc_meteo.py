"""Reanálise de Óbidos. Só recolhe, avalia e guarda dados; não envia mensagens."""
import argparse
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

UTC = timezone.utc
H = timedelta(hours=1)
LISBON = ZoneInfo("Europe/Lisbon")
IPMA = "https://api.ipma.pt/open-data/forecast/warnings/warnings_www.json"
CRITERIOS = "https://www.ipma.pt/pt/enciclopedia/otempo/sam/index.html?page=criterios.xml"
LAT, LON = 39.36, -9.16
LIMITS = {"Rajada": ("km/h", 70, 91, 130), "Chuva 1h": ("mm/1h", 10, 21, 40),
          "Chuva 6h": ("mm/6h", 30, 41, 60)}
LEVELS = ["Sem sinal", "Amarelo", "Laranja", "Vermelho"]
OFFICIAL = {"yellow": "Amarelo", "orange": "Laranja", "red": "Vermelho"}
ICONS = {"Amarelo": "🟡", "Laranja": "🟠", "Vermelho": "🔴"}
SOURCES = {
    "GFS": ("forecast", "ncep_gfs_global", False),
    "ECMWF": ("forecast", "ecmwf_ifs025", False),
    "NOAA GEFS": ("ensemble", "ncep_gefs025", True),
    "ECMWF ENS": ("ensemble", "ecmwf_ifs025_ensemble", True),
}
N_EXPECTED = {"NOAA GEFS": 31, "ECMWF ENS": 51}


def dt(x):
    t = datetime.fromisoformat(x)
    return t.astimezone(UTC) if t.tzinfo else t.replace(tzinfo=UTC)


def local(x):
    return dt(x).astimezone(LISBON).strftime("%d/%m %H:%M %Z")


def get_json(url, headers=None):
    with urlopen(Request(url, headers={"User-Agent": "SMPC-Obidos-meteo/1.0", **(headers or {})}),
                 timeout=20) as response:
        return json.load(response)


def warnings(now):
    raw = get_json(IPMA)
    if not isinstance(raw, list) or any(not isinstance(x, dict) or
                                       "idAreaAviso" not in x for x in raw):
        raise ValueError("Formato inesperado dos avisos IPMA")
    found = {}
    for row in raw:
        if row["idAreaAviso"] != "LRA":
            continue
        severity = row.get("awarenessLevelID")
        if severity == "green":
            continue
        if severity not in OFFICIAL or not row.get("awarenessTypeName"):
            raise ValueError("Aviso IPMA de Leiria sem nível ou fenómeno reconhecível")
        start, end = dt(row["startTime"]), dt(row["endTime"])
        if end <= start:
            raise ValueError("Validade IPMA inválida")
        if end <= now:
            continue
        alert = {"level": OFFICIAL[severity], "phenomenon": row["awarenessTypeName"],
                 "start": start.isoformat(), "end": end.isoformat(), "description": row.get("text") or "",
                 "issued": row.get("issuedAt")}
        found[warning_key(alert)] = alert
    return [found[k] for k in sorted(found)]


def warning_key(a):
    return (a["phenomenon"], a["level"], a["start"], a["end"], a["description"])


def level(metric, value):
    _, yellow, orange, red = LIMITS[metric]
    return 3 if value > red else 2 if value >= orange else 1 if value >= yellow else 0


def finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def load_model(name):
    service, model, ensemble = SOURCES[name]
    host = "api" if service == "forecast" else "ensemble-api"
    url = f"https://{host}.open-meteo.com/v1/{service}?" + urlencode({
        "latitude": LAT, "longitude": LON, "models": model, "timezone": "GMT",
        "past_days": 1, "forecast_days": 9, "hourly": "precipitation,wind_gusts_10m",
        "wind_speed_unit": "kmh", "precipitation_unit": "mm",
    })
    data = get_json(url)
    hourly = data["hourly"]
    times = [dt(t) for t in hourly["time"]]
    if len(set(times)) != len(times) or sorted(times) != times or not times:
        raise ValueError("Validades inválidas")
    series = {"precipitation": {}, "wind_gusts_10m": {}}
    for base, collection in series.items():
        units = data["hourly_units"]
        expected = "mm" if base == "precipitation" else "km/h"
        for key, vals in hourly.items():
            match = re.fullmatch(re.escape(base) + r"(?:_member(\d+))?", key)
            if not match or len(vals) != len(times) or units.get(key) != expected:
                continue
            member = int(match.group(1) or 0)
            if ensemble and member >= N_EXPECTED[name]:
                continue
            collection[member] = {t: float(v) for t, v in zip(times, vals) if finite(v) and v >= 0}
    if not any(series.values()):
        raise ValueError("Nenhuma variável válida")
    return series


def samples(metric, series, start, end):
    for t, v in series.items():
        duration = 6 if metric == "Chuva 6h" else 1
        if not start <= t - duration * H or t > end:
            continue
        if duration == 6:
            # Janela UTC alinhada com as saídas nativas de 3/6 h; não soma períodos sobrepostos.
            if t.hour % 6:
                continue
            values = [series.get(t - i * H) for i in range(6)]
            if any(x is None for x in values):
                continue
            v = sum(values)
        yield (v, t - duration * H, t)


def summarize(name, series, start, end, group):
    rows = []
    ensemble = SOURCES[name][2]
    for metric in LIMITS:
        if metric == "Chuva 1h" and (ensemble or name == "ECMWF" or group == "+72 a +168 h"):
            continue  # a grelha horária interpolada não resolve extremos de 1 h
        var = "wind_gusts_10m" if metric == "Rajada" else "precipitation"
        member_peaks = []
        for values in series[var].values():
            valid = list(samples(metric, values, start, end))
            expected = (sum(1 for i in range(6, int((end-start)/H)+1)
                            if (start+i*H).hour % 6 == 0)
                        if metric == "Chuva 6h" else int((end-start)/H))
            if valid and (not ensemble or len(valid) == expected):
                member_peaks.append(max(valid, key=lambda x: x[0]))
        if not member_peaks:
            continue
        if ensemble:
            n, N = len(member_peaks), N_EXPECTED[name]
            if n < math.ceil(N * 0.8):
                rows.append({"source": name, "window": group, "metric": metric, "n": n,
                             "N": N, "probability": None})
                continue
            probabilities = {LEVELS[k]: sum(level(metric, x[0]) >= k for x in member_peaks)
                             for k in (1, 2, 3)}
            rows.append({"source": name, "window": group, "metric": metric, "n": n,
                         "N": N, "probability": probabilities})
        else:
            value, t0, t1 = member_peaks[0]
            rows.append({"source": name, "window": group, "metric": metric,
                         "value": round(value, 2), "level": level(metric, value),
                         "start": t0.isoformat(), "end": t1.isoformat()})
    return rows


def material(previous, report):
    changes = []
    prior = previous.get("last_valid_warnings")
    if report["warnings"] is not None:
        new = {warning_key(a): a for a in report["warnings"]}
        old = {warning_key(a): a for a in prior or []}
        for k in new.keys() - old.keys():
            if prior is not None or new[k]["level"] in {"Laranja", "Vermelho"}:
                changes.append(f"IPMA: {new[k]['level']} · {new[k]['phenomenon']} · "
                               f"{local(new[k]['start'])}–{local(new[k]['end'])}")
        for k in old.keys() - new.keys():
            if dt(old[k]["end"]) > dt(report["generatedAt"]):
                changes.append(f"IPMA: aviso anterior alterado ou retirado · {old[k]['phenomenon']} · "
                               f"{local(old[k]['start'])}–{local(old[k]['end'])}")
    for metric in LIMITS:
        current = report["signal_baseline"].get(metric)
        before = previous.get("signal_baseline", {}).get(metric)
        if not current or current == before:
            continue
        if current["level"] >= 2 and (not before or before["level"] != current["level"]
                or abs(dt(current["end"]) - dt(before["end"])) >= 3*H):
            changes.append(f"Previsão: {metric} · sinal concordante · {local(current['end'])}")
    return sorted(set(changes))


def run(previous, now=None):
    now = now or datetime.now(UTC)
    hour = now.replace(minute=0, second=0, microsecond=0)
    # Inclui a hora em curso; os gráficos representam intervalos, não observações.
    windows = [("0–6 h", 0, 6), ("0–24 h", 0, 24), ("24–48 h", 24, 48),
               ("48–72 h", 48, 72)]
    extended_slot = hour.astimezone(LISBON).hour in {0, 6, 12, 18}
    extended = extended_slot or not previous.get("extendedAt")
    if extended:
        windows.append(("+72 a +168 h", 72, 168))
    active = list(SOURCES)
    issues, rows = {}, []
    with ThreadPoolExecutor(max_workers=5) as pool:
        ipma = pool.submit(warnings, now)
        pending = {name: pool.submit(load_model, name) for name in active}
        try:
            official = ipma.result()
        except Exception as error:
            official = None
            issues["IPMA"] = str(error)
        for name, future in pending.items():
            try:
                data = future.result()
                groups = windows
                result = [row for group, a, b in groups
                          for row in summarize(name, data, hour+a*H, hour+b*H, group)]
                if not result:
                    raise ValueError("Sem amostras válidas nas janelas analisadas")
                rows.extend(result)
            except Exception as error:
                issues[name] = str(error)
    signals = dict(previous.get("signal_baseline", {}))
    for metric in ("Rajada", "Chuva 6h"):
        picks = {name: next((r for r in rows if r["source"] == name and r["metric"] == metric
                             and r["window"] == "0–24 h"), None) for name in ("GFS", "ECMWF")}
        if all(picks.values()):
            a, b = picks.values()
            agreed = min(a["level"], b["level"]) if abs(dt(a["end"]) - dt(b["end"])) <= 3*H else 0
            signals[metric] = {"level": agreed, "end": a["end"]}
    report = {"generatedAt": now.isoformat(), "anchor": hour.isoformat(), "warnings": official,
              "last_valid_warnings": official if official is not None else previous.get("last_valid_warnings"),
              "issues": issues, "rows": rows, "signal_baseline": signals,
              "extendedAt": now.isoformat() if extended else previous.get("extendedAt"),
              "extendedRows": [r for r in rows if r["window"] == "+72 a +168 h"]
                              if extended else previous.get("extendedRows", []),
              "extendedIssues": issues if extended else previous.get("extendedIssues", {})}
    report["changes"] = material(previous, report)
    before = previous.get("last_valid_warnings") or []
    live_keys = {warning_key(w) for w in official or []}
    report["withdrawn"] = [w for w in before if official is not None and
                           warning_key(w) not in live_keys and dt(w["end"]) > now]
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--previous", default="snapshot.json")
    parser.add_argument("--output", default="snapshot.json")
    args = parser.parse_args()
    previous = Path(args.previous)
    result = run(json.loads(previous.read_text()) if previous.exists() else {})
    output = Path(args.output)
    temp = output.with_suffix(".tmp")
    temp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(output)
    print(f'{result["generatedAt"]}: {len(result["rows"])} resultados; '
          f'{len(result["changes"])} sinais para revisão; fontes com falha: {", ".join(result["issues"]) or "nenhuma"}')


if __name__ == "__main__":
    main()
