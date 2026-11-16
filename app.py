from datetime import datetime, time, timedelta
import json
import os
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

CACHE_LOCAL_FILE = "/tmp/smpc_obidos_cache.json"


@st.cache_resource
def criar_sessao_http() -> requests.Session:
    sessao = requests.Session()
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    sessao.mount("https://", adapter)
    sessao.mount("http://", adapter)
    sessao.headers.update({"User-Agent": "SMPC-Obidos-Meteo/2.0"})
    return sessao


SESSAO_HTTP = criar_sessao_http()


def guardar_cache_disco(chave: str, df: pd.DataFrame):
    if df.empty:
        return
    try:
        store = {}
        if os.path.exists(CACHE_LOCAL_FILE):
            with open(CACHE_LOCAL_FILE, "r", encoding="utf-8") as f:
                store = json.load(f)
        df_copy = df.copy()
        df_copy["Hora"] = df_copy["Hora"].astype(str)
        store[chave] = {
            "timestamp": datetime.now().isoformat(),
            "records": df_copy.to_dict(orient="records"),
        }
        with open(CACHE_LOCAL_FILE, "w", encoding="utf-8") as f:
            json.dump(store, f)
    except Exception:
        pass


def ler_cache_disco(chave: str):
    try:
        if not os.path.exists(CACHE_LOCAL_FILE):
            return pd.DataFrame(), None
        with open(CACHE_LOCAL_FILE, "r", encoding="utf-8") as f:
            store = json.load(f)
        item = store.get(chave)
        if not item or not item.get("records"):
            return pd.DataFrame(), None
        df_rec = pd.DataFrame(item["records"])
        df_rec["Hora"] = pd.to_datetime(df_rec["Hora"])
        return df_rec, item.get("timestamp")
    except Exception:
        return pd.DataFrame(), None


def gerar_dados_contingencia(past: int, forecast: int) -> pd.DataFrame:
    base = datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(days=past)
    horas = pd.date_range(start=base, periods=(past + forecast) * 24, freq="h")
    n = len(horas)
    return pd.DataFrame(
        {
            "Hora": horas,
            "Precipitação (mm)": np.zeros(n),
            "Vento (km/h)": np.full(n, 18.0),
            "Rajada (km/h)": np.full(n, 28.0),
            "Direção Vento (°)": np.full(n, 315.0),
            "Temperatura (°C)": np.full(n, 16.0),
            "Pressão (hPa)": np.full(n, 1016.0),
            "Humidade (%)": np.full(n, 75.0),
        }
    )


def enviar_notificacao_push(titulo: str, mensagem: str, prioridade: int = 4, ntfy_topic: str = "", tg_token: str = "", tg_chat: str = "", webhook_url: str = ""):
    enviados = []
    erros = []
    if ntfy_topic.strip():
        try:
            r = SESSAO_HTTP.post(
                f"https://ntfy.sh/{ntfy_topic.strip()}",
                data=mensagem.encode("utf-8"),
                headers={
                    "Title": titulo.encode("latin-1", "ignore").decode("latin-1"),
                    "Priority": str(prioridade),
                    "Tags": "warning,rotating_light,shield",
                },
                timeout=10,
            )
            if r.ok:
                enviados.append("ntfy.sh")
            else:
                erros.append(f"ntfy ({r.status_code})")
        except Exception as e:
            erros.append(f"ntfy ({e})")
    if tg_token.strip() and tg_chat.strip():
        try:
            r = SESSAO_HTTP.post(
                f"https://api.telegram.org/bot{tg_token.strip()}/sendMessage",
                json={"chat_id": tg_chat.strip(), "text": f"{titulo}\n\n{mensagem}"},
                timeout=10,
            )
            if r.ok:
                enviados.append("Telegram")
            else:
                erros.append(f"Telegram ({r.status_code})")
        except Exception as e:
            erros.append(f"Telegram ({e})")
    if webhook_url.strip():
        try:
            r = SESSAO_HTTP.post(
                webhook_url.strip(),
                json={"title": titulo, "message": mensagem, "priority": prioridade},
                timeout=10,
            )
            if r.ok:
                enviados.append("Webhook")
            else:
                erros.append(f"Webhook ({r.status_code})")
        except Exception as e:
            erros.append(f"Webhook ({e})")
    return enviados, erros


