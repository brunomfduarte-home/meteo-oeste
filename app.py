from datetime import datetime, time, timedelta
import re
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pydeck as pdk
import requests
from requests.adapters import HTTPAdapter
import streamlit as st
import streamlit.components.v1 as components
from urllib3.util.retry import Retry

st.set_page_config(
    page_title="Serviço Municipal de Proteção Civil de Óbidos - Análise Meteorológica",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def criar_sessao_http() -> requests.Session:
    sessao = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    sessao.mount("https://", adapter)
    sessao.mount("http://", adapter)
    sessao.headers.update({"User-Agent": "SMPC-Obidos-Meteo/1.0"})
    return sessao


SESSAO_HTTP = criar_sessao_http()

st.title("🛡️ Serviço Municipal de Proteção Civil de Óbidos - Inteligência Meteorológica")
st.markdown(
    "Painel tático de apoio à decisão operacional, boletim técnico multi-modelo (14 dias), "
    "comparação com eventos históricos adversos e emissão de avisos."
)


def extrair_coords_google_maps(url_gmaps: str):
    if not url_gmaps:
        return None, None
    padrao_at = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", url_gmaps)
    if padrao_at:
        return float(padrao_at.group(1)), float(padrao_at.group(2))
    padrao_q = re.search(r"[?&](?:q|ll)=(-?\d+\.\d+),(-?\d+\.\d+)", url_gmaps)
    if padrao_q:
        return float(padrao_q.group(1)), float(padrao_q.group(2))
    return None, None


def deg_para_direcao(deg):
    if pd.isna(deg):
        return "N/D"
    direcoes = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    ]
    val = int((deg / 22.5) + 0.5)
    return direcoes[val % 16]


def deg_para_seta(deg):
    if pd.isna(deg):
        return "⬆️"
    if 337.5 <= deg <= 360 or 0 <= deg < 22.5:
        return "⬇️ (N)"
    if 22.5 <= deg < 67.5:
        return "↙️ (NE)"
    if 67.5 <= deg < 112.5:
        return "⬅️ (E)"
    if 112.5 <= deg < 157.5:
        return "↖️ (SE)"
    if 157.5 <= deg < 202.5:
        return "⬆️ (S)"
    if 202.5 <= deg < 247.5:
        return "↗️ (SW)"
    if 247.5 <= deg < 292.5:
        return "➡️ (W)"
    if 292.5 <= deg < 337.5:
        return "↘️ (NW)"
    return "⬆️"


dias_semana_pt = {
    "Monday": "Segunda-feira",
    "Tuesday": "Terça-feira",
    "Wednesday": "Quarta-feira",
    "Thursday": "Quinta-feira",
    "Friday": "Sexta-feira",
    "Saturday": "Sábado",
    "Sunday": "Domingo",
}
dias_semana_curto = {
    "Monday": "Seg",
    "Tuesday": "Ter",
    "Wednesday": "Qua",
    "Thursday": "Qui",
    "Friday": "Sex",
    "Saturday": "Sáb",
    "Sunday": "Dom",
}
meses_pt = {
    "January": "janeiro",
    "February": "fevereiro",
    "March": "março",
    "April": "abril",
    "May": "maio",
    "June": "junho",
    "July": "julho",
    "August": "agosto",
    "September": "setembro",
    "October": "outubro",
    "November": "novembro",
    "December": "dezembro",
}


def formatar_data_pt(dt: datetime) -> str:
    dia_sem = dias_semana_pt.get(dt.strftime("%A"), dt.strftime("%A"))
    mes = meses_pt.get(dt.strftime("%B"), dt.strftime("%B"))
    return f"{dia_sem}, {dt.day} de {mes} de {dt.year} às {dt.strftime('%H:%M')}"


def formatar_intervalo_pico(dt_ini: datetime, dt_fim: datetime) -> str:
    return (
        f"das {dt_ini.strftime('%H:%M')}h de {dt_ini.strftime('%d/%m')} "
        f"às {dt_fim.strftime('%H:%M')}h de {dt_fim.strftime('%d/%m')}"
    )


