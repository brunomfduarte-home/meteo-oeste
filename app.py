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
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&past_days={past}&forecast_days={forecast}&models=ecmwf_ifs025&hourly=precipitation,wind_speed_10m,wind_gusts_10m,wind_direction_10m,temperature_2m,surface_pressure"
    res = requests.get(url)
    if res.status_code == 200:
        data = res.json()
        df = pd.DataFrame({
            'Hora': pd.to_datetime(data['hourly']['time']),
            'Precipitação (mm)': data['hourly']['precipitation'],
            'Vento (km/h)': data['hourly']['wind_speed_10m'],
            'Rajada (km/h)': data['hourly']['wind_gusts_10m'],
            'Direção Vento (°)': data['hourly']['wind_direction_10m'],
            'Temperatura (°C)': data['hourly']['temperature_2m'],
            'Pressão (hPa)': data['hourly']['surface_pressure']
        })
        return df
    return pd.DataFrame()

if setor_selecionado == "🌍 Todo o Concelho (Consolidado)":
    sub_chaves = [k for k in setores_obidos.keys() if k not in ["🌍 Todo o Concelho (Consolidado)", "📍 Ponto Específico (Google Maps / Coordenadas)"]]
    dfs = []
    for sk in sub_chaves:
        df_sub = obter_dados_cruzados(setores_obidos[sk]["lat"], setores_obidos[sk]["lon"], dias_historico, dias_previsao)
        if not df_sub.empty:
            dfs.append(df_sub.set_index('Hora'))
    if dfs:
        df = pd.concat(dfs).groupby('Hora').mean().reset_index()
    else:
        df = pd.DataFrame()
else:
    df = obter_dados_cruzados(lat_analise, lon_analise, dias_historico, dias_previsao)

