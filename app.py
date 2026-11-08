import streamlit as st
import pandas as pd
import requests
import re
import numpy as np
import plotly.express as px
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import pydeck as pdk
from datetime import datetime, time, timedelta

st.set_page_config(
    page_title="Serviço Municipal de Proteção Civil de Óbidos - Análise Meteorológica",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🛡️ Serviço Municipal de Proteção Civil de Óbidos - Análise Meteorológica")
st.markdown("Painel tático de apoio à decisão operacional, monitorização setorial por polígonos, radar em tempo real e emissão de avisos.")

# ==============================================================================
# FUNÇÕES AUXILIARES (GOOGLE MAPS E DIREÇÃO DO VENTO)
# ==============================================================================
def extrair_coords_google_maps(url_gmaps):
    if not url_gmaps:
        return None, None
    padrao_at = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url_gmaps)
    if padrao_at:
        return float(padrao_at.group(1)), float(padrao_at.group(2))
    
    padrao_q = re.search(r'[?&](?:q|ll)=(-?\d+\.\d+),(-?\d+\.\d+)', url_gmaps)
    if padrao_q:
        return float(padrao_q.group(1)), float(padrao_q.group(2))
        
    return None, None

def deg_para_direcao(deg):
    if pd.isna(deg):
        return "N/D"
    direcoes = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    val = int((deg / 22.5) + 0.5)
    return direcoes[(val % 16)]

def deg_para_seta(deg):
    if pd.isna(deg):
        return "⬆️"
    if 337.5 <= deg <= 360 or 0 <= deg < 22.5: return "⬇️ (N)"
    elif 22.5 <= deg < 67.5: return "↙️ (NE)"
    elif 67.5 <= deg < 112.5: return "⬅️ (E)"
    elif 112.5 <= deg < 157.5: return "↖️ (SE)"
    elif 157.5 <= deg < 202.5: return "⬆️ (S)"
    elif 202.5 <= deg < 247.5: return "↗️ (SW)"
    elif 247.5 <= deg < 292.5: return "➡️ (W)"
    elif 292.5 <= deg < 337.5: return "↘️ (NW)"
    return "⬆️"

# ==============================================================================
# DICIONÁRIOS DE TRADUÇÃO DE DATAS PARA PORTUGUÊS DE PORTUGAL
# ==============================================================================
dias_semana_pt = {
    'Monday': 'Segunda-feira', 'Tuesday': 'Terça-feira', 'Wednesday': 'Quarta-feira',
    'Thursday': 'Quinta-feira', 'Friday': 'Sexta-feira', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
}

meses_pt = {
    'January': 'janeiro', 'February': 'fevereiro', 'March': 'março', 'April': 'abril',
    'May': 'maio', 'June': 'junho', 'July': 'julho', 'August': 'agosto',
    'September': 'setembro', 'October': 'outubro', 'November': 'novembro', 'December': 'dezembro'
}

def formatar_data_pt(dt):
    dia_sem = dias_semana_pt.get(dt.strftime('%A'), dt.strftime('%A'))
    mes = meses_pt.get(dt.strftime('%B'), dt.strftime('%B'))
    return f"{dia_sem}, {dt.day} de {mes} de {dt.year} às {dt.strftime('%H:%M')}"

def formatar_intervalo_pico(dt_ini, dt_fim):
    return f"das {dt_ini.strftime('%H:%M')} horas do dia {dt_ini.strftime('%d/%m')} até às {dt_fim.strftime('%H:%M')} horas do dia {dt_fim.strftime('%d/%m')}"

