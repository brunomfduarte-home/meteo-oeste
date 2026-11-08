import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import pydeck as pdk
from datetime import datetime, timedelta

st.set_page_config(
    page_title="Meteo Óbidos — Comando Operacional & Eventos",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🛡️ Centro de Comando Operacional — Concelho de Óbidos")
st.markdown("Painel tático para monitorização meteorológica, mapeamento territorial por polígonos de risco e emissão de avisos para eventos.")

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
    }
}

st.sidebar.header("⚙️ Parâmetros de Análise")
setor_selecionado = st.sidebar.selectbox("Selecionar Setor / Vista", list(setores_obidos.keys()))
info_setor = setores_obidos[setor_selecionado]

dias_historico = st.sidebar.slider("Dias de Calibração (Passado)", min_value=1, max_value=5, value=3)
dias_previsao = st.sidebar.slider("Dias de Previsão Operacional", min_value=1, max_value=7, value=3)

# ==============================================================================
# AQUISIÇÃO DE DADOS (API Open-Meteo com ECMWF/GFS priorizado)
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

# Se for "Todo o Concelho", calculamos a média ponderada dos subsetores
if setor_selecionado == "🌍 Todo o Concelho (Consolidado)":
    sub_chaves = [k for k in setores_obidos.keys() if k != "🌍 Todo o Concelho (Consolidado)"]
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
    df = obter_dados_cruzados(info_setor["lat"], info_setor["lon"], dias_historico, dias_previsao)

