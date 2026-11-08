import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(
    page_title="Meteo Oeste — Operacional & Proteção Civil",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🛡️ Centro de Análise e Alerta Meteorológico — Região de Óbidos & Oeste")
st.markdown("Painel de Apoio à Decisão Operacional (Proteção Civil / Eventos ao Ar Livre) com base em limiares IPMA e nowcast horário.")

# Configuração de Coordenadas Geográficas da Região
coords = {
    "Óbidos (Sede / Castelo)": {"lat": 39.3607, "lon": -9.1572, "risco": "Inundações urbanas e bacia do Arnóia"},
    "Bom Sucesso / Lagoa de Óbidos": {"lat": 39.3800, "lon": -9.2200, "risco": "Vento forte e agitação marítima"},
    "Leiria": {"lat": 39.7436, "lon": -8.8071, "risco": "Linhas de instabilidade geral"},
    "Peniche (Costenta)": {"lat": 39.3558, "lon": -9.3811, "risco": "Exposição marítima extrema e rajadas"},
    "Caldas da Rainha": {"lat": 39.4036, "lon": -9.1354, "risco": "Escorrências urbanas"}
}

# Barra Lateral Operacional
st.sidebar.header("⚙️ Parâmetros Operacionais")
local_selecionado = st.sidebar.selectbox("Local de Monitorização", list(coords.keys()))
lat = coords[local_selecionado]["lat"]
lon = coords[local_selecionado]["lon"]

janela_analise = st.sidebar.selectbox("Janela Temporal de Análise", ["Próximas 24 Horas (Nowcast Fino)", "Próximos 3 Dias (Previsão)", "Tendência de 7 Dias"])

st.sidebar.divider()
st.sidebar.markdown(f"📍 **Perfil de Risco Local:**\n_{coords[local_selecionado]['risco']}_")

# Aquisição de Dados Meteorológicos Horários e Diários (Open-Meteo / Modelos de Alta Resolução)
@st.cache_data(ttl=900) # Cache de 15 minutos para manter frescura operacional
def buscar_dados_operacionais(lat, lon):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&past_days=1&forecast_days=3&hourly=precipitation,wind_speed_10m,wind_gusts_10m,temperature_2m,surface_pressure&daily=precipitation_sum,wind_speed_10m_max"
    res = requests.get(url)
    if res.status_code == 200:
        data = res.json()
        
        df_hourly = pd.DataFrame({
            'Hora': pd.to_datetime(data['hourly']['time']),
            'Precipitação (mm)': data['hourly']['precipitation'],
            'Vento (km/h)': data['hourly']['wind_speed_10m'],
            'Rajada (km/h)': data['hourly']['wind_gusts_10m'],
            'Pressão (hPa)': data['hourly']['surface_pressure']
        })
        
        df_daily = pd.DataFrame({
            'Data': pd.to_datetime(data['daily']['time']),
            'Chuva Acumulada (mm)': data['daily']['precipitation_sum'],
            'Rajada Máxima (km/h)': data['daily']['wind_speed_10m_max']
        })
        return df_hourly, df_daily
    return pd.DataFrame(), pd.DataFrame()

df_hourly, df_daily = buscar_dados_operacionais(lat, lon)

if not df_hourly.empty:
    # Filtrar apenas as próximas 24h ou 3 dias conforme escolha
    agora = datetime.now()
    if janela_analise == "Próximas 24 Horas (Nowcast Fino)":
        df_focal = df_hourly[(df_hourly['Hora'] >= agora - timedelta(hours=6)) & (df_hourly['Hora'] <= agora + timedelta(hours=24))]
    else:
        df_focal = df_hourly

    # --- MOTOR EXPERT DE AVALIAÇÃO DE RISCO IPMA ---
    max_rajada = df_focal['Rajada (km/h)'].max()
    max_chuva_hora = df_focal['Precipitação (mm)'].max()
    acumulado_janela = df_focal['Precipitação (mm)'].sum()

    def classificar_severidade(rajada, chuva_h, acumulado):
        # Critérios operacionais adaptados do IPMA
        if rajada > 110 or chuva_h > 35 or acumulado > 50:
            return "VERMELHO", "🔴 **ALERTA VERMELHO (RISCO EXTREMO):** Perigo grave para pessoas, bens e estruturas provisórias.", \
                   "Evitar deslocações. Suspender imediatamente eventos ao ar livre. Garantir desobstrução de sarjetas e valnas (ex: zona ribeirinha e baixa de Óbidos)."
        elif (91 <= rajada <= 110) or (20 <= chuva_h <= 35) or (30 <= acumulado <= 50):
            return "LARANJA", "🟠 **AVISO LARANJA (RISCO ELEVADO):** Situação meteorológica severa com potencial de danos.", \
                   "Atenção a estruturas suspensas, quedas de árvores e pequenas escorrentes rápidas. Reforçar amarração de equipamentos em feiras/eventos."
        elif (70 <= rajada < 91) or (10 <= chuva_h < 20) or (15 <= acumulado < 30):
            return "AMARELO", "🟡 **AVISO AMARELO (RISCO MODERADO):** Condições desfavoráveis para atividades específicas.", \
                   "Monitorizar evolução local. Cuidado na circulação rodoviária devido a piso molhado e visibilidade reduzida."
        else:
            return "VERDE", "🟢 **ESTADO NORMAL (SEM ALERTAS ATIVOS):** Condições meteorológicas estáveis na região.", \
                   "Manter vigilância regular de rotina."

    nivel, titulo_alerta, conselhos = classificar_severidade(max_rajada, max_chuva_hora, acumulado_janela)

    # Caixa de Alerta Operacional no Topo
    if nivel == "VERMELHO":
        st.error(titulo_alerta)
    elif nivel == "LARANJA":
        st.warning(titulo_alerta)
    elif nivel == "AMARELO":
        st.info(titulo_alerta)
    else:
        st.success(titulo_alerta)

    # Bloco de Mensagem Pronta para Operacionais / Partilha (Telegram / WhatsApp)
    with st.expander("📋 **Gerar Mensagem de Alerta Operacional (Pronta a Partilhar)**"):
        msg_pronta = (
            f"🚨 *COMUNICADO DE PROTEÇÃO CIVIL / METEO OESTE*\n"
            f"📍 *Local:* {local_selecionado}\n"
            f"⚠️ *Estado:* {nivel}\n"
            f"💨 *Pico de Rajada Previsto:* {max_rajada:.1f} km/h\n"
            f"🌧️ *Intensidade Máx. Chuva:* {max_chuva_hora:.1f} mm/h\n\n"
            f"💡 *Recomendações:* {conselhos}"
        )
        st.code(msg_pronta, language="markdown")
        st.caption("Pode copiar este bloco diretamente para grupos de emergência ou comando operacional.")

    st.divider()

    # KPIs Operacionais
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Máx. Rajada de Vento", f"{max_rajada:.1f} km/h")
    col2.metric("Pico Chuva Horária", f"{max_chuva_hora:.1f} mm/h")
    col3.metric("Chuva Acumulada (Período)", f"{acumulado_janela:.1f} mm")
    col4.metric("Nível de Alerta", nivel)

    st.divider()

    # Gráficos Técnicos de Suporte à Decisão
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("💨 Perfil de Rajadas de Vento (Nowcast)")
        fig_v = px.line(df_focal, x='Hora', y='Rajada (km/h)', markers=True)
        fig_v.add_hline(y=70, line_dash="dash", line_color="orange", annotation_text="Limiar Amarelo (70 km/h)")
        fig_v.add_hline(y=91, line_dash="dash", line_color="red", annotation_text="Limiar Laranja (91 km/h)")
        fig_v.update_layout(margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_v, use_container_width=True)

    with c2:
        st.subheader("🌧️ Ritmo Horário de Precipitação")
        fig_c = px.bar(df_focal, x='Hora', y='Precipitação (mm)', color='Precipitação (mm)', color_continuous_scale='Blues')
        fig_c.add_hline(y=10, line_dash="dash", line_color="orange", annotation_text="Chuva Intensa (10mm/h)")
        fig_c.update_layout(margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_c, use_container_width=True)

    # Secção de Radares / Links Úteis de Apoio Operacional em Portugal
    st.divider()
    st.subheader("🛰️ Fontes de Confirmação Visual Externa (Radar e Satélite)")
    col_r1, col_r2, col_r3 = st.columns(3)
    with col_r1:
        st.markdown("[🔍 **Radar IPMA (Portugal Continental)**](https://www.ipma.pt/en/otempo/obs.radar/)")
        st.caption("Visualize em tempo real a entrada de ecos de precipitação no litoral oeste.")
    with col_r2:
        st.markdown("[🛰️ **EUMETSAT / Sat24 (Europa Ocidental)**](https://en.sat24.com/en/eu/visual)")
        st.caption("Acompanhamento de massas nubosas e sistemas frontais atlânticos.")
    with col_r3:
        st.markdown("[🌊 **Windy (Análise de Vento e Ondas)**](https://www.windy.com/)")
        st.caption("Modelação avançada de vento em alta resolução para Óbidos e Peniche.")

else:
    st.error("Erro ao sincronizar dados operacionais com a estação meteorológica.")
import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(
    page_title="Meteo Oeste — Operacional & Lagoa de Óbidos",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🌊 Centro de Operações — Lagoa de Óbidos & Região do Oeste")
st.markdown("Painel de Apoio à Decisão com cruzamento de **Meteorologia (IPMA/Open-Meteo)**, **Nowcast de Vento/Chuva** e **Previsão de Marés**.")

# Configuração de Coordenadas e Zonas de Risco da Lagoa
coords = {
    "Lagoa de Óbidos (Bom Sucesso / Margens)": {"lat": 39.3800, "lon": -9.2200, "risco": "Inundações por galgamento maregráfico e escoamento do Arnóia"},
    "
