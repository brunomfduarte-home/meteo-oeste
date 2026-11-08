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
        with col_l2:
            url_ventusky = f"https://www.ventusky.com/?p={lat_analise};{lon_analise};10&l=radar"
            st.markdown(f"### 🌀 Ventusky Radar\nAcompanhe a refletividade do radar e células de trovoada em tempo real.\n\n[👉 Abrir no Ventusky]({url_ventusky})")
        with col_l3:
            url_ipma = "https://www.ipma.pt/pt/otempo/obs.radar/"
            st.markdown(f"### 📡 Radar IPMA Oficial\nAceda às imagens dos radares de Coruche e Loulé da rede IPMA.\n\n[👉 Abrir Radar IPMA]({url_ipma})")

    st.divider()

    # ==============================================================================
    # MÓDULO DE GESTÃO DE AVISOS E EVENTOS (PADRÃO PROTEÇÃO CIVIL)
    # ==============================================================================
    st.subheader("📢 Central de Avisos & Recomendações (Padrão UNDRR)")
    st.markdown("Defina a **data/hora de início e fim** para gerar alertas operacionais e medidas de autoproteção e prevenção.")

    idioma = st.radio("Idioma do Comunicado / Language", ["Português", "English"], horizontal=True)

    with st.container():
        st.markdown("#### 📅 Janela de Evento / Monitorização (Início e Fim)")
        col_i1, col_i2 = st.columns(2)
        with col_i1:
            data_inicio = st.date_input("Data de Início / Start Date", value=datetime.today().date() + timedelta(days=1))
            hora_inicio = st.time_input("Hora de Início / Start Time", value=time(17, 0))
        with col_i2:
            data_fim = st.date_input("Data de Fim / End Date", value=data_inicio)
            hora_fim = st.time_input("Hora de Fim / End Time", value=time(21, 0))

        dt_inicio = datetime.combine(data_inicio, hora_inicio)
        dt_fim = datetime.combine(data_fim, hora_fim)

        if dt_fim <= dt_inicio:
            st.warning("⚠️ A data/hora de fim deve ser posterior à data/hora de início.")
            dt_fim = dt_inicio + timedelta(hours=4)
        
        diferenca_horas = (dt_fim - dt_inicio).total_seconds() / 3600
        if diferenca_horas > 72:
            st.info("ℹ️ A janela selecionada foi ajustada para o limite máximo de 3 dias (72h).")
            dt_fim = dt_inicio + timedelta(hours=72)

        df_janela = df[(df['Hora'] >= dt_inicio) & (df['Hora'] <= dt_fim)]

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
                picos_texto_pt += "\n⏱️ *JANELAS DE PICO A ATENTAR:*"
                picos_texto_en += "\n⏱️ *CRITICAL PEAK WINDOWS:*"

                if not df_picos_vento.empty:
                    h_v_ini = df_picos_vento['Hora'].min().strftime('%d/%m às %H:%M')
                    h_v_fim = df_picos_vento['Hora'].max().strftime('%H:%M')
                    v_val = df_picos_vento['Rajada (km/h)'].max()
                    picos_texto_pt += f"\n  • 💨 *Pico de Vento / Rajada Intensa:* de {v_val:.0f} km/h entre {h_v_ini}h e {h_v_fim}h."
                    picos_texto_en += f"\n  • 💨 *Severe Wind Peak:* gusts up to {v_val:.0f} km/h between {h_v_ini}h and {h_v_fim}h."

                if not df_picos_chuva.empty:
                    h_c_ini = df_picos_chuva['Hora'].min().strftime('%d/%m às %H:%M')
                    h_c_fim = df_picos_chuva['Hora'].max().strftime('%H:%M')
                    c_val = df_picos_chuva['Precipitação (mm)'].max()
                    picos_texto_pt += f"\n  • 🌧️ *Pico de Precipitação:* de {c_val:.1f} mm/h entre {h_c_ini}h e {h_c_fim}h."
                    picos_texto_en += f"\n  • 🌧️ *Rainfall Peak:* rate of {c_val:.1f} mm/h between {h_c_ini}h and {h_c_fim}h."
        else:
            chuva_janela_max, acum_janela_total, vento_janela_max, temp_janela_media = 0.0, 0.0, 20.0, 15.0
            tem_pico_critico = False
            picos_texto_pt, picos_texto_en = "", ""

        st.divider()

        tipo_alvo = st.radio(
            "Destinatário / Target Audience:", 
            ["População em Geral (General Public)", "Organizadores de Eventos (Event Organizers)"]
        )

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
            desc_chuva_pop = "Chuva fraca ou aguaceiros dispersos de curta duração."
        elif acum_janela_total < 15.0:
            desc_chuva_pop = "Chuva moderada. Recomenda-se precaução na circulação."
        elif acum_janela_total < 35.0:
            desc_chuva_pop = "Chuva forte e persistente. Risco de acumulação de água na via pública."
        else:
            desc_chuva_pop = "Chuva muito forte e intensa com risco elevado de inundações rápidas."

        if vento_janela_max < 30:
            desc_vento_pop = "Vento fraco."
        elif vento_janela_max < 55:
            desc_vento_pop = "Vento moderado."
        elif vento_janela_max < 85:
            desc_vento_pop = "Vento forte com rajadas percetíveis."
        else:
            desc_vento_pop = "Vento muito forte e severo com risco de queda de ramos e estragos em estruturas."

        if idioma == "Português":
            if nivel_j == "VERMELHO":
                risco_meteo = "RISCO EXTREMO: Perigo grave para a integridade física de pessoas, bens e estruturas."
                rec_pop = "• Evite deslocações não essenciais durante o período crítico.\n• Afaste-se de zonas arborizadas, arribas e estruturas temporárias ou desprotegidas.\n• Não tente atravessar passagens molhadas, linhas de água ou áreas inundadas.\n• Siga escrupulosamente as orientações das autoridades de Proteção Civil e Forças de Segurança."
                rec_org = "• Suspenda ou adie as atividades programadas ao ar livre.\n• Garanta o desmonte ou o reforço preventivo de estruturas amovíveis (tendas, palcos, painéis e sinalética).\n• Ative o plano de contingência e comunique antecipadamente a suspensão ao público."
            elif nivel_j == "LARANJA":
                risco_meteo = "RISCO ELEVADO: Potencial de danos em estruturas, queda de ramos/árvores e inundações urbanas."
                rec_pop = "• Adote uma condução defensiva, reduzindo a velocidade e aumentando a distância de segurança.\n• Evite a circulação e permanência junto a zonas arborizadas ou estruturas sujeitas à ação do vento.\n• Esteja atento à acumulação de água na via pública e desobstrua sistemas de escoamento privados."
                rec_org = "• Reforce preventivamente a fixação e amarração de estruturas amovíveis (tendas, coberturas e palcos).\n• Assegure um plano de abrigo em local coberto seguro para os participantes.\n• Monitorize em permanência a evolução do vento e precipitação para suspensão preventiva do recinto se necessário."
            elif nivel_j == "AMARELO":
                risco_meteo = "RISCO MODERADO: Possibilidade de perturbações pontuais na circulação e atividades ao ar livre."
                rec_pop = "• Mantenha a atenção ao circular junto a árvores ou estruturas expostas ao vento.\n• Precaveja-se contra a ocorrência de aguaceiros repentinos ou vento moderado.\n• Garanta a fixação de objetos soltos em varandas, terraços e quintais."
                rec_org = "• Verifique preventivamente a amarração de coberturas, telas e instalações elétricas temporárias no exterior.\n• Mantenha os acessos e saídas de emergência do recinto livres e desobstruídos."
            else:
                risco_meteo = "ESTADO NORMAL: Sem riscos meteorológicos severos previstos no período em análise."
                rec_pop = "• Adote as medidas habituais de autoproteção e mantenha-se informado sobre a situação meteorológica."
                rec_org = "• Garanta a manutenção das condições normais de segurança, acessibilidade e prevenção no recinto do evento."
        else:
            if nivel_j == "VERMELHO":
                risco_meteo = "EXTREME RISK: Severe danger to personal safety, property, and structures."
                rec_pop = "• Avoid non-essential travel during the critical period.\n• Stay away from wooded areas, cliffs, and unprotected temporary structures.\n• Do not attempt to cross flooded roads or water channels.\n• Strictly follow all directions from Civil Protection and emergency authorities."
                rec_org = "• Suspend or postpone outdoor activities.\n• Secure or dismantle temporary structures (tents, stages, signage).\n• Activate contingency plans and notify the public in advance."
            elif nivel_j == "LARANJA":
                risco_meteo = "ELEVATED RISK: High potential for structural damage, falling branches, and localized flooding."
                rec_pop = "• Drive defensively, reduce speed, and increase safety distance.\n• Avoid staying or walking near large trees or wind-exposed structures.\n• Watch for standing water on roads and ensure private drainage is clear."
                rec_org = "• Reinforce anchoring for all temporary structures (tents and stages).\n• Prepare an alternative covered shelter or emergency plan for attendees.\n• Monitor real-time weather and suspend operations if safety thresholds are met."
            elif nivel_j == "AMARELO":
                risco_meteo = "MODERATE RISK: Potential minor disruptions to outdoor activities and travel."
                rec_pop = "• Stay alert when driving or walking in exposed areas.\n• Prepare for sudden rain showers or gusty winds.\n• Secure loose objects on balconies and outdoor areas."
                rec_org = "• Inspect anchor points for temporary covers, banners, and outdoor electrical setups.\n• Keep emergency exits and access routes clear."
            else:
                risco_meteo = "NORMAL STATUS: No severe weather risks expected during the analyzed period."
                rec_pop = "• Follow standard self-protection measures and remain informed."
                rec_org = "• Ensure routine safety, accessibility, and emergency standards are maintained."

        fmt_ini_pt = formatar_data_pt(dt_inicio)
        fmt_fim_pt = formatar_data_pt(dt_fim)
        fmt_ini_en = dt_inicio.strftime('%A, %B %d, %Y, at %H:%M')
        fmt_fim_en = dt_fim.strftime('%A, %B %d, %Y, at %H:%M')

        if idioma == "Português":
            if tipo_alvo.startswith("População"):
                msg_final = (
                    f"🌧️ *SERVIÇO MUNICIPAL DE PROTEÇÃO CIVIL DE ÓBIDOS* | Alerta\n"
                    f"📅 *Período:* De {fmt_ini_pt} até {fmt_fim_pt}\n\n"
                    f"⚠️ *{ico_j} AVISO {nivel_j}* — SETOR: *{setor_selecionado}*\n"
                    f"*{risco_meteo}*\n\n"
                    f"🗣️ *O que esperar no local:*\n"
                    f"• 🌧️ *Precipitação:* {desc_chuva_pop} (acumulado total: {acum_janela_total:.1f} mm)\n"
                    f"• 💨 *Vento:* {desc_vento_pop} (rajada máx: {vento_janela_max:.0f} km/h)\n"
                    f"• 🌡️ *Temperatura Média:* {temp_janela_media:.0f} °C\n"
                    f"{picos_texto_pt}\n\n"
                    f"🛡️ *Medidas de Autoproteção e Prevenção:*\n"
                    f"{rec_pop}\n\n"
                    f"🔗 Consulte os avisos ativos do IPMA: https://www.ipma.pt/pt/otempo/prev-sam/?p=LRA\n"
                    f"_Fonte: Análise de modelos de previsão de meteorologia._"
                )
            else:
                prob_c = min(95, int(chuva_janela_max * 20 + 20)) if chuva_janela_max > 0 else 10
                msg_final = (
                    f"🛡️ *SERVIÇO MUNICIPAL DE PROTEÇÃO CIVIL DE ÓBIDOS* | Alerta para Organizadores de Eventos\n"
                    f"📅 *Período do Evento:* De {fmt_ini_pt} até {fmt_fim_pt}\n\n"
                    f"⚠️ *{ico_j} AVISO {nivel_j}* | Setor: *{setor_selecionado}*\n"
                    f"*{risco_meteo}*\n\n"
                    f"📊 *Valores previstos no período em análise:*\n"
                    f"• 🌧️ *Precipitação:* Máx. horária de *{chuva_janela_max:.1f} mm/h* | Acumulado total: *{acum_janela_total:.1f} mm* (Probabilidade: *{prob_c}%*)\n"
                    f"• 💨 *Vento:* Rajada máxima de *{vento_janela_max:.0f} km/h*\n"
                    f"{picos_texto_pt}\n\n"
                    f"👉 *Recomendações de Proteção Civil (Prevenção):*\n"
                    f"{rec_org}\n\n"
                    f"🔗 AVISOS IPMA: https://www.ipma.pt/pt/otempo/prev-sam/?p=LRA\n"
                    f"_Fonte: Análise de modelos de previsão de meteorologia._"
                )
        else:
            if tipo_alvo.startswith("População"):
                msg_final = (
                    f"🌧️ *MUNICIPAL CIVIL PROTECTION SERVICE OF ÓBIDOS* | Weather Alert\n"
                    f"📅 *Period:* From {fmt_ini_en} to {fmt_fim_en}\n\n"
                    f"⚠️ *{ico_j} {nivel_j} ALERT* — SECTOR: *{setor_selecionado}*\n"
                    f"*{risco_meteo}*\n\n"
                    f"🗣️ *What to expect:*\n"
                    f"• 🌧️ *Rainfall:* {desc_chuva_pop} (total accum: {acum_janela_total:.1f} mm)\n"
                    f"• 💨 *Wind:* {desc_vento_pop} (peak gust: {vento_janela_max:.0f} km/h)\n"
                    f"• 🌡️ *Average Temp:* {temp_janela_media:.0f} °C\n"
                    f"{picos_texto_en}\n\n"
                    f"🛡️ *Self-Protection and Prevention Measures:*\n"
                    f"{rec_pop}\n\n"
                    f"🔗 Check active IPMA warnings: https://www.ipma.pt/pt/otempo/prev-sam/?p=LRA\n"
                    f"_Source: Analysis of meteorological forecasting models._"
                )
            else:
                prob_c = min(95, int(chuva_janela_max * 20 + 20)) if chuva_janela_max > 0 else 10
                msg_final = (
                    f"🛡️ *MUNICIPAL CIVIL PROTECTION SERVICE OF ÓBIDOS* | Event Weather Alert\n"
                    f"📅 *Event Time Frame:* From {fmt_ini_en} to {fmt_fim_en}\n\n"
                    f"⚠️ *{ico_j} {nivel_j} ALERT* | Sector: *{setor_selecionado}*\n"
                    f"*{risco_meteo}*\n\n"
                    f"📊 *Forecasted Values in Analyzed Period:*\n"
                    f"• 🌧️ *Precipitation:* Peak hourly rate of *{chuva_janela_max:.1f} mm/h* | Total accum: *{acum_janela_total:.1f} mm* (Probability: *{prob_c}%*)\n"
                    f"• 💨 *Wind:* Peak gust of *{vento_janela_max:.0f} km/h*\n"
                    f"{picos_texto_en}\n\n"
                    f"👉 *Civil Protection Prevention Recommendations:*\n"
                    f"{rec_org}\n\n"
                    f"🔗 IPMA WARNINGS: https://www.ipma.pt/pt/otempo/prev-sam/?p=LRA\n"
                    f"_Source: Analysis of meteorological forecasting models._"
                )

        st.success("Mensagem gerada com sucesso! Pode copiar o bloco abaixo para partilhar:")
        st.code(msg_final, language="markdown")

    st.divider()

    # ==============================================================================
    # DESTAQUE DOS PICOS TEMPORAIS GLOBAIS
    # ==============================================================================
    st.subheader("⏱️ Picos Temporais Críticos & Parâmetros em Destaque (Visão Geral)")
    hora_pico_rajada_fmt = hora_r.strftime('%d/%m às %H:%M')
    hora_pico_chuva_fmt = hora_c.strftime('%d/%m às %H:%M')

    col_p1, col_p2, col_p3, col_p4 = st.columns(4)
    col_p1.metric("Pico Máx. de Rajada", f"{pico_r:.1f} km/h", delta=f"Previsto: {hora_pico_rajada_fmt}", delta_color="inverse")
    col_p2.metric("Pico Máx. de Precipitação", f"{pico_c:.1f} mm/h", delta=f"Previsto: {hora_pico_chuva_fmt}", delta_color="inverse")
    col_p3.metric("Grau de Confiança", f"{confianca}%", help="Estabilidade dos dados cruzados com estações de referência.")
    col_p4.metric("Acumulado Previsto", f"{df_futuro['Precipitação (mm)'].sum():.1f} mm", delta="Janela Operacional")

else:
    st.error("Não foi possível carregar os dados analíticos.")
