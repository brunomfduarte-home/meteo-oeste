import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import re

import streamlit as st

from smpc_meteo import CRITERIOS, ICONS, LEVELS, LIMITS, dt, get_json, local

st.set_page_config(page_title="Meteorologia · SMPC Óbidos", page_icon="🌦️", layout="wide")
st.title("🌦️ Meteorologia · SMPC Óbidos")
st.caption("Painel de apoio à decisão · Hora de Portugal continental · Mensagens para validação")
WARN_URL = "https://www.ipma.pt/pt/otempo/prev-sam/"


@st.cache_data(ttl=120, show_spinner=False)
def read_snapshot(repo, _token):
    if repo:
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
            raise ValueError("SMPC_REPO deve ter a forma dono/repositorio")
        if _token:
            return get_json(f"https://api.github.com/repos/{repo}/contents/snapshot.json?ref=meteo-data",
                            {"Accept": "application/vnd.github.raw+json", "Authorization": f"Bearer {_token}"})
        return get_json(f"https://raw.githubusercontent.com/{repo}/meteo-data/snapshot.json")
    return json.loads(Path("snapshot.json").read_text(encoding="utf-8"))


def setting(key):
    if os.getenv(key):
        return os.environ[key]
    try:
        return st.secrets.get(key, "")
    except FileNotFoundError:
        return ""


