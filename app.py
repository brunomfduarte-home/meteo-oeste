import streamlit as st
import pandas as pd
import requests
import re
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
# FUNÇÃO PARA EXTRAIR COORDENADAS DE LINKS DO GOOGLE MAPS
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

dias_historico = st.sidebar.slider("Dias de Calibração (Passado)", min_value=1, max_value=5, value=3)
dias_previsao = st.sidebar.slider("Dias de Previsão Operacional", min_value=1, max_value=7, value=5)

# ==============================================================================
# AQUISIÇÃO DE DADOS (API Open-Meteo com modelo ECMWF priorizado)
# ==============================================================================
@st.cache_data(ttl=900)
def obter_dados_cruzados(lat, lon, past, forecast):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&past_days={past}&forecast_days={forecast}&models=ecmwf_ifs025&hourly=precipitation,wind_speed_10m,wind_gusts_10m,temperature_2m,surface_pressure,soil_moisture_7_to_28cm"
    res = requests.get(url)
    if res.status_code == 200:
        data = res.json()
        df = pd.DataFrame({
            'Hora': pd.to_datetime(data['hourly']['time']),
            'Precipitação (mm)': data['hourly']['precipitation'],
            'Vento (km/h)': data['hourly']['wind_speed_10m'],
            'Rajada (km/h)': data['hourly']['wind_gusts_10m'],
            'Temperatura (°C)': data['hourly']['temperature_2m'],
            'Pressão (hPa)': data['hourly']['surface_pressure'],
            'Humidade Solo (%)': [v * 100 for v in data['hourly']['soil_moisture_7_to_28cm']]
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
        hora_pico_rajada = df_f.loc[df_f['Rajada (km/h)'].idxmax()]['Hora'] if not df_f.empty else agora
        
        pico_chuva = df_f['Precipitação (mm)'].max() if not df_f.empty else 0
        hora_pico_chuva = df_f.loc[df_f['Precipitação (mm)'].idxmax()]['Hora'] if not df_f.empty else agora
        
        if not df_p.empty and len(df_p) > 10:
            estabilidade_vento = df_p['Vento (km/h)'].std()
            grau_confianca = max(70, min(95, int(98 - estabilidade_vento * 1.5)))
        else:
            grau_confianca = 88
            
        return pico_rajada, hora_pico_rajada, pico_chuva, hora_pico_chuva, grau_confianca

    pico_r, hora_r, pico_c, hora_c, confianca = calcular_confianca_e_picos(df_futuro, df_passado)

    if pico_r > 110 or pico_c > 35:
        nivel, icone_ipma, cor_hex = "VERMELHO", "🔴", "#FF0000"
    elif pico_r > 90 or pico_c > 20:
        nivel, icone_ipma, cor_hex = "LARANJA", "🟠", "#FF8C00"
    elif pico_r > 70 or pico_c > 10:
        nivel, icone_ipma, cor_hex = "AMARELO", "🟡", "#FFD700"
    else:
        nivel, icone_ipma, cor_hex = "VERDE", "🟢", "#008000"

    proximo_de_aviso = (pico_r >= 60) or (pico_c >= 8)
    if nivel in ["AMARELO", "LARANJA", "VERMELHO"]:
        st.toast(f"{icone_ipma} ATENÇÃO: Aviso {nivel} ativo ou iminente em {setor_selecionado}!", icon="⚠️")
    elif proximo_de_aviso:
        st.toast(f"⚡ Parâmetros próximos do limiar de aviso em {setor_selecionado} (Rajada: {pico_r:.1f} km/h).", icon="🔔")

    st.markdown(
        f"""
        <div style="border-bottom: 4px solid {cor_hex}; padding-bottom: 8px; margin-bottom: 16px;">
            <h3>{icone_ipma} ESTADO DE ALERTA: <span style="color: {cor_hex};">{nivel}</span> | Vista: {setor_selecionado} | Grau de Confiança (ECMWF): <b>{confianca}%</b></h3>
        </div>
        """,
        unsafe_allow_html=True
    )

    # ==============================================================================
    # CARTÕES DE DESTAQUE DE PERÍODO CRÍTICO (ESTILO SMPC)
    # ==============================================================================
    st.subheader("📌 Resumo Executivo & Períodos de Pico Crítico")
    
    col_c1, col_c2, col_c3 = st.columns(3)
    
    with col_c1:
        st.markdown(
            f"""
            <div style="background-color: #f1f3f5; padding: 15px; border-radius: 8px; border-left: 5px solid #3399ff;">
                <h4>🌧️ Precipitação</h4>
                <p><b>Máx:</b> {pico_c:.1f} mm/h</p>
                <p>🕒 <b>Período do Pico:</b><br>{hora_c.strftime('%d/%m às %H:%M')}</p>
            </div>
            """,
            unsafe_allow_html=True
        )
    with col_c2:
        st.markdown(
            f"""
            <div style="background-color: #f1f3f5; padding: 15px; border-radius: 8px; border-left: 5px solid #d62728;">
                <h4>💨 Rajadas de Vento</h4>
                <p><b>Máx:</b> {pico_r:.1f} km/h</p>
                <p>🕒 <b>Período do Pico:</b><br>{hora_r.strftime('%d/%m às %H:%M')}</p>
            </div>
            """,
            unsafe_allow_html=True
        )
    with col_c3:
        temp_atual = df_futuro['Temperatura (°C)'].mean() if not df_futuro.empty else 15.0
        st.markdown(
            f"""
            <div style="background-color: #f1f3f5; padding: 15px; border-radius: 8px; border-left: 5px solid #ff7f0e;">
                <h4>🌡️ Temperatura Média</h4>
                <p><b>Média Prevista:</b> {temp_atual:.1f} °C</p>
                <p>📊 <b>Estabilidade Térmica</b></p>
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
    # METEOGRAMA INTEGRADO PROFISSIONAL (CORRIGIDO E SEPARADO POR PAINÉIS)
    # ==============================================================================
    st.subheader(f"📊 Meteograma Operacional Avançado (Estilo SpotWX) — {setor_selecionado}")
    st.caption("Evolução temporal multi-painel corrigida: eixos isolados por parâmetro para leitura limpa e rigorosa.")

    # Criar Subplots com 4 painéis independentes para evitar sobreposições
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

    # Painel 3: Temperatura (Isolada)
    fig_spotwx.add_trace(go.Scatter(
        x=df['Hora'], y=df['Temperatura (°C)'],
        name="Temperatura (°C)",
        line=dict(color='#ff7f0e', width=2)
    ), row=3, col=1)

    # Painel 4: Pressão (Isolada)
    fig_spotwx.add_trace(go.Scatter(
        x=df['Hora'], y=df['Pressão (hPa)'],
        name="Pressão (hPa)",
        line=dict(color='#9467bd', width=2)
    ), row=4, col=1)

    fig_spotwx.update_layout(
        height=850,
        margin=dict(l=20, r=20, t=40, b=20),
        hovermode="x unified",
        showlegend=False,
        plot_bgcolor="#f8f9fa",
        paper_bgcolor="#ffffff"
    )

    fig_spotwx.update_xaxes(
        dtick="H6",
        tickformat="%d/%m\n%H:%M",
        gridcolor="#e9ecef",
        showgrid=True,
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
        with col_l
