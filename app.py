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
        "<tr><td><b>Rajadas Vento</b></td><td>70 - 90 km/h</td><td>90 - 110 km/h</td><td>> 110 km/h</td></tr>"
        "<tr><td><b>Chuva (1h)</b></td><td>10 - 20 mm/h</td><td>20 - 35 mm/h</td><td>> 35 mm/h</td></tr>"
        "<tr><td><b>Chuva (6h)</b></td><td>20 - 40 mm</td><td>40 - 60 mm</td><td>> 60 mm</td></tr>"
        "</table></div>",
        unsafe_allow_html=True,
    )

st.divider()

st.subheader("🕰️ Análise de Impacto Territorial por Analogia com Eventos Históricos")
evento_analogo, similaridade = calcular_analogia_historica(pico_r, pico_c, max_chuva_24h)

col_hist1, col_hist2 = st.columns([1.3, 1.7])
with col_hist1:
    if pico_r < 55 and pico_c < 6 and max_chuva_24h < 15:
        st.success("✅ **Cenário Sem Analogia Severa:** Os valores previstos encontram-se abaixo dos limiares de eventos históricos adversos registados em Óbidos.")
    else:
        st.warning(f"⚠️ **Análogo Histórico Mais Próximo:** **{evento_analogo['nome']}** (Similaridade: **{similaridade}%**)")
    st.markdown(
        f"* **Tipologia:** {evento_analogo['tipo']}\n"
        f"* **Referência Histórica:** Rajadas `{evento_analogo['rajada_ref']:.0f} km/h` | Chuva 1h `{evento_analogo['chuva_1h_ref']:.0f} mm/h` | Chuva 24h `{evento_analogo['chuva_24h_ref']:.0f} mm`\n"
        f"* **Previsto:** Rajadas `{pico_r:.1f} km/h` | Chuva 1h `{pico_c:.1f} mm/h` | Chuva 24h `{max_chuva_24h:.1f} mm`"
    )
with col_hist2:
    st.markdown(
        "<div style='background-color: #fff8e7; padding: 15px; border-radius: 10px; border-left: 5px solid #ff8c00;'>"
        "<div style='font-weight: bold; color: #b35900; margin-bottom: 6px;'>📍 Impacto Potencial no Território:</div>"
        "<div style='font-size: 13px; color: #222; margin-bottom: 8px;'><b>Setores Críticos:</b> " + evento_analogo["setores_criticos"] + "</div>"
        "<div style='font-size: 13px; color: #222; margin-bottom: 8px;'><b>Ocorrências Típicas:</b> " + evento_analogo["impacto"] + "</div>"
        "<div style='font-size: 13px; color: #004085;'><b>🛡️ Ação Preventiva (SMPC):</b> " + evento_analogo["medidas"] + "</div></div>",
        unsafe_allow_html=True,
    )

st.divider()

tab_meteo, tab_boletim, tab_mapa_radar, tab_alertas = st.tabs(
    [
        "📊 Meteogramas Operacionais",
        "📑 Boletim Técnico (14 Dias)",
        "🗺️ Mapa Tático & Radar",
        "📢 Comunicados",
    ]
)