@st.fragment(run_every="5m")
def panel():
    if st.button("↻ Verificar atualização"):
        read_snapshot.clear()
    try:
        report = read_snapshot(setting("SMPC_REPO"), setting("SMPC_GITHUB_TOKEN"))
        age = datetime.now(timezone.utc) - dt(report["generatedAt"])
    except (OSError, ValueError, KeyError):
        st.error("Ainda não foi possível ler uma análise. Verifique a execução em GitHub Actions e SMPC_REPO.")
        st.stop()
    st.caption(f"Reanálise: {local(report['generatedAt'])} · Critérios configurados: 08/11/2026 · "
               "Ciclos dos modelos: não indicados pelo endpoint.")
    st.markdown(f"[Critérios IPMA]({CRITERIOS}) · [Avisos IPMA]({WARN_URL}) · "
                "[Open-Meteo — modelos](https://open-meteo.com/en/docs)")
    stale = age > timedelta(minutes=95) or age < timedelta(minutes=-5)
    if stale:
        st.warning("Análise fora do prazo esperado. Consulte diretamente o IPMA. Rascunhos bloqueados.")

    warnings = report["warnings"]
    st.subheader("Avisos oficiais IPMA · Distrito de Leiria")
    active = []
    if warnings is None:
        st.warning("Avisos indisponíveis nesta execução.")
    else:
        active = [w for w in warnings if dt(w["end"]) > datetime.now(timezone.utc)]
        if not active:
            st.caption("Sem avisos atuais ou futuros na resposta consultada. Consulte a fonte para confirmação.")
        for w in active:
            st.markdown(f"**{ICONS[w['level']]} {w['level']} · {w['phenomenon']}**")
            st.write(f"{local(w['start'])} → {local(w['end'])} · Emissão: {w['issued'] or 'não indicada no feed'}")
            if w["description"]:
                st.write(w["description"])


    ADVICE = {
        "Rajada": ("Possíveis quedas de ramos e deslocação de objetos ou estruturas leves.",
                   "Recolha objetos soltos e evite zonas arborizadas durante as rajadas.",
                   "Confirme os limites do fabricante para tendas e palcos; reveja o plano de suspensão."),
        "Chuva 1h": ("Possível acumulação rápida de água em ruas e passagens baixas.",
                     "Evite atravessar vias inundadas e ajuste o trajeto.",
                     "Verifique escoamento, acessos e abrigos; reveja o plano de interrupção."),
        "Chuva 6h": ("Possível acumulação de água em zonas baixas e condicionamentos nas vias.",
                     "Evite atravessar vias inundadas e acompanhe a informação oficial.",
                     "Verifique drenagem, acessos e abrigos; reveja o plano de interrupção."),
    }


    def peak_text(row):
        unit = LIMITS[row["metric"]][0]
        return (f"{row['source']}: {row['value']:g} {unit} · "
                f"{local(row['start'])} → {local(row['end'])}")


    def message(metric, row, audience):
        effects, protect, event = ADVICE[metric]
        risk = LEVELS[row["level"]]
        label = f"{ICONS.get(risk, 'ℹ️')} Previsão · {metric} · Óbidos"
        lines = [label, f"Atualização: {local(report['generatedAt'])}",
                 f"🕒 Pico estimado: {local(row['start'])}–{local(row['end'])} · "
                 f"{row['value']:g} {LIMITS[metric][0]} ({row['source']}).",
                 f"⚠️ {effects}",
                 f"✅ {event if audience == 'eventos' else protect}",
                 f"📡 Pico estimado por modelo; hora e intensidade podem variar. Avisos IPMA: {WARN_URL}"]
        category = "vento" if metric == "Rajada" else "precipita"
        matching = [w for w in active if category in w["phenomenon"].lower()
                    and dt(w["start"]) < dt(row["end"]) and dt(w["end"]) > dt(row["start"])]
        if warnings is None:
            lines.append("Estado oficial indisponível no painel; confirme na fonte.")
        elif matching:
            lines.extend(f"IPMA (Leiria): {w['level']} · {w['phenomenon']} · "
                         f"{local(w['start'])}–{local(w['end'])}." for w in matching)
        else:
            lines.append("Sem aviso IPMA correspondente ao pico no feed consultado.")
        for e in report["rows"]:
            if (e["window"] == "0–24 h" and e["metric"] == metric and
                    "probability" in e and e["probability"] is not None):
                k = e["probability"][risk]
                lines.append(f"{e['source']}: {k}/{e['n']} membros ({k/e['n']:.0%}) atingem o limiar "
                             f"de referência {risk.lower()} em algum momento da janela de 24 h.")
        return "\n".join(lines)


    def table(rows):
        data = []
        for r in rows:
            if "value" in r:
                result = peak_text(r)
                note = " / ".join((ICONS.get(LEVELS[r["level"]], ""), LEVELS[r["level"]])).strip(" /")
            else:
                result = f"{r['n']}/{r['N']} membros válidos"
                p = r["probability"]
                note = "Não quantificável" if p is None else "; ".join(
                    f"{k}: {x}/{r['n']} ({x/r['n']:.0%})" for k,x in p.items())
            data.append({"Janela": r["window"], "Fenómeno": r["metric"], "Fonte": r["source"],
                         "Pico / amostra": result, "Sinal / frequência no ensemble": note})
        if data:
            st.dataframe(data, hide_index=True)
        else:
            st.info("Dados insuficientes para esta janela.")


    tech, public, events = st.tabs(["🧭 Técnicos SMPC", "🏠 População", "🎪 Eventos ao ar livre"])
    short = [r for r in report["rows"] if r["window"] != "+72 a +168 h"]
    with tech:
        st.subheader("Alterações detetadas para revisão")
        for change in report["changes"]:
            st.write(change)
        if not report["changes"]:
            st.caption("Sem alteração detetada pelas regras implementadas.")
        st.caption("A janela 0–6 h é previsão. Este pacote não confirma nowcast com radar, estações, satélite ou descargas.")
        table(short)
        if report["changes"] and not stale:
            draft = (f"🧭 SMPC Óbidos · {local(report['generatedAt'])}\n" +
                     "\n".join(report["changes"]) +
                     f"\nConfirmar validade, exposição local e medidas. Fonte oficial: {WARN_URL}")
            st.text_area("Rascunho técnico · WhatsApp / Telegram", draft, height=180)
        st.subheader("Cenários a 3–7 dias")
        stamp = report.get("extendedAt")
        if stamp:
            st.caption(f"Última avaliação alargada: {local(stamp)}. Percentagens: membros válidos que atingem o limiar.")
            if datetime.now(timezone.utc) - dt(stamp) > timedelta(hours=7):
                st.warning("Avaliação alargada antiga.")
        table(report.get("extendedRows", []))
        for name in sorted(set(report["issues"]) | set(report.get("extendedIssues", {}))):
            st.warning(f"{name}: dados indisponíveis numa das últimas avaliações; consultar o registo da execução.")

    for tab, audience in [(public, "população"), (events, "eventos")]:
        with tab:
            st.subheader("Picos previstos para as próximas 24 horas")
            options = [r for r in short if r["window"] == "0–24 h" and "value" in r and r["level"] > 0
                       and dt(r["end"]) > datetime.now(timezone.utc)]
            for row in sorted(options, key=lambda r: (-r["level"], r["end"])):
                st.markdown(f"**{ICONS[LEVELS[row['level']]]} Sinal de modelo · {row['metric']} · {peak_text(row)}**")
                effects, protect, event = ADVICE[row["metric"]]
                st.write(effects)
                st.write(event if audience == "eventos" else protect)
            if not options:
                st.caption("Sem pico acima dos limiares calculados nos dados disponíveis.")
            if options and not stale:
                selected = st.selectbox("Pico para o rascunho", options, key=audience,
                                        format_func=lambda r: f"{r['metric']} · {peak_text(r)}")
                draft = message(selected["metric"], selected, audience)
                st.text_area("Rascunho para WhatsApp / Telegram · validar antes de usar",
                             value=draft, height=240)
                st.download_button("Descarregar texto", draft, f"meteo-{audience}.txt")

            if (active or report.get("withdrawn")) and not stale:
                choices = [(w, False) for w in active] + [(w, True) for w in report.get("withdrawn", [])]
                w, removed = st.selectbox("Aviso IPMA ou atualização", choices, key=f"official-{audience}",
                    format_func=lambda item: ("Anterior · " if item[1] else "") +
                    f"{item[0]['level']} · {item[0]['phenomenon']} · {local(item[0]['start'])}")
                header = ("ℹ️ Atualização de aviso anterior" if removed else
                          f"{ICONS[w['level']]} Aviso IPMA {w['level']}")
                text = [f"{header} · {w['phenomenon']} · Leiria / Óbidos",
                        f"Atualização: {local(report['generatedAt'])}.",
                        f"Validade {'anterior' if removed else 'indicada'}: {local(w['start'])}–{local(w['end'])}."]
                if removed:
                    text.append("O aviso anterior já não consta com os mesmos dados. Consulte os avisos em vigor antes de alterar medidas.")
                else:
                    p = w["phenomenon"].lower()
                    metric = "Rajada" if "vento" in p else "Chuva 6h" if "precipita" in p else None
                    if w["description"]:
                        text.append(w["description"])
                    if metric:
                        effects, protect, event = ADVICE[metric]
                        text += [f"⚠️ {effects}", f"✅ {event if audience == 'eventos' else protect}"]
                    else:
                        text.append("✅ Siga as indicações da Proteção Civil e confirme as medidas para este fenómeno.")
                text.append(f"Fonte: IPMA · {WARN_URL}")
                st.text_area("Rascunho de aviso ou atualização · validar antes de usar", "\n".join(text), height=220,
                             key=f"draft-{audience}-{w['start']}-{w['level']}-{removed}")


panel()