EVENTOS_HISTORICOS_OBIDOS = [
    {
        "nome": "Furacão Leslie (Outubro 2018)",
        "tipo": "Eólico Extremo",
        "rajada_ref": 145.0,
        "chuva_1h_ref": 12.0,
        "chuva_24h_ref": 25.0,
        "setores_criticos": "Centro Histórico, Zonas Arborizadas, Rede Elétrica Aérea e Estruturas Temporárias",
        "impacto": "Queda generalizada de árvores de grande porte, cortes prolongados de energia e comunicações, destelhamentos na Vila e vias obstruídas.",
        "medidas": "Ativação preventiva do PMEPC, corte de acessos a zonas arborizadas, verificação de geradores críticos e equipas de desobstrução em prontidão.",
    },
    {
        "nome": "Tempestade Elsa & Fabien (Dezembro 2019)",
        "tipo": "Hidrológico & Eólico Severo",
        "rajada_ref": 102.0,
        "chuva_1h_ref": 18.0,
        "chuva_24h_ref": 62.0,
        "setores_criticos": "Bacia do Rio Arnóia, Barragem do Arnóia, Várzea da Rainha, Vau e Amoreira",
        "impacto": "Saturação total dos solos, galgamento das margens do Rio Arnóia, submersão de estradas municipais na várzea e deslizamentos de taludes.",
        "medidas": "Monitorização contínua de caudais do Rio Arnóia e descargas da barragem, sinalização de vias inundáveis e alerta às Juntas de Freguesia.",
    },
    {
        "nome": "Depressão Martinho / Ventos de Março (2025)",
        "tipo": "Eólico & Agitação Costeira",
        "rajada_ref": 112.0,
        "chuva_1h_ref": 14.0,
        "chuva_24h_ref": 32.0,
        "setores_criticos": "Litoral & Lagoa de Óbidos (Bom Sucesso, Vau), Centro Histórico",
        "impacto": "Queda de árvores e postes de iluminação, danos em coberturas ligeiras, galgamento costeiro e condicionamentos nas ligações à Lagoa.",
        "medidas": "Interdição de estacionamento junto a arvoredo e muralhas, reforço de fixação de estruturas exteriores e vigilância da barra da Lagoa.",
    },
    {
        "nome": "Episódios Convectivos Severos (Out–Dez 2022/2023)",
        "tipo": "Chuva Intensa / Inundação Urbana Rápida",
        "rajada_ref": 68.0,
        "chuva_1h_ref": 26.0,
        "chuva_24h_ref": 45.0,
        "setores_criticos": "Zonas Baixas da Vila, Arelho, Olho Marinho, A-dos-Negros e Eixos A8/EN8",
        "impacto": "Inundações urbanas rápidas (flash floods), sobrecarga do sistema de drenagem pluvial, lençóis de água nas estradas e inundação de caves.",
        "medidas": "Limpeza preventiva de sarjetas e sumidouros nos pontos críticos identificados, patrulhamento preventivo em pontos negros de drenagem.",
    },
    {
        "nome": "Nortada Severa / Vento Forte Seco de Norte",
        "tipo": "Vento Canalizado (Sem Chuva)",
        "rajada_ref": 82.0,
        "chuva_1h_ref": 0.0,
        "chuva_24h_ref": 0.0,
        "setores_criticos": "Centro Histórico (Cota Alta), Recintos de Eventos e Áreas Florestais (se época seca)",
        "impacto": "Queda de ramos secos, derrube de tendas/palcos ou estruturas não ancoradas e elevado risco de propagação de incêndios rurais.",
        "medidas": "Vistoria rigorosa a estruturas amovíveis de eventos e vigilância reforçada em zonas florestais.",
    },
]