with tab_meteo:
    fig_spotwx = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=(
            "💨 Vento Sustentado e Rajadas Máximas (km/h)",
            "🌧️ Intensidade de Precipitação Horária (mm/h)",
            "🌡️ Temperatura do Ar (°C)",
            "📉 Pressão Atmosférica à Superfície (hPa)",
        ),
    )
    fig_spotwx.add_trace(
        go.Scatter(
            x=df["Hora"],
            y=df["Rajada (km/h)"],
            name="Rajada (km/h)",
            line=dict(color="#d62728", width=2, dash="dot"),
            fill="tonexty",
            fillcolor="rgba(214, 39, 40, 0.1)",
        ),
        row=1,
        col=1,
    )
    fig_spotwx.add_trace(
        go.Scatter(
            x=df["Hora"],
            y=df["Vento (km/h)"],
            name="Vento Sustentado (km/h)",
            line=dict(color="#1f77b4", width=2.5),
        ),
        row=1,
        col=1,
    )
    for _, r_row in df.iloc[::4].iterrows():
        seta_txt = deg_para_seta(r_row["Direção Vento (°)"]).split()[0]
        fig_spotwx.add_annotation(
            x=r_row["Hora"],
            y=r_row["Rajada (km/h)"] + 8,
            text=f"{seta_txt} {r_row['Rajada (km/h)']:.0f}",
            showarrow=False,
            font=dict(size=9, color="#444"),
            row=1,
            col=1,
        )
    if pico_r >= 60:
        fig_spotwx.add_hline(y=70, line_dash="dash", line_color="#ffcc00", row=1, col=1, annotation_text="Amarelo (70 km/h)")
        fig_spotwx.add_hline(y=90, line_dash="dash", line_color="#ff6600", row=1, col=1, annotation_text="Laranja (90 km/h)")
        fig_spotwx.add_hline(y=110, line_dash="dash", line_color="#ff0000", row=1, col=1, annotation_text="Vermelho (110 km/h)")
    fig_spotwx.add_trace(
        go.Bar(x=df["Hora"], y=df["Precipitação (mm)"], name="Precipitação (mm/h)", marker_color="#1f77b4", opacity=0.9),
        row=2,
        col=1,
    )
    if pico_c >= 8:
        fig_spotwx.add_hline(y=10, line_dash="dash", line_color="#ffcc00", row=2, col=1, annotation_text="Amarelo (10 mm/h)")
        fig_spotwx.add_hline(y=20, line_dash="dash", line_color="#ff6600", row=2, col=1, annotation_text="Laranja (20 mm/h)")
        fig_spotwx.add_hline(y=35, line_dash="dash", line_color="#ff0000", row=2, col=1, annotation_text="Vermelho (35 mm/h)")
    fig_spotwx.add_trace(
        go.Scatter(x=df["Hora"], y=df["Temperatura (°C)"], name="Temperatura (°C)", line=dict(color="#ff7f0e", width=2.5)),
        row=3,
        col=1,
    )
    fig_spotwx.add_trace(
        go.Scatter(x=df["Hora"], y=df["Pressão (hPa)"], name="Pressão (hPa)", line=dict(color="#9467bd", width=2.5)),
        row=4,
        col=1,
    )
    fig_spotwx.update_layout(height=1050, hovermode="x unified", showlegend=False, plot_bgcolor="#ffffff")
    st.plotly_chart(fig_spotwx, use_container_width=True)