# ==============================================================================
# SEGMENTAÇÃO GEOMORFOLÓGICA E POLÍGONOS DOS SETORES DE ÓBIDOS
# ==============================================================================
setores_obidos = {
    "🌍 Todo o Concelho (Consolidado)": {
        "lat": 39.3700, "lon": -9.1600, 
        "perfil": "Visão global agregada de todo o território de Óbidos.",
        "polygon": [
            [-9.260, 39.340], [-9.080, 39.340], 
            [-9.080, 39.415], [-9.260, 39.415]
        ]
    },
    "🏛️ Centro Histórico (Vila / Cota Alta)": {
        "lat": 39.3607, "lon": -9.1572, 
        "perfil": "Zona elevada e muralhada. Exposição direta a rajadas canalizadas.",
        "polygon": [
            [-9.175, 39.350], [-9.140, 39.350], 
            [-9.140, 39.375], [-9.175, 39.375]
        ]
    },
    "🌊 Litoral & Lagoa (Bom Sucesso / Vau)": {
        "lat": 39.3800, "lon": -9.2200, 
        "perfil": "Zona estuarina e lagunar. Vulnerável a marés, vento atlântico e frentes costeiras.",
        "polygon": [
            [-9.260, 39.340], [-9.185, 39.340], 
            [-9.185, 39.410], [-9.260, 39.410]
        ]
    },
    "🌾 Interior & Bacia do Arnóia (A-dos-Negros / Olho Marinho)": {
        "lat": 39.3700, "lon": -9.1300, 
        "perfil": "Zona de vales aluviais. Suscetível a retenção de humidade e cheias de bacia.",
        "polygon": [
            [-9.150, 39.355], [-9.080, 39.355], 
            [-9.080, 39.415], [-9.150, 39.415]
        ]
    },
    "📍 Ponto Específico (Google Maps / Coordenadas)": {
        "lat": 39.3607, "lon": -9.1572,
        "perfil": "Coordenadas geográficas personalizadas definidas pelo utilizador.",
        "polygon": []
    }
}

st.sidebar.header("⚙️ Parâmetros de Análise Global")
setor_selecionado = st.sidebar.selectbox("Selecionar Setor / Vista", list(setores_obidos.keys()))

if 'lat_clicada' not in st.session_state:
    st.session_state.lat_clicada = 39.3607
if 'lon_clicada' not in st.session_state:
    st.session_state.lon_clicada = -9.1572

if setor_selecionado == "📍 Ponto Específico (Google Maps / Coordenadas)":
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📍 Localização Personalizada")
    
    url_gmaps = st.sidebar.text_input("Link do Google Maps (Cole o URL completo):", placeholder="https://www.google.com/maps/@39.3607,-9.1572,15z")
    lat_ext, lon_ext = extrair_coords_google_maps(url_gmaps)
    
    if lat_ext and lon_ext:
        st.session_state.lat_clicada = lat_ext
        st.session_state.lon_clicada = lon_ext
        st.sidebar.success(f"Coordenadas extraídas do link: {lat_ext:.4f}, {lon_ext:.4f}")
    
    lat_custom = st.sidebar.number_input("Latitude", value=st.session_state.lat_clicada, format="%.4f")
    lon_custom = st.sidebar.number_input("Longitude", value=st.session_state.lon_clicada, format="%.4f")
    nome_ponto_custom = st.sidebar.text_input("Nome/Ref. do Ponto", value="Ponto Específico")
    
    lat_analise = lat_custom
    lon_analise = lon_custom
    setores_obidos["📍 Ponto Específico (Google Maps / Coordenadas)"]["lat"] = lat_custom
    setores_obidos["📍 Ponto Específico (Google Maps / Coordenadas)"]["lon"] = lon_custom
    setores_obidos["📍 Ponto Específico (Google Maps / Coordenadas)"]["perfil"] = f"Análise focada em {nome_ponto_custom} ({lat_custom:.4f}, {lon_custom:.4f})."
    info_setor = setores_obidos["📍 Ponto Específico (Google Maps / Coordenadas)"]
else:
    info_setor = setores_obidos[setor_selecionado]
    lat_analise = info_setor["lat"]
    lon_analise = info_setor["lon"]

dias_historico = st.sidebar.slider("Dias de Calibração (Passado)", min_value=1, max_value=5, value=2)
dias_previsao = st.sidebar.slider("Dias de Previsão Operacional", min_value=1, max_value=7, value=5)

# ==============================================================================
# AQUISIÇÃO DE DADOS (API Open-Meteo com modelo ECMWF priorizado)
# ==============================================================================
@st.cache_data(ttl=900)
def obter_dados_cruzados(lat, lon, past, forecast):
    url = f"