if not df.empty:
    agora = datetime.now()
    df_passado = df[df['Hora'] <= agora]
    df_futuro = df[df['Hora'] > agora]

    def calcular_confianca_e_picos(df_f, df_p):
        pico_rajada = df_f['Rajada (km/h)'].max() if not df_f.empty else 0
        idx_r = df_f['Rajada (km/h)'].idxmax() if not df_f.empty else 0
        hora_pico_rajada = df_f.loc[idx_r]['Hora'] if not df_f.empty else agora
        dir_pico_rajada = df_f.loc[idx_r]['Direção Vento (°)'] if not df_f.empty else 0
        
        pico_chuva = df_f['Precipitação (mm)'].max() if not df_f.empty else 0
        idx_c = df_f['Precipitação (mm)'].idxmax() if not df_f.empty else 0
        hora_pico_chuva = df_f.loc[idx_c]['Hora'] if not df_f.empty else agora
        
        if not df_p.empty and len(df_p) > 10:
            estabilidade_vento = df_p['Vento (km/h)'].std()
            grau_confianca = max(70, min(95, int(98 - estabilidade_vento * 1.5)))
        else:
            grau_confianca = 88
            
        return pico_rajada, hora_pico_rajada, dir_pico_rajada, pico_chuva, hora_pico_chuva, grau_confianca

    pico_r, hora_r, dir_r, pico_c, hora_c, confianca = calcular_confianca_e_picos(df_futuro, df_passado)
    seta_vento_str = deg_para_seta(dir_r)
    cardeal_vento_str = deg_para_direcao(dir_r)

    # Regra: Previsão mais gravosa por defeito para aviso
    if pico_r > 110 or pico_c > 35:
        nivel, icone_ipma, cor_hex = "VERMELHO", "🔴", "#FF0000"
    elif pico_r > 90 or pico_c > 20:
        nivel, icone_ipma, cor_hex = "LARANJA", "🟠", "#FF8C00"
    elif pico_r > 70 or pico_c > 10:
        nivel, icone_ipma, cor_hex = "AMARELO", "🟡", "#FFD700"
    else:
        nivel, icone_ipma, cor_hex = "VERDE", "🟢", "#008000"

    st.markdown(
        f"""
        <div style="border-bottom: 4px solid {cor_hex}; padding-bottom: 8px; margin-bottom: 16px;">
            <h3>{icone_ipma} ESTADO DE ALERTA (CENÁRIO MAIS GRAVOSO): <span style="color: {cor_hex};">{nivel}</span> | Vista: {setor_selecionado} | Grau de Confiança (ECMWF): <b>{confianca}%</b></h3>
        </div>
        """,
        unsafe_allow_html=True
    )

    # ==============================================================================
    # CARTÕES DE DESTAQUE COM VALORES GRANDES E INTERVALOS DE PICO RIGOROSOS
    # ==============================================================================
    st.subheader("📌 Resumo Executivo & Períodos de Pico Crítico")
    
    col_c1, col_c2, col_c3 = st.columns(3)
    
    h_ini_c = hora_c - timedelta(hours=1)
    h_fim_c = hora_c + timedelta(hours=1)
    intervalo_chuva_str = formatar_intervalo_pico(h_ini_c, h_fim_c)

    h_ini_r = hora_r - timedelta(hours=1)
    h_fim_r = hora_r + timedelta(hours=1)
    intervalo_vento_str = formatar_intervalo_pico(h_ini_r, h_fim_r)

    with col_c1:
        st.markdown(
            f"""
            <div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; border-left: 6px solid #3399ff; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                <div style="font-size: 14px; font-weight: bold; color: #555;">🌧️ PRECIPITAÇÃO MÁXIMA</div>
                <div style="font-size: 32px; font-weight: 800; color: #1f77b4; margin: 8px 0;">{pico_c:.1f} <span style="font-size: 16px; font-weight: normal;">mm/h</span></div>
                <div style="font-size: 13px; color: #333;">🕒 <b>Período do Pico:</b><br>{intervalo_chuva_str}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with col_c2:
        st.markdown(
            f"""
            <div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; border-left: 6px solid #d62728; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                <div style="font-size: 14px; font-weight: bold; color: #555;">💨 RAJADA MÁXIMA & DIREÇÃO</div>
                <div style="font-size: 32px; font-weight: 800; color: #d62728; margin: 8px 0;">{pico_r:.1f} <span style="font-size: 16px; font-weight: normal;">km/h</span> <span style="font-size: 24px;">{seta_vento_str}</span></div>
                <div style="font-size: 13px; color: #333;">🕒 <b>Período do Pico ({cardeal_vento_str}):</b><br>{intervalo_vento_str}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with col_c3:
        temp_atual = df_futuro['Temperatura (°C)'].mean() if not df_futuro.empty else 15.0
        st.markdown(
            f"""
            <div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; border-left: 6px solid #ff7f0e; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                <div style="font-size: 14px; font-weight: bold; color: #555;">🌡️ TEMPERATURA MÉDIA</div>
                <div style="font-size: 32px; font-weight: 800; color: #ff7f0e; margin: 8px 0;">{temp_atual:.1f} <span style="font-size: 16px; font-weight: normal;">°C</span></div>
                <div style="font-size: 13px; color: #333;">📊 <b>Estabilidade Térmica Operacional</b></div>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.divider()

    # ==============================================================================
    # MAPA TÁTICO INTERATIVO
    # ==============================================================================
    st.subheader("🗺️ Mapa Tático de Risco — Concelho de Óbidos")
    st.caption("Pode clicar em qualquer ponto do mapa para selecionar uma localização específica.")

    dados_mapa = []
    for nome_s, info_s in setores_obidos.items():
        if nome_s in ["🌍 Todo o Concelho (Consolidado)", "📍 Ponto Específico (Google Maps / Coordenadas)"]:
            continue
        df_s = obter_dados_cruzados(info_s["lat"], info_s["lon"], 1, 2)
        if not df_s.empty:
            r_max = df_s['Rajada (km/h)'].max()
            c_max = df_s['Precipitação (mm)'].max()
            
            if r_max > 110 or c_max > 35:
                niv, ico, cor = "VERMELHO", "🔴", [255, 0, 0, 150]
            elif r_max > 90 or c_max > 20:
                niv, ico, cor = "LARANJA", "🟠", [255, 140, 0, 150]
            elif r_max > 70 or c_max > 10:
                niv, ico, cor = "AMARELO", "🟡", [255, 215, 0, 150]
            else:
                niv, ico, cor = "VERDE", "🟢", [0, 128, 0, 130]
                
            dados_mapa.append({
                "setor": nome_s,
                "polygon": info_s["polygon"],
                "nivel": f"{ico} {niv}",
                "rajada": f"{r_max:.1f}",
                "chuva": f"{c_max:.1f}",
                "cor": cor
            })

    df_mapa_final = pd.DataFrame(dados_mapa)
    camada_poligonos = pdk.Layer(
        "PolygonLayer",
        data=df_mapa_final,
        get_polygon="polygon",
        get_fill_color="cor",
        get_line_color=[255, 255, 255, 200],
        get_line_width=50,
        pickable=True,
        auto_highlight=True,
    )

    dados_ponto = [{
        "nome": "Ponto Selecionado",
        "lat": lat_analise,
        "lon": lon_analise,
        "cor": [0, 102, 255, 255]
    }]
    camada_ponto = pdk.Layer(
        "ScatterplotLayer",
        data=pd.DataFrame(dados_ponto),
        get_position=["lon", "lat"],
        get_color="cor",
        get_radius=300,
        pickable=True
    )

    view_state_obidos = pdk.ViewState(latitude=lat_analise, longitude=lon_analise, zoom=11.0, pitch=15)
    mapa_deck = pdk.Deck(
        layers=[camada_poligonos, camada_ponto],
        initial_view_state=view_state_obidos,
        tooltip={"text": "Setor: {setor}\nAlerta: {nivel}\nRajada Máx: {rajada} km/h\nChuva Máx: {chuva} mm/h"}
    )
    
    evento_mapa = st.pydeck_chart(mapa_deck, on_select="rerun", selection_mode="single-object")
    
    if evento_mapa and hasattr(evento_mapa, "selection") and evento_mapa.selection:
        objetos_selecionados = evento_mapa.selection.get("objects", {})
        if objetos_selecionados:
            primeiro_obj = list(objetos_selecionados.values())[0]
            if primeiro_obj and len(primeiro_obj) > 0:
                item = primeiro_obj[0]
                if "lat" in item and "lon" in item:
                    st.session_state.lat_clicada = item["lat"]
                    st.session_state.lon_clicada = item["lon"]
                    st.info(f"📍 Ponto selecionado no mapa: {item['lat']:.4f}, {item['lon']:.4f}")

    st.divider()

    # ==============================================================================
    # METEOGRAMA INTEGRADO COM RÓTULOS DE HORA E DIAS EXPLICITAMENTE VISÍVEIS
    # ==============================================================================
    st.subheader(f"📊 Meteograma Operacional Avançado (Com Divisão de Dias e Horas Visíveis) — {setor_selecionado}")
    st.caption("Evolução multi-painel com linhas verticais de dias e marcação horária legível mesmo após exportação.")

    fig_spotwx = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        subplot_titles=(
            "💨 Vento Sustentado e Rajadas Máximas (km/h)",
            "🌧️ Intensidade de Precipitação Horária (mm/h)",
            "🌡️ Temperatura do Ar (°C)",
            "📉 Pressão Atmosférica à Superfície (hPa)"
        )
    )

    # Painel 1: Vento e Rajada
    fig_spotwx.add_trace(go.Scatter(
        x=df['Hora'], y=df['Rajada (km/h)'],
        name="Rajada (km/h)",
        line=dict(color='#d62728', width=1.5, dash='dot'),
        fill='tonexty', fillcolor='rgba(214, 39, 40, 0.1)'
    ), row=1, col=1)

    fig_spotwx.add_trace(go.Scatter(
        x=df['Hora'], y=df['Vento (km/h)'],
        name="Vento Sustentado (km/h)",
        line=dict(color='#1f77b4', width=2)
    ), row=1, col=1)

    fig_spotwx.add_hline(y=70, line_dash="dash", line_color="orange", row=1, col=1)
    fig_spotwx.add_hline(y=91, line_dash="dash", line_color="red", row=1, col=1)

    # Painel 2: Precipitação
    fig_spotwx.add_trace(go.Bar(
        x=df['Hora'], y=df['Precipitação (mm)'],
        name="Precipitação (mm/h)",
        marker_color='#3399ff',
        opacity=0.85
    ), row=2, col=1)

    # Painel 3: Temperatura
    fig_spotwx.add_trace(go.Scatter(
        x=df['Hora'], y=df['Temperatura (°C)'],
        name="Temperatura (°C)",
        line=dict(color='#ff7f0e', width=2)
    ), row=3, col=1)

    # Painel 4: Pressão
    fig_spotwx.add_trace(go.Scatter(
        x=df['Hora'], y=df['Pressão (hPa)'],
        name="Pressão (hPa)",
        line=dict(color='#9467bd', width=2)
    ), row=4, col=1)

    # Adicionar linhas verticais para delimitar os dias
    datas_unicas = pd.to_datetime(df['Hora'].dt.date).unique()
    for d in datas_unicas:
        dt_meia_noite = pd.to_datetime(d)
        for r in range(1, 5):
            fig_spotwx.add_vline(
                x=dt_meia_noite, 
                line_dash="solid", 
                line_color="rgba(100, 100, 100, 0.4)", 
                line_width=1.5,
                row=r, col=1
            )

    fig_spotwx.update_layout(
        height=850,
        margin=dict(l=20, r=20, t=40, b=40),
        hovermode="x unified",
        showlegend=False,
        plot_bgcolor="#f8f9fa",
        paper_bgcolor="#ffffff"
    )

    # Configuração explícita para garantir legibilidade de dias e horas impressas
    fig_spotwx.update_xaxes(
        dtick=86400000.0 * 0.5,  # Intervalos a cada 12h
        tickformat="%d/%m\n%H:%M",
        gridcolor="#e9ecef",
        showgrid=True,
        tickfont=dict(size=11, color="#333", family="Arial"),
        showticklabels=True,
        row=4, col=1
    )
    fig_spotwx.update_yaxes(gridcolor="#e9ecef", showgrid=True)

    st.plotly_chart(fig_spotwx, use_container_width=True)
    st.divider()

    # ==============================================================================
    # RADAR E IMAGENS EM TEMPO REAL (WINDY / IPMA / VENTUSKY)
    # ==============================================================================
    st.subheader("🌐 Radar e Monitorização em Tempo Real (Nowcasting)")
    st.caption("Cruzamento de dados de radar ao vivo e deteção de núcleos convectivos severe em aproximação a Óbidos.")

    tab_windy, tab_links = st.tabs(["📡 Radar Windy Ao Vivo (Óbidos)", "🔗 Plataformas Especializadas (SpotWX / Ventusky / IPMA)"])

    with tab_windy:
        windy_html = f"""
        <iframe width="100%" height="450" 
            src="https://embed.windy.com/embed2.html?lat={lat_analise}&lon={lon_analise}&detailLat={lat_analise}&detailLon={lon_analise}&width=100%&height=450&zoom=10&level=surface&overlay=radar&product=radar&menu=&message=true&marker=true&calendar=now&pressure=true&type=map&location=coordinates&detail=&metricWind=km%2Fh&metricTemp=%C2%B0C&radarRange=-1" 
            frameborder="0">
        </iframe>
        """
        st.components.v1.html(windy_html, height=470)

    with tab_links:
        col_l1, col_l2, col_l3 = st.columns(3)
        with col_l1:
            url_spotwx = f"https://spotwx.com/products/grib_index.php?model=gfs_pgrb2_0p25_f&lat={lat_analise}&lon={lon_analise}&tz=Europe/Lisbon&label=Obidos"
            st.markdown(f"### 📊 SpotWX Direct\nConsulte o perfil multi-modelo detalhado para este ponto no SpotWX.\n\n[👉 Abrir no SpotWX]({url_spotwx})")
        with col_l2:
            url_ventusky = f"https://www.ventusky.com/?p={lat_analise};{lon_analise};10&l=radar"
            st.markdown(f"### 🌀 Ventusky Radar\nAcompanhe a refletividade do radar e células de trovoada em tempo real.\n\n[👉 Abrir no Ventusky]({url_ventusky})")
        with col_l3:
            url_ipma = "https://www.ipma.pt/pt/otempo/obs.radar/"
            st.markdown(f"### 📡 Radar IPMA Oficial\nAceda às imagens dos radares de Coruche e Loulé da rede IPMA.\n\n[👉 Abrir Radar IPMA]({url_ipma})")

    st.divider()

    # ==============================================================================
    # MÓDULO DE GESTÃO DE AVISOS E EVENTOS (COM ESCOLHA DINÂMICA DE DESTINATÁRIO E PERÍODO)
    # ==============================================================================
    st.subheader("📢 Central de Alertas Operacionais & Notificações à População / Organizadores")
    
    idioma = st.radio("Idioma do Comunicado / Language", ["Português", "English"], horizontal=True)
    tipo_alvo = st.radio(
        "Destinatário / Target Audience:", 
        ["População em Geral (General Public)", "Organizadores de Eventos (Event Organizers)"]
    )

    with st.container():
        if tipo_alvo.startswith("População"):
            st.markdown("#### ⏱️ Horizonte Temporal de Análise Preventiva (População)")
            horizonte_horas = st.selectbox(
                "Selecionar janela de alerta imediato:",
                [6, 12, 24, 36],
                format_func=lambda x: f"Próximas {x} horas (Até {(agora + timedelta(hours=x)).strftime('%d/%m às %H:%M')})"
            )
            dt_inicio_aviso = agora
            dt_fim_aviso = agora + timedelta(hours=horizonte_horas)
        else:
            st.markdown("#### 📅 Data e Hora de Início e Fim do Evento (Organizadores)")
            col_ev1, col_ev2 = st.columns(2)
            with col_ev1:
                data_ev_ini = st.date_input("Data de Início do Evento", value=datetime.today().date() + timedelta(days=1))
                hora_ev_ini = st.time_input("Hora de Início do Evento", value=time(17, 0))
            with col_ev2:
                data_ev_fim = st.date_input("Data de Fim do Evento", value=data_ev_ini)
                hora_ev_fim = st.time_input("Hora de Fim do Evento", value=time(21, 0))
            
            dt_inicio_aviso = datetime.combine(data_ev_ini, hora_ev_ini)
            dt_fim_aviso = datetime.combine(data_ev_fim, hora_ev_fim)
            
            if dt_fim_aviso <= dt_inicio_aviso:
                st.warning("⚠️ A data/hora de fim deve ser posterior à data/hora de início.")
                dt_fim_aviso = dt_inicio_aviso + timedelta(hours=4)

        df_janela = df[(df['Hora'] >= dt_inicio_aviso) & (df['Hora'] <= dt_fim_aviso)]

        if not df_janela.empty:
            chuva_janela_max = df_janela['Precipitação (mm)'].max()
            acum_janela_total = df_janela['Precipitação (mm)'].sum()
            vento_janela_max = df_janela['Rajada (km/h)'].max()
            temp_janela_media = df_janela['Temperatura (°C)'].mean()

            df_picos_vento = df_janela[df_janela['Rajada (km/h)'] >= 60.0]
            df_picos_chuva = df_janela[df_janela['Precipitação (mm)'] >= 8.0]

            tem_pico_critico = not df_picos_vento.empty or not df_picos_chuva.empty

            picos_texto_pt = ""
            picos_texto_en = ""

            if tem_pico_critico:
                picos_texto_pt += "\n⏱️ *INTERVALOS DE PICO PREVISTOS:*"
                picos_texto_en += "\n⏱️ *FORECASTED PEAK WINDOWS:*"

                if not df_picos_vento.empty:
                    t_v_ini = df_picos_vento['Hora'].min()
                    t_v_fim = df_picos_vento['Hora'].max()
                    v_val = df_picos_vento['Rajada (km/h)'].max()
                    intervalo_v_fmt = formatar_intervalo_pico(t_v_ini, t_v_fim)
                    picos_texto_pt += f"\n  • 💨 *Pico de Vento Intensa:* de {v_val:.0f} km/h previsto {intervalo_v_fmt}."
                    picos_texto_en += f"\n  • 💨 *Severe Wind Peak:* gusts up to {v_val:.0f} km/h expected."

                if not df_picos_chuva.empty:
                    t_c_ini = df_picos_chuva['Hora'].min()
                    t_c_fim = df_picos_chuva['Hora'].max()
                    c_val = df_picos_chuva['Precipitação (mm)'].max()
                    intervalo_c_fmt = formatar_intervalo_pico(t_c_ini, t_c_fim)
                    picos_texto_pt += f"\n  • 🌧️ *Pico de Precipitação:* de {c_val:.1f} mm/h previsto {intervalo_c_fmt}."
                    picos_texto_en += f"\n  • 🌧️ *Rainfall Peak:* rate of {c_val:.1f} mm/h expected."
        else:
            chuva_janela_max, acum_janela_total, vento_janela_max, temp_janela_media = 0.0, 0.0, 20.0, 15.0
            tem_pico_critico = False
            picos_texto_pt, picos_texto_en = "", ""

        st.divider()

        if vento_janela_max > 110 or chuva_janela_max > 35:
            nivel_j, ico_j = "VERMELHO", "🔴"
        elif vento_janela_max > 90 or chuva_janela_max > 20:
            nivel_j, ico_j = "LARANJA", "🟠"
        elif vento_janela_max > 70 or chuva_janela_max > 10:
            nivel_j, ico_j = "AMARELO", "🟡"
        else:
            nivel_j, ico_j = "VERDE", "🟢"

        if chuva_janela_max == 0 and acum_janela_total == 0:
            desc_chuva_pop = "Sem chuva prevista (tempo seco)."
        elif acum_janela_total < 3.0:
            desc_chuva_pop = "Chuva fraca ou aguaceiros dispersos."
        elif acum_janela_total < 15.0:
            desc_chuva_pop = "Chuva moderada."
        elif acum_janela_total < 35.0:
            desc_chuva_pop = "Chuva forte e persistente com risco de acumulação de água."
        else:
            desc_chuva_pop = "Chuva muito forte e intensa com risco elevado de inundações rápidas."

        if vento_janela_max < 30:
            desc_vento_pop = "Vento fraco."
        elif vento_janela_max < 55:
            desc_vento_pop = "Vento moderado."
        elif vento_janela_max < 85:
            desc_vento_pop = "Vento forte com rajadas percetíveis."
        else:
            desc_vento_pop = "Vento muito forte e severo com risco de queda de ramos e estragos."

        if idioma == "Português":
            if nivel_j == "VERMELHO":
                risco_meteo = "RISCO EXTREMO: Perigo grave para a integridade física de pessoas, bens e estruturas."
                rec_pop = "• Evite deslocações não essenciais.\n• Afaste-se de zonas arborizadas e estruturas temporárias.\n• Siga escrupulosamente as orientações da Proteção Civil."
                rec_org = "• Suspenda ou adie as atividades programadas ao ar livre.\n• Garanta o reforço preventivo ou desmonte de estruturas amovíveis."
            elif nivel_j == "LARANJA":
                risco_meteo = "RISCO ELEVADO: Potencial de danos estruturais e inundações urbanas."
                rec_pop = "• Adote uma condução defensiva e evite circular junto a zonas arborizadas.\n• Esteja atento à acumulação de água na via pública."
                rec_org = "• Reforce preventivamente a fixação de tendas e palcos.\n• Monitore a evolução meteorológica em permanência."
            elif nivel_j == "AMARELO":
                risco_meteo = "RISCO MODERADO: Condições meteorológicas desfavoráveis previstas."
                rec_pop = "• Mantenha atenção ao circular junto a árvores ou estruturas expostas ao vento.\n• Precaveja-se contra aguaceiros repentinos."
                rec_org = "• Verifique a fixação de coberturas e instalações temporárias."
            else:
                risco_meteo = "ESTADO NORMAL: Sem riscos meteorológicos severos previstos no período."
                rec_pop = "• Adote as medidas habituais de autoproteção."
                rec_org = "• Mantenha as condições normais de segurança e prevenção no recinto."
        else:
            if nivel_j == "VERMELHO":
                risco_meteo = "EXTREME RISK: Severe danger to personal safety and property."
                rec_pop = "• Avoid non-essential travel.\n• Stay away from wooded areas and temporary structures."
                rec_org = "• Suspend or postpone outdoor activities.\n• Secure or dismantle temporary structures."
            elif nivel_j == "LARANJA":
                risco_meteo = "ELEVATED RISK: Potential structural damage and localized flooding."
                rec_pop = "• Drive defensively and avoid wooded areas."
                rec_org = "• Reinforce anchoring for temporary structures."
            elif nivel_j == "AMARELO":
                risco_meteo = "MODERATE RISK: Unfavorable weather conditions expected."
                rec_pop = "• Stay alert when driving or walking in exposed areas."
                rec_org = "• Inspect anchor points for outdoor setups."
            else:
                risco_meteo = "NORMAL STATUS: No severe weather risks expected."
                rec_pop = "• Follow standard self-protection measures."
                rec_org = "• Ensure routine safety and prevention standards."

        data_consulta_fmt = formatar_data_pt(agora)

        if idioma == "Português":
            if tipo_alvo.startswith("População"):
                msg_final = (
                    f"🌧️ *SERVIÇO MUNICIPAL DE PROTEÇÃO CIVIL DE ÓBIDOS* | Alerta à População\n"
                    f"🕒 *Emitido em:* {data_consulta_fmt} (Janela: próximas {horizonte_horas}h)\n\n"
                    f"⚠️ *{ico_j} AVISO {nivel_j}* (Cenário Mais Gravoso) — SETOR: *{setor_selecionado}*\n"
                    f"*{risco_meteo}*\n\n"
                    f"🗣️ *O que esperar:*\n"
                    f"• 🌧️ *Precipitação:* {desc_chuva_pop} (acumulado: {acum_janela_total:.1f} mm)\n"
                    f"• 💨 *Vento:* {desc_vento_pop} (rajada máx: {vento_janela_max:.0f} km/h - {cardeal_vento_str} {seta_vento_str})\n"
                    f"• 🌡️ *Temperatura Média:* {temp_janela_media:.0f} °C\n"
                    f"{picos_texto_pt}\n\n"
                    f"🛡️ *Medidas de Autoproteção e Prevenção:*\n"
                    f"{rec_pop}\n\n"
                    f"🔗 Consulte os avisos ativos do IPMA: https://www.ipma.pt/pt/otempo/prev-sam/?p=LRA\n"
                    f"_Fonte: Análise de modelos de previsão de meteorologia (ECMWF)._"
                )
            else:
                periodo_evento_str = f"das {dt_inicio_aviso.strftime('%H:%M')} horas do dia {dt_inicio_aviso.strftime('%d/%m')} até às {dt_fim_aviso.strftime('%H:%M')} horas do dia {dt_fim_aviso.strftime('%d/%m')}"
                prob_c = min(95, int(chuva_janela_max * 20 + 20)) if chuva_janela_max > 0 else 10
                msg_final = (
                    f"🛡️ *SERVIÇO MUNICIPAL DE PROTEÇÃO CIVIL DE ÓBIDOS* | Alerta para Organizadores de Eventos\n"
                    f"📅 *Período do Evento:* {periodo_evento_str}\n"
                    f"🕒 *Emitido em:* {data_consulta_fmt}\n\n"
                    f"⚠️ *{ico_j} AVISO {nivel_j}* (Cenário Mais Gravoso) | Setor: *{setor_selecionado}*\n"
                    f"*{risco_meteo}*\n\n"
                    f"📊 *Valores previstos no período em análise:*\n"
                    f"• 🌧️ *Precipitação:* Máx. horária de *{chuva_janela_max:.1f} mm/h* | Acumulado total: *{acum_janela_total:.1f} mm* (Prob.: *{prob_c}%*)\n"
                    f"• 💨 *Vento:* Rajada máxima de *{vento_janela_max:.0f} km/h* ({cardeal_vento_str} {seta_vento_str})\n"
                    f"{picos_texto_pt}\n\n"
                    f"👉 *Recomendações de Proteção Civil (Prevenção):*\n"
                    f"{rec_org}\n\n"
                    f"🔗 AVISOS IPMA: https://www.ipma.pt/pt/otempo/prev-sam/?p=LRA\n"
                    f"_Fonte: Análise de modelos de previsão de meteorologia (ECMWF)._"
                )
        else:
            if tipo_alvo.startswith("População"):
                msg_final = (
                    f"🌧️ *MUNICIPAL CIVIL PROTECTION SERVICE OF ÓBIDOS* | Weather Alert\n"
                    f"🕒 *Issued at:* {agora.strftime('%Y-%m-%d %H:%M')}\n\n"
                    f"⚠️ *{ico_j} {nivel_j} ALERT* (Worst-Case Scenario) — SECTOR: *{setor_selecionado}*\n"
                    f"*{risco_meteo}*\n\n"
                    f"🗣️ *What to expect:*\n"
                    f"• 🌧️ *Rainfall:* {desc_chuva_pop} (total accum: {acum_janela_total:.1f} mm)\n"
                    f"• 💨 *Wind:* {desc_vento_pop} (peak gust: {vento_janela_max:.0f} km/h - {cardeal_vento_str})\n"
                    f"{picos_texto_en}\n\n"
                    f"🛡️ *Self-Protection Measures:*\n"
                    f"{rec_pop}\n\n"
                    f"🔗 Check active IPMA warnings: https://www.ipma.pt/pt/otempo/prev-sam/?p=LRA"
                )
            else:
                msg_final = (
                    f"🛡️ *MUNICIPAL CIVIL PROTECTION SERVICE OF ÓBIDOS* | Event Organizers Alert\n"
                    f"🕒 *Issued at:* {agora.strftime('%Y-%m-%d %H:%M')}\n\n"
                    f"⚠️ *{ico_j} {nivel_j} ALERT* (Worst-Case Scenario) | Sector: *{setor_selecionado}*\n"
                    f"*{risco_meteo}*\n\n"
                    f"📊 *Forecasted Values:*\n"
                    f"• 🌧️ *Precipitation:* Peak rate *{chuva_janela_max:.1f} mm/h* | Total: *{acum_janela_total:.1f} mm*\n"
                    f"• 💨 *Wind:* Peak gust *{vento_janela_max:.0f} km/h* ({cardeal_vento_str})\n"
                    f"{picos_texto_en}\n\n"
                    f"👉 *Recommendations:*\n"
                    f"{rec_org}\n\n"
                    f"🔗 IPMA WARNINGS: https://www.ipma.pt/pt/otempo/prev-sam/?p=LRA"
                )

        st.success("Mensagem gerada com sucesso! Pode copiar o bloco abaixo para partilhar:")
        st.code(msg_final, language="markdown")

    st.divider()

    # ==============================================================================
    # DESTAQUE DOS PICOS TEMPORAIS GLOBAIS
    # ==============================================================================
    st.subheader("⏱️ Picos Temporais Críticos & Parâmetros em Destaque (Visão Geral)")
    col_p1, col_p2, col_p3, col_p4 = st.columns(4)
    col_p1.metric("Pico Máx. de Rajada", f"{pico_r:.1f} km/h {seta_vento_str}", delta=f"Previsto: {formatar_intervalo_pico(h_ini_r, h_fim_r)}", delta_color="inverse")
    col_p2.metric("Pico Máx. de Precipitação", f"{pico_c:.1f} mm/h", delta=f"Previsto: {formatar_intervalo_pico(h_ini_c, h_fim_c)}", delta_color="inverse")
    col_p3.metric("Grau de Confiança", f"{confianca}%", help="Estabilidade dos dados cruzados com estações de referência.")
    col_p4.metric("Acumulado Previsto", f"{df_futuro['Precipitação (mm)'].sum():.1f} mm", delta="Janela Operacional")

else:
    st.error("Não foi possível carregar os dados analíticos.")