with tab_boletim:
    if not df_14d.empty:
        df_14d["Data"] = df_14d["Hora"].dt.date
        resumo_dias = []
        for data_dia, grupo in df_14d.groupby("Data"):
            dt_obj = pd.to_datetime(data_dia)
            dia_label = f"{dias_semana_curto.get(dt_obj.strftime('%A'), '')} {dt_obj.strftime('%d/%m')}"
            resumo_dias.append(
                {
                    "Dia": dia_label,
                    "T. Mín (°C)": round(grupo["Temp_ECMWF"].min(), 1),
                    "T. Méd (°C)": round(grupo["Temp_ECMWF"].mean(), 1),
                    "T. Máx (°C)": round(grupo["Temp_ECMWF"].max(), 1),
                    "Vento Méd (km/h)": round(grupo["Vento_ECMWF"].mean(), 1),
                    "Rajada Máx (km/h)": round(grupo["Rajada_ECMWF"].max(), 1),
                    "Dir.": f"{deg_para_seta(grupo['Dir_ECMWF'].median()).split()[0]} {deg_para_direcao(grupo['Dir_ECMWF'].median())}",
                    "Chuva Acum (mm)": round(grupo["Chuva_ECMWF"].sum(), 1),
                    "Chuva Máx (mm/h)": round(grupo["Chuva_ECMWF"].max(), 1),
                    "Humidade (%)": round(grupo["HR_ECMWF"].mean(), 0),
                }
            )
        st.dataframe(pd.DataFrame(resumo_dias), use_container_width=True, height=500)

        fig_multi = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.08,
            subplot_titles=("💨 Rajadas Máximas (km/h) — ECMWF vs GFS vs ICON", "🌡️ Temperatura (°C) — ECMWF vs GFS vs ICON"),
        )
        fig_multi.add_trace(go.Scatter(x=df_14d["Hora"], y=df_14d["Rajada_ECMWF"], name="ECMWF", line=dict(color="#d62728", width=2)), row=1, col=1)
        fig_multi.add_trace(go.Scatter(x=df_14d["Hora"], y=df_14d["Rajada_GFS"], name="GFS", line=dict(color="#1f77b4", width=1.5, dash="dash")), row=1, col=1)
        fig_multi.add_trace(go.Scatter(x=df_14d["Hora"], y=df_14d["Rajada_ICON"], name="ICON", line=dict(color="#2ca02c", width=1.5, dash="dot")), row=1, col=1)
        fig_multi.add_trace(go.Scatter(x=df_14d["Hora"], y=df_14d["Temp_ECMWF"], name="Temp ECMWF", line=dict(color="#ff7f0e", width=2)), row=2, col=1)
        fig_multi.add_trace(go.Scatter(x=df_14d["Hora"], y=df_14d["Temp_GFS"], name="Temp GFS", line=dict(color="#9467bd", width=1.5, dash="dash")), row=2, col=1)
        fig_multi.add_trace(go.Scatter(x=df_14d["Hora"], y=df_14d["Temp_ICON"], name="Temp ICON", line=dict(color="#8c564b", width=1.5, dash="dot")), row=2, col=1)
        fig_multi.update_layout(height=580, hovermode="x unified", plot_bgcolor="#ffffff")
        st.plotly_chart(fig_multi, use_container_width=True)
    else:
        st.info("Boletim multi-modelo de 14 dias indisponível de momento devido a latência na API.")

with tab_mapa_radar:
    dados_mapa = []
    for nome_s, info_s in setores_obidos.items():
        if nome_s in ["🌍 Todo o Concelho (Consolidado)", "📍 Ponto Específico (Google Maps / Coordenadas)"]:
            continue
        df_s = obter_dados_cruzados(info_s["lat"], info_s["lon"], 1, 2)
        if not df_s.empty:
            r_max, c_max = df_s["Rajada (km/h)"].max(), df_s["Precipitação (mm)"].max()
            if r_max > 110 or c_max > 35:
                niv, ico, cor = "VERMELHO", "🔴", [255, 0, 0, 150]
            elif r_max > 90 or c_max > 20:
                niv, ico, cor = "LARANJA", "🟠", [255, 140, 0, 150]
            elif r_max > 70 or c_max > 10:
                niv, ico, cor = "AMARELO", "🟡", [255, 215, 0, 150]
            else:
                niv, ico, cor = "VERDE", "🟢", [0, 128, 0, 130]
            dados_mapa.append(
                {
                    "setor": nome_s,
                    "polygon": info_s["polygon"],
                    "nivel": f"{ico} {niv}",
                    "rajada": f"{r_max:.1f}",
                    "chuva": f"{c_max:.1f}",
                    "cor": cor,
                }
            )
    if dados_mapa:
        camada_poligonos = pdk.Layer(
            "PolygonLayer",
            data=pd.DataFrame(dados_mapa),
            get_polygon="polygon",
            get_fill_color="cor",
            get_line_color=[255, 255, 255, 200],
            get_line_width=50,
            pickable=True,
            auto_highlight=True,
        )
        camada_ponto = pdk.Layer(
            "ScatterplotLayer",
            data=pd.DataFrame([{"nome": "Ponto", "lat": lat_analise, "lon": lon_analise, "cor": [0, 102, 255, 255]}]),
            get_position=["lon", "lat"],
            get_color="cor",
            get_radius=300,
            pickable=True,
        )
        st.pydeck_chart(
            pdk.Deck(
                layers=[camada_poligonos, camada_ponto],
                initial_view_state=pdk.ViewState(latitude=lat_analise, longitude=lon_analise, zoom=11.0, pitch=15),
                tooltip={"text": "Setor: {setor}\\nAlerta: {nivel}\\nRajada Máx: {rajada} km/h\\nChuva Máx: {chuva} mm/h"},
            )
        )
    windy_html = (
        "<iframe width='100%' height='450' src='https://embed.windy.com/embed2.html?"
        f"lat={lat_analise}&lon={lon_analise}&detailLat={lat_analise}&detailLon={lon_analise}"
        "&width=100%&height=450&zoom=10&level=surface&overlay=radar&product=radar&menu=&message=true"
        "&marker=true&calendar=now&pressure=true&type=map&location=coordinates&metricWind=km%2Fh&metricTemp=%C2%B0C' "
        "frameborder='0'></iframe>"
    )
    components.html(windy_html, height=470)