def calcular_analogia_historica(pico_rajada: float, pico_chuva_1h: float, max_chuva_24h: float):
    melhor_evento = EVENTOS_HISTORICOS_OBIDOS[0]
    melhor_score = -1
    for ev in EVENTOS_HISTORICOS_OBIDOS:
        diff_r = abs(pico_rajada - ev["rajada_ref"]) / max(ev["rajada_ref"], 80.0)
        diff_c1 = abs(pico_chuva_1h - ev["chuva_1h_ref"]) / max(ev["chuva_1h_ref"], 15.0)
        diff_c24 = abs(max_chuva_24h - ev["chuva_24h_ref"]) / max(ev["chuva_24h_ref"], 30.0)
        distancia = (diff_r * 0.45) + (diff_c1 * 0.25) + (diff_c24 * 0.30)
        similaridade = max(15, min(98, int((1 - distancia) * 100)))
        if similaridade > melhor_score:
            melhor_score = similaridade
            melhor_evento = ev
    return melhor_evento, melhor_score


setores_obidos = {
    "🌍 Todo o Concelho (Consolidado)": {
        "lat": 39.3700,
        "lon": -9.1600,
        "perfil": "Visão global agregada de todo o território de Óbidos.",
        "polygon": [[-9.260, 39.340], [-9.080, 39.340], [-9.080, 39.415], [-9.260, 39.415]],
    },
    "🏛️ Centro Histórico (Vila / Cota Alta)": {
        "lat": 39.3607,
        "lon": -9.1572,
        "perfil": "Zona elevada e muralhada. Exposição direta a rajadas canalizadas.",
        "polygon": [[-9.175, 39.350], [-9.140, 39.350], [-9.140, 39.375], [-9.175, 39.375]],
    },
    "🌊 Litoral & Lagoa (Bom Sucesso / Vau)": {
        "lat": 39.3800,
        "lon": -9.2200,
        "perfil": "Zona estuarina e lagunar. Vulnerável a marés, vento atlântico e frentes costeiras.",
        "polygon": [[-9.260, 39.340], [-9.185, 39.340], [-9.185, 39.410], [-9.260, 39.410]],
    },
    "🌾 Interior & Bacia do Arnóia (A-dos-Negros / Olho Marinho)": {
        "lat": 39.3700,
        "lon": -9.1300,
        "perfil": "Zona de vales aluviais. Suscetível a retenção de humidade e cheias de bacia.",
        "polygon": [[-9.150, 39.355], [-9.080, 39.355], [-9.080, 39.415], [-9.150, 39.415]],
    },
    "📍 Ponto Específico (Google Maps / Coordenadas)": {
        "lat": 39.3607,
        "lon": -9.1572,
        "perfil": "Coordenadas geográficas personalizadas definidas pelo utilizador.",
        "polygon": [],
    },
}

st.sidebar.header("⚙️ Parâmetros de Análise Global")
if st.sidebar.button("🔄 Forçar Atualização Agora"):
    st.cache_data.clear()
    st.rerun()

setor_selecionado = st.sidebar.selectbox("Selecionar Setor / Vista", list(setores_obidos.keys()))

if "lat_clicada" not in st.session_state:
    st.session_state.lat_clicada = 39.3607
if "lon_clicada" not in st.session_state:
    st.session_state.lon_clicada = -9.1572