st.title("🛡️ Serviço Municipal de Proteção Civil de Óbidos - Inteligência Meteorológica")
st.markdown(
    "Painel tático contínuo de apoio à decisão operacional, boletim técnico multi-modelo (14 dias), "
    "comparação com depressões históricas adversas e alertas push automáticos."
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
        "depressao": "Furacão / Tempestade Pós-Tropical Leslie",
        "mes_ano": "Outubro de 2018",
        "nome": "Furacão Leslie (Outubro de 2018)",
        "tipo": "Ciclogénese Explosiva / Eólico Extremo",
        "rajada_ref": 145.0,
        "chuva_1h_ref": 12.0,
        "chuva_24h_ref": 25.0,
        "setores_criticos": "Centro Histórico (Vila), Zonas Arborizadas, Rede Elétrica Aérea e Estruturas Temporárias",
        "efeitos_provocados": "Queda generalizada de árvores de grande porte e postes, cortes prolongados de energia elétrica e comunicações, destelhamentos severos na Vila de Óbidos e obstrução total de vias municipais e nacionais.",
        "medidas": "Ativação preventiva do PMEPC, corte de acessos a zonas arborizadas, verificação de geradores críticos e equipas de desobstrução em prontidão.",
    },
    {
        "depressao": "Depressões Elsa & Fabien",
        "mes_ano": "Dezembro de 2019",
        "nome": "Depressões Elsa & Fabien (Dezembro de 2019)",
        "tipo": "Hidrológico & Eólico Severo (Saturação de Solos)",
        "rajada_ref": 102.0,
        "chuva_1h_ref": 18.0,
        "chuva_24h_ref": 62.0,
        "setores_criticos": "Bacia do Rio Arnóia, Barragem do Arnóia, Várzea da Rainha, Vau e Amoreira",
        "efeitos_provocados": "Saturação extrema dos solos, galgamento das margens do Rio Arnóia, submersão de estradas municipais e campos agrícolas na várzea, instabilização de taludes e colapso parcial de muros de suporte.",
        "medidas": "Monitorização contínua de caudais do Rio Arnóia e descargas da barragem, sinalização e corte de vias inundáveis e alerta às Juntas de Freguesia.",
    },
    {
        "depressao": "Depressão Martinho",
        "mes_ano": "Março de 2025",
        "nome": "Depressão Martinho (Março de 2025)",
        "tipo": "Eólico Severo & Agitação Costeira",
        "rajada_ref": 112.0,
        "chuva_1h_ref": 14.0,
        "chuva_24h_ref": 32.0,
        "setores_criticos": "Litoral & Lagoa de Óbidos (Bom Sucesso, Vau), Centro Histórico",
        "efeitos_provocados": "Queda de árvores de médio e grande porte, danos em coberturas ligeiras e painéis solares, galgamento costeiro na faixa litoral e condicionamentos rodoviários nas ligações à Lagoa de Óbidos.",
        "medidas": "Interdição de estacionamento junto a arvoredo e muralhas, reforço de fixação de estruturas exteriores e vigilância da barra da Lagoa.",
    },
    {
        "depressao": "Depressão Efraín",
        "mes_ano": "Dezembro de 2022",
        "nome": "Depressão Efraín (Dezembro de 2022)",
        "tipo": "Chuva Convectiva Intensa / Inundação Urbana Rápida",
        "rajada_ref": 68.0,
        "chuva_1h_ref": 26.0,
        "chuva_24h_ref": 45.0,
        "setores_criticos": "Zonas Baixas da Vila, Arelho, Olho Marinho, A-dos-Negros e Eixos A8/EN8",
        "efeitos_provocados": "Inundações urbanas rápidas (flash floods), sobrecarga imediata dos coletores pluviais, formação de lençóis de água perigosos nos eixos rodoviários e inundação de caves e pisos térreos.",
        "medidas": "Limpeza preventiva de sarjetas e sumidouros nos pontos críticos identificados, patrulhamento preventivo em pontos negros de drenagem.",
    },
    {
        "depressao": "Depressão Domingos",
        "mes_ano": "Novembro de 2023",
        "nome": "Depressão Domingos (Novembro de 2023)",
        "tipo": "Vento Forte Persistente & Agitação Marítima",
        "rajada_ref": 95.0,
        "chuva_1h_ref": 11.0,
        "chuva_24h_ref": 22.0,
        "setores_criticos": "Centro Histórico (Cota Alta), Freguesias Costeiras e Recintos de Eventos",
        "efeitos_provocados": "Queda de ramos e sinalética vertical, levantamento de telhas soltas, derrube de estruturas temporárias não ancoradas e forte agitação marítima junto à costa.",
        "medidas": "Vistoria rigorosa a estruturas amovíveis de eventos, aviso à navegação/pesca na Lagoa e vigilância de património edificado.",
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

auto_refresh = st.sidebar.checkbox("🔁 Monitorização Contínua (Auto-Refresh 15 min)", value=True)
if auto_refresh:
    components.html("<script>setTimeout(function(){ window.parent.location.reload(); }, 900000);</script>", height=0)

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

st.sidebar.markdown("---")
st.sidebar.header("📲 Notificações Push (Laranja / Vermelho)")
push_ativo = st.sidebar.checkbox("Ativar Alerta Push Automático (≥ Laranja)", value=True)
ntfy_topic = st.sidebar.text_input(
    "Tópico ntfy.sh (Telemóvel/PC)",
    value="smpc-obidos-alertas",
    help="Instale a app ntfy no telemóvel e subscreva este tópico para receber notificações push instantâneas.",
)
with st.sidebar.expander("Canais Adicionais (Telegram / Webhook)"):
    tg_token = st.text_input("Telegram Bot Token", type="password")
    tg_chat = st.text_input("Telegram Chat ID")
    webhook_url = st.text_input("Webhook URL (Pushover / Home Assistant)")
testar_push_btn = st.sidebar.button("🔔 Enviar Push de Teste")


@st.cache_data(ttl=1800, show_spinner=False)
def obter_dados_cruzados(lat: float, lon: float, past: int, forecast: int):
    chave_cache = f"cruzados_{lat:.4f}_{lon:.4f}_{past}_{forecast}"
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}&past_days={past}&forecast_days={forecast}"
        f"&models=ecmwf_ifs025&hourly=precipitation,wind_speed_10m,wind_gusts_10m,"
        f"wind_direction_10m,temperature_2m,surface_pressure,relative_humidity_2m"
    )
    try:
        res = SESSAO_HTTP.get(url, timeout=(10, 40))
        res.raise_for_status()
        data = res.json()
        h = data.get("hourly", {})
        if h.get("time"):
            df_novo = pd.DataFrame(
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
            guardar_cache_disco(chave_cache, df_novo)
            return df_novo, "online", None
    except Exception as exc:
        st.session_state["ultimo_erro_api"] = str(exc)

    df_cache, ts_cache = ler_cache_disco(chave_cache)
    if not df_cache.empty:
        return df_cache, "cache_disco", ts_cache
    return gerar_dados_contingencia(past, forecast), "contingencia", None


@st.cache_data(ttl=1800, show_spinner=False)
def obter_boletim_multimodelo_14d(lat: float, lon: float):
    chave_cache = f"multi14d_{lat:.4f}_{lon:.4f}"
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}&forecast_days=14"
        f"&models=ecmwf_ifs025,gfs_seamless,icon_seamless"
        f"&hourly=precipitation,wind_speed_10m,wind_gusts_10m,wind_direction_10m,temperature_2m,relative_humidity_2m"
    )
    try:
        res = SESSAO_HTTP.get(url, timeout=(10, 40))
        res.raise_for_status()
        data = res.json()
        h = data.get("hourly", {})
        if h.get("time"):
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
    