with tab_alertas:
    tipo_alvo = st.radio("Destinatário:", ["População em Geral", "Organizadores de Eventos"])
    if tipo_alvo == "População em Geral":
        horizonte_horas = st.selectbox("Janela de análise:", [6, 12, 24, 36], format_func=lambda x: f"Próximas {x} horas")
        dt_inicio_aviso, dt_fim_aviso = agora, agora + timedelta(hours=horizonte_horas)
    else:
        col_ev1, col_ev2 = st.columns(2)
        with col_ev1:
            data_ev_ini = st.date_input("Data de Início", value=datetime.today().date() + timedelta(days=1))
            hora_ev_ini = st.time_input("Hora de Início", value=time(17, 0))
        with col_ev2:
            data_ev_fim = st.date_input("Data de Fim", value=data_ev_ini)
            hora_ev_fim = st.time_input("Hora de Fim", value=time(21, 0))
        dt_inicio_aviso = datetime.combine(data_ev_ini, hora_ev_ini)
        dt_fim_aviso = datetime.combine(data_ev_fim, hora_ev_fim)

    df_janela = df[(df["Hora"] >= dt_inicio_aviso) & (df["Hora"] <= dt_fim_aviso)]
    chuva_j = df_janela["Precipitação (mm)"].max() if not df_janela.empty else 0.0
    acum_j = df_janela["Precipitação (mm)"].sum() if not df_janela.empty else 0.0
    vento_j = df_janela["Rajada (km/h)"].max() if not df_janela.empty else 0.0

    if vento_j > 110 or chuva_j > 35:
        nivel_j, ico_j = "VERMELHO", "🔴"
    elif vento_j > 90 or chuva_j > 20:
        nivel_j, ico_j = "LARANJA", "🟠"
    elif vento_j > 70 or chuva_j > 10:
        nivel_j, ico_j = "AMARELO", "🟡"
    else:
        nivel_j, ico_j = "VERDE", "🟢"

    msg_final = (
        f"🛡️ *SERVIÇO MUNICIPAL DE PROTEÇÃO CIVIL DE ÓBIDOS*\n"
        f"🕒 *Emitido em:* {formatar_data_pt(agora)}\n"
        f"⚠️ *{ico_j} AVISO {nivel_j}* — Setor: *{setor_selecionado}*\n"
        f"• 🌧️ *Precipitação:* Máx {chuva_j:.1f} mm/h (Acumulado: {acum_j:.1f} mm)\n"
        f"• 💨 *Rajada Máxima:* {vento_j:.0f} km/h ({cardeal_vento_str} {seta_vento_str})\n"
        f"• 🕰️ *Análogo Histórico:* {evento_analogo['nome']} ({similaridade}%)\n"
        "🔗 Avisos oficiais IPMA: https://www.ipma.pt/pt/otempo/prev-sam/?p=LRA"
    )
    st.code(msg_final, language="markdown")