if setor_selecionado == "📍 Ponto Específico (Google Maps / Coordenadas)":
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📍 Localização Personalizada")
    url_gmaps = st.sidebar.text_input(
        "Link do Google Maps (URL completo):",
        placeholder="https://www.google.com/maps/@39.3607,-9.1572,15z",
    )
    lat_ext, lon_ext = extrair_coords_google_maps(url_gmaps)
    if lat_ext and lon_ext:
        st.session_state.lat_clicada = lat_ext
        st.session_state.lon_clicada = lon_ext
        st.sidebar.success(f"Coordenadas extraídas: {lat_ext:.4f}, {lon_ext:.4f}")
    lat_custom = st.sidebar.number_input("Latitude", value=st.session_state.lat_clicada, format="%.4f")
    lon_custom = st.sidebar.number_input("Longitude", value=st.session_state.lon_clicada, format="%.4f")
    nome_ponto_custom = st.sidebar.text_input("Nome/Ref. do Ponto", value="Ponto Específico")
    lat_analise, lon_analise = lat_custom, lon_custom
    setores_obidos["📍 Ponto Específico (Google Maps / Coordenadas)"]["lat"] = lat_custom
    setores_obidos["📍 Ponto Específico (Google Maps / Coordenadas)"]["lon"] = lon_custom
    setores_obidos["📍 Ponto Específico (Google Maps / Coordenadas)"]["perfil"] = (
        f"Análise focada em {nome_ponto_custom} ({lat_custom:.4f}, {lon_custom:.4f})."
    )
else:
    info_setor = setores_obidos[setor_selecionado]
    lat_analise, lon_analise = info_setor["lat"], info_setor["lon"]

dias_historico = st.sidebar.slider("Dias de Calibração (Passado)", min_value=1, max_value=5, value=2)
dias_previsao = st.sidebar.slider("Dias de Previsão (Meteograma)", min_value=1, max_value=7, value=5)


@st.cache_data(ttl=1800, show_spinner=False)
def obter_dados_cruzados(lat: float, lon: float, past: int, forecast: int) -> pd.DataFrame:
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}&past_days={past}&forecast_days={forecast}"
        f"&models=ecmwf_ifs025&hourly=precipitation,wind_speed_10m,wind_gusts_10m,"
        f"wind_direction_10m,temperature_2m,surface_pressure,relative_humidity_2m"
    )
    try:
        res = SESSAO_HTTP.get(url, timeout=(10, 45))
        res.raise_for_status()
        data = res.json()
        h = data.get("hourly", {})
        if not h.get("time"):
            return pd.DataFrame()
        return pd.DataFrame(
            {
                "Hora": pd.to_datetime(h["time"]),
                "Precipitação (mm)": h["precipitation"],
                "Vento (km/h)": h["wind_speed_10m"],
                "Rajada (km/h)": h["wind_gusts_10m"],
                "Direção Vento (°)": h["wind_direction_10m"],
                "Temperatura (°C)": h["temperature_2m"],
                "Pressão (hPa)": h["surface_pressure"],
                "Humidade (%)": h["relative_humidity_2m"],
            }
        )
    except requests.exceptions.RequestException as exc:
        st.session_state["ultimo_erro_api"] = str(exc)
        return pd.DataFrame()


@st.cache_data(ttl=1800, show_spinner=False)
def obter_boletim_multimodelo_14d(lat: float, lon: float) -> pd.DataFrame:
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}&forecast_days=14"
        f"&models=ecmwf_ifs025,gfs_seamless,icon_seamless"
        f"&hourly=precipitation,wind_speed_10m,wind_gusts_10m,wind_direction_10m,temperature_2m,relative_humidity_2m"
    )
    try:
        res = SESSAO_HTTP.get(url, timeout=(10, 45))
        res.raise_for_status()
        data = res.json()
        h = data.get("hourly", {})
        if not h.get("time"):
            return pd.DataFrame()
        df_m = pd.DataFrame({"Hora": pd.to_datetime(h["time"])})
        mapa_colunas = {
            "temperature_2m_ecmwf_ifs025": "Temp_ECMWF",
            "temperature_2m_gfs_seamless": "Temp_GFS",
            "temperature_2m_icon_seamless": "Temp_ICON",
            "precipitation_ecmwf_ifs025": "Chuva_ECMWF",
            "precipitation_gfs_seamless": "Chuva_GFS",
            "precipitation_icon_seamless": "Chuva_ICON",
            "wind_gusts_10m_ecmwf_ifs025": "Rajada_ECMWF",
            "wind_gusts_10m_gfs_seamless": "Rajada_GFS",
            "wind_gusts_10m_icon_seamless": "Rajada_ICON",
            "wind_speed_10m_ecmwf_ifs025": "Vento_ECMWF",
            "wind_direction_10m_ecmwf_ifs025": "Dir_ECMWF",
            "relative_humidity_2m_ecmwf_ifs025": "HR_ECMWF",
        }
        for col_api, col_dest in mapa_colunas.items():
            df_m[col_dest] = h.get(col_api, np.nan)
        return df_m
    except requests.exceptions.RequestException as exc:
        st.session_state["ultimo_erro_api"] = str(exc)
        return pd.DataFrame()