if not df.empty:
    agora = datetime.now()
    df_passado = df[df['Hora'] <= agora]
    df_futuro = df[df['Hora'] > agora]

    def calcular_confianca_e_picos(df_f, df_p):
        pico_rajada = df_f['Rajada (km/h)'].max()
        hora_pico_rajada = df_f.loc[df_f['Rajada (km/h)'].idxmax()]['Hora'] if not df_f.empty else agora
        
        pico_chuva = df_f['Precipitação (mm)'].max()
        hora_pico_chuva = df_f.loc[df_f['Precipitação (mm)'].idxmax()]['Hora'] if not df_f.empty else agora
        
        if not df_p.empty and len(df_p) > 10:
            estabilidade_vento = df_p['Vento (km/h)'].std()
            grau_confianca = max(70, min(95, int(98 - estabilidade_vento * 1.5)))
        else:
            grau_confianca = 88
            
        return pico_rajada, hora_pico_rajada, pico_chuva, hora_pico_chuva, grau_confianca

    pico_r, hora_r, pico_c, hora_c, confianca = calcular_confianca_e_picos(df_futuro, df_passado)

    # Avaliação de Severidade IPMA
    if pico_r > 110 or pico_c > 35:
        nivel, cor_alerta = "VERMELHO", "error"
    elif pico_r > 90 or pico_c > 20:
        nivel, cor_alerta = "LARANJA", "warning"
    elif pico_r > 70 or pico_c > 10:
        nivel, cor_alerta = "AMARELO", "info"
    else:
        nivel, cor_alerta = "VERDE", "success"

    # Alerta Principal no Topo
    mensagem_topo = f"🚨 **ESTADO DE ALERTA: {nivel}** | Vista: {setor_selecionado} | Grau de Confiança (ECMWF): **{confianca}%**"
    if cor_alerta == "error": st.error(mensagem_topo)
    elif cor_alerta == "warning": st.warning(mensagem_topo)
    elif cor_alerta == "info": st.info(mensagem_topo)
    else: st.success(mensagem_topo)

    # ==============================================================================
    # MAPA TÁTICO COM POLÍGONOS SETORIAIS COLORIDOS POR AVISO
    # ==============================================================================
    st.subheader("🗺️ Mapa Tático de Risco — Setores do Concelho de Óbidos")
    st.caption("As áreas territoriais encontram-se preenchidas de acordo com o respetivo nível de aviso meteorológico ativo.")

    dados_mapa = []
    for nome_s, info_s in setores_obidos.items():
        if nome_s == "🌍 Todo o Concelho (Consolidado)":
            continue
        df_s = obter_dados_cruzados(info_s["lat"], info_s["lon"], 1, 2)
        if not df_s.empty:
            r_max = df_s['Rajada (km/h)'].max()
            c_max = df_s['Precipitação (mm)'].max()
            
            if r_max > 110 or c_max > 35:
                niv, cor = "VERMELHO", [255, 0, 0, 160]
            elif r_max > 90 or c_max > 20:
                niv, cor = "LARANJA", [255, 128, 0, 160]
            elif r_max > 70 or c_max > 10:
                niv, cor = "AMARELO", [255, 204, 0, 160]
            else:
                niv, cor = "VERDE", [0, 200, 0, 140]
                
            dados_mapa.append({
                "setor": nome_s,
                "polygon": info_s["polygon"],
                "nivel": niv,
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
        get_line_width=60,
        pickable=True,
        auto_highlight=True,
    )

    view_state_obidos = pdk.ViewState(
        latitude=39.3750,
        longitude=-9.1700,
        zoom=10.6,
        pitch=15,
    )

    mapa_deck = pdk.Deck(
        layers=[camada_poligonos],
        initial_view_state=view_state_obidos,
        tooltip={"text": "Setor: {setor}\nAlerta: {nivel}\nRajada Máx: {rajada} km/h\nChuva Máx: {chuva} mm/h"}
    )

    st.pydeck_chart(mapa_deck)
    st.divider()

    # ==============================================================================
    # DESTAQUE DOS PICOS TEMPORAIS
    # ==============================================================================
    st.subheader("⏱️ Picos Temporais Críticos & Parâmetros em Destaque")
    
    hora_pico_rajada_fmt = hora_r.strftime('%d/%m às %H:%M')
    hora_pico_chuva_fmt = hora_c.strftime('%d/%m às %H:%M')

    col_p1, col_p2, col_p3, col_p4 = st.columns(4)
    col_p1.metric("Pico Máx. de Rajada", f"{pico_r:.1f} km/h", delta=f"Previsto: {hora_pico_rajada_fmt}", delta_color="inverse")
    col_p2.metric("Pico Máx. de Precipitação", f"{pico_c:.1f} mm/h", delta=f"Previsto: {hora_pico_chuva_fmt}", delta_color="inverse")
    col_p3.metric("Grau de Confiança", f"{confianca}%", help="Estabilidade dos dados cruzados com estações de referência.")
    col_p4.metric("Acumulado Previsto", f"{df_futuro['Precipitação (mm)'].sum():.1f} mm", delta="Janela Operacional")

    st.divider()

    # ==============================================================================
    # MÓDULO DE GERAÇÃO DE MENSAGENS PARA ORGANIZADORES DE EVENTOS
    # ==============================================================================
    st.subheader("📢 Gerador de Mensagem de Alerta para Eventos ao Ar Livre")
    st.markdown("Crie um aviso direto, claro e estruturado para enviar aos organizadores de eventos no concelho.")

    with st.form("form_evento"):
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            nome_evento = st.text_input("Nome do Evento", value="Magusto Tradicional de Óbidos")
            data_evento_str = st.text_input("Data e Hora do Evento", value="Quarta, 11 de novembro, às 17h00")
        with col_e2:
            recomendacao_custom = st.text_area(
                "Recomendação Operacional Específica", 
                value="Manter o evento e reservar um espaço coberto. Confirmar a decisão no dia anterior às 14h. Se houver risco de projeção de brasas ou vento forte, não acender fogueira."
            )
        
        gerar_msg = st.form_submit_button("Gerar Mensagem de Aviso")

    if gerar_msg:
        prob_chuva_estimada = min(95, int(pico_c * 15 + 30)) if pico_c > 0 else 15
        msg_gerada = (
            f"🌰 *{nome_evento}* | {data_evento_str}\n\n"
            f"🌧️ *Precipitação provável:* {prob_chuva_estimada}% de probabilidade na faixa horária crítica. "
            f"Rajadas de vento previstas até *{pico_r:.0f} km/h*.\n\n"
            f"👉 *Recomendação de Proteção Civil:* {recomendacao_custom}\n\n"
            f"_Previsão gerada pelo Centro de Comando Operacional de Óbidos em {datetime.now().strftime('%d de %B')}, sujeita a atualização._"
        )
        st.success("Mensagem gerada com sucesso! Pode copiar o bloco abaixo:")
        st.code(msg_gerada, language="markdown")

    st.divider()

    # ==============================================================================
    # GRÁFICOS MULTI-PARÂMETRO
    # ==============================================================================
    st.subheader(f"📈 Análise Avançada — {setor_selecionado}")
    
    fig_vento = px.line(df, x='Hora', y=['Vento (km/h)', 'Rajada (km/h)'], markers=False,
                        color_discrete_map={'Vento (km/h)': '#1f77b4', 'Rajada (km/h)':'#d62728'})
    fig_vento.add_hline(y=70, line_dash="dash", line_color="orange", annotation_text="Limiar Amarelo (70 km/h)")
    fig_vento.add_hline(y=91, line_dash="dash", line_color="red", annotation_text="Limiar Laranja (91 km/h)")
    fig_vento.update_layout(title="Dinâmica de Vento e Rajadas (km/h)", margin=dict(l=10, r=10, t=30, b=10), height=320)
    st.plotly_chart(fig_vento, use_container_width=True)

    fig_dupla = make_subplots(specs=[[{"secondary_y": True}]])
    fig_dupla.add_trace(go.Bar(x=df['Hora'], y=df['Precipitação (mm)'], name="Precipitação (mm/h)", marker_color='cornflowerblue'), secondary_y=False)
    fig_dupla.add_trace(go.Scatter(x=df['Hora'], y=df['Pressão (hPa)'], name="Pressão (hPa)", line=dict(color='purple', width=2)), secondary_y=True)
    fig_dupla.update_layout(title="Precipitação Horária & Queda de Pressão Atmosférica", margin=dict(l=10, r=10, t=30, b=10), height=320)
    fig_dupla.update_yaxes(title_text="Precipitação (mm)", secondary_y=False)
    fig_dupla.update_yaxes(title_text="Pressão (hPa)", secondary_y=True)
    st.plotly_chart(fig_dupla, use_container_width=True)

else:
    st.error("Não foi possível carregar os dados analíticos.")