with st.spinner("A recolher dados meteorológicos do Open-Meteo..."):
    if setor_selecionado == "🌍 Todo o Concelho (Consolidado)":
        sub_chaves = [
            k
            for k in setores_obidos
            if k not in ["🌍 Todo o Concelho (Consolidado)", "📍 Ponto Específico (Google Maps / Coordenadas)"]
        ]
        dfs = []
        for sk in sub_chaves:
            df_sub = obter_dados_cruzados(
                setores_obidos[sk]["lat"],
                setores_obidos[sk]["lon"],
                dias_historico,
                dias_previsao,
            )
            if not df_sub.empty:
                dfs.append(df_sub.set_index("Hora"))
        df = pd.concat(dfs).groupby("Hora").mean().reset_index() if dfs else pd.DataFrame()
    else:
        df = obter_dados_cruzados(lat_analise, lon_analise, dias_historico, dias_previsao)

    df_14d = obter_boletim_multimodelo_14d(lat_analise, lon_analise)

if df.empty:
    st.warning(
        "⚠️ A API Open-Meteo excedeu o tempo limite de resposta ou está temporariamente indisponível. "
        "Clique em **Forçar Atualização Agora** na barra lateral dentro de alguns segundos."
    )
    if "ultimo_erro_api" in st.session_state:
        st.caption(f"Detalhe técnico: {st.session_state['ultimo_erro_api']}")
    st.stop()

agora = datetime.now()
df_passado = df[df["Hora"] <= agora]
df_futuro = df[df["Hora"] > agora]

pico_r = df_futuro["Rajada (km/h)"].max() if not df_futuro.empty else df["Rajada (km/h)"].max()
idx_r = (df_futuro if not df_futuro.empty else df)["Rajada (km/h)"].idxmax()
hora_r = df.loc[idx_r, "Hora"]
dir_r = df.loc[idx_r, "Direção Vento (°)"]

pico_c = df_futuro["Precipitação (mm)"].max() if not df_futuro.empty else df["Precipitação (mm)"].max()
idx_c = (df_futuro if not df_futuro.empty else df)["Precipitação (mm)"].idxmax()
hora_c = df.loc[idx_c, "Hora"]

max_chuva_24h = (
    df_futuro["Precipitação (mm)"].rolling(24, min_periods=1).sum().max()
    if not df_futuro.empty
    else df["Precipitação (mm)"].rolling(24, min_periods=1).sum().max()
)

if not df_passado.empty and len(df_passado) > 10:
    estabilidade_vento = df_passado["Vento (km/h)"].std()
    confianca = max(70, min(95, int(98 - estabilidade_vento * 1.5)))
else:
    confianca = 88

seta_vento_str = deg_para_seta(dir_r)
cardeal_vento_str = deg_para_direcao(dir_r)

if pico_r > 110 or pico_c > 35:
    nivel, icone_ipma, cor_hex = "VERMELHO", "🔴", "#FF0000"
elif pico_r > 90 or pico_c > 20:
    nivel, icone_ipma, cor_hex = "LARANJA", "🟠", "#FF8C00"
elif pico_r > 70 or pico_c > 10:
    nivel, icone_ipma, cor_hex = "AMARELO", "🟡", "#FFD700"
else:
    nivel, icone_ipma, cor_hex = "VERDE", "🟢", "#008000"

st.markdown(
    "<div style='border-bottom: 4px solid " + cor_hex + "; padding-bottom: 8px; margin-bottom: 16px;'>"
    "<h3>" + icone_ipma + " ESTADO DE ALERTA (CENÁRIO MAIS GRAVOSO): <span style='color: " + cor_hex + ";'>" + nivel + "</span> | "
    "Vista: " + setor_selecionado + " | Confiança ECMWF: <b>" + str(confianca) + "%</b> | "
    "Última atualização: " + agora.strftime("%H:%M") + "</h3></div>",
    unsafe_allow_html=True,
)

st.subheader("📌 Resumo Executivo, Períodos de Pico & Limiares IPMA")
col_c1, col_c2, col_c3, col_tabela = st.columns([1.1, 1.1, 1.1, 1.7])

h_ini_c, h_fim_c = hora_c - timedelta(hours=1), hora_c + timedelta(hours=1)
h_ini_r, h_fim_r = hora_r - timedelta(hours=1), hora_r + timedelta(hours=1)

with col_c1:
    st.markdown(
        "<div style='background-color: #f8f9fa; padding: 14px; border-radius: 10px; border-left: 6px solid #3399ff;'>"
        "<div style='font-size: 12px; font-weight: bold; color: #555;'>🌧️ PRECIPITAÇÃO MÁX. (1H)</div>"
        "<div style='font-size: 26px; font-weight: 800; color: #1f77b4; margin: 4px 0;'>" + f"{pico_c:.1f}" + " <span style='font-size: 13px;'>mm/h</span></div>"
        "<div style='font-size: 11px; color: #333;'>🕒 " + formatar_intervalo_pico(h_ini_c, h_fim_c) + "</div></div>",
        unsafe_allow_html=True,
    )
with col_c2:
    st.markdown(
        "<div style='background-color: #f8f9fa; padding: 14px; border-radius: 10px; border-left: 6px solid #0055aa;'>"
        "<div style='font-size: 12px; font-weight: bold; color: #555;'>💧 ACUMULADO MÁX. (24H)</div>"
        "<div style='font-size: 26px; font-weight: 800; color: #0055aa; margin: 4px 0;'>" + f"{max_chuva_24h:.1f}" + " <span style='font-size: 13px;'>mm/24h</span></div>"
        "<div style='font-size: 11px; color: #333;'>📊 Saturação de solo / Bacia Arnóia</div></div>",
        unsafe_allow_html=True,
    )
with col_c3:
    st.markdown(
        "<div style='background-color: #f8f9fa; padding: 14px; border-radius: 10px; border-left: 6px solid #d62728;'>"
        "<div style='font-size: 12px; font-weight: bold; color: #555;'>💨 RAJADA MÁX. & DIREÇÃO</div>"
        "<div style='font-size: 26px; font-weight: 800; color: #d62728; margin: 4px 0;'>" + f"{pico_r:.1f}" + " <span style='font-size: 13px;'>km/h</span> <span style='font-size: 18px;'>" + seta_vento_str + "</span></div>"
        "<div style='font-size: 11px; color: #333;'>🕒 " + formatar_intervalo_pico(h_ini_r, h_fim_r) + "</div></div>",
        unsafe_allow_html=True,
    )
with col_tabela:
    st.markdown(
        "<div style='background-color: #f8f9fa; padding: 11px; border-radius: 10px; border: 1px solid #e0e0e0; font-size: 12px;'>"
        "<b>📋 Critérios de Aviso IPMA (Referência):</b>"
        "<table style='width:100%; margin-top:4px; font-size:11px; border-collapse: collapse;'>"
        "<tr style='background:#eef2f5;'><th style='text-align:left; padding:3px;'>Parâmetro</th><th style='padding:3px;'>🟡 Amarelo</th><th style='padding:3px;'>🟠 Laranja</th><th style='padding:3px;'>🔴 Vermelho</th></tr>"
        "<tr><td><b>Rajadas Vento</b></td><td>70
