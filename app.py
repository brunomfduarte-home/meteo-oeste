import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(
    page_title="Meteo Oeste — Alertas IPMA",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🚨 Monitorização Meteorológica com Alertas IPMA — Oeste")
st.markdown("Painel analítico integrado com verificação automática de **limiares oficiais do IPMA** (Previsão e Nowcast) para Óbidos e região.")

# Barra Lateral de Controlo
st.sidebar.header("⚙️ Parâmetros Geográficos")
concelho = st.sidebar.selectbox(
    "Concelho / Zona",
    ["Óbidos", "Leiria", "Caldas da Rainha", "Peniche", "Torres Vedras", "Alenquer"]
)

dias_historico = st.sidebar.slider("Dias Anteriores (Histórico)", min_value=1, max_value=7, value=3)
dias_previsao = st.sidebar.slider("Dias de Previsão", min_value=1, max_value=7, value=3)

# Coordenadas geográficas oficiais
coords = {
    "Óbidos": {"lat": 39.3607, "lon": -9.1572},
    "Leiria": {"lat": 39.7436, "lon": -8.8071},
    "Caldas da Rainha": {"lat": 39.4036, "lon": -9.1354},
    "Peniche": {"lat": 39.3558, "lon": -9.3811},
    "Torres Vedras": {"lat": 39.0918, "lon": -9.2577},
    "Alenquer": {"lat": 39.0560, "lon": -9.0076}
}

lat = coords[concelho]["lat"]
lon = coords[concelho]["lon"]

# --- FUNÇÃO DE AQUISIÇÃO DE DADOS (Open-Meteo com dados horários e diários) ---
@st.cache_data(ttl=1800)
def obter_dados_completos(lat, lon, past_days, forecast_days):
    # Pedido que inclui dados horários (para nowcast/análise fina) e diários (previsão)
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&past_days={past_days}&forecast_days={forecast_days}&hourly=precipitation,wind_speed_10m,wind_gusts_10m,temperature_2m,relative_humidity_2m&daily=precipitation_sum,temperature_2m_mean,wind_speed_10m_max"
    
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        
        # Processar dados diários
        daily = data.get("daily", {})
        df_daily = pd.DataFrame({
            'Data': pd.to_datetime(daily.get("time", [])),
            'Precipitação (mm)': daily.get("precipitation_sum", []),
            'Temperatura Média (°C)': daily.get("temperature_2m_mean", []),
            'Vento Máximo (km/h)': daily.get("wind_speed_10m_max", [])
        })
        
        # Processar dados horários (para simular nowcast de picos)
        hourly = data.get("hourly", {})
        df_hourly = pd.DataFrame({
            'Hora': pd.to_datetime(hourly.get("time", [])),
            'Precipitação Horária (mm)': hourly.get("precipitation", []),
            'Rajada Vento (km/h)': hourly.get("wind_gusts_10m", [])
        })
        
        return df_daily, df_hourly
    return pd.DataFrame(), pd.DataFrame()

df_daily, df_hourly = obter_dados_completos(lat, lon, dias_historico, dias_previsao)

if not df_daily.empty and not df_hourly.empty:
    
    # --- MOTOR DE AVALIAÇÃO DE CRITÉRIOS IPMA ---
    # Critérios oficiais de Portugal Continental para Vento (Rajadas em km/h) e Chuva (mm/h)
    def avaliar_nivel_ipma(vento_max, chuva_horaria):
        # Vento Laranja: 91-130 | Amarelo: 70-90
        # Chuva Laranja: 21-40 mm/h | Amarelo: 10-20 mm/h
        if vento_max > 130 or chuva_horaria > 40:
            return "VERMELHO", "🔴 **AVISO VERMELHO:** Risco extremo meteorológico!"
        elif (91 <= vento_max <= 130) or (21 <= chuva_horaria <= 40):
            return "LARANJA", "🟠 **AVISO LARANJA:** Situação meteorológica de risco moderado a elevado."
        elif (70 <= vento_max < 91) or (10 <= chuva_horaria < 21):
            return "AMARELO", "🟡 **AVISO AMARELO:** Situação de risco para determinadas atividades."
        return "VERDE", "🟢 **ESTADO NORMAL:** Sem avisos meteorológicos ativos."

    # Verificar picos atuais horários (Nowcast / Curto Prazo)
    pico_vento_atual = df_hourly['Rajada Vento (km/h)'].max()
    pico_chuva_atual = df_hourly['Precipitação Horária (mm)'].max()
    
    nivel, mensagem_alerta = avaliar_nivel_ipma(pico_vento_atual, pico_chuva_atual)

    # Exibição visual do Alerta IPMA no Topo
    if nivel == "VERMELHO":
        st.error(mensagem_alerta)
    elif nivel == "LARANJA":
        st.warning(mensagem_alerta)
    elif nivel == "AMARELO":
        st.info(mensagem_alerta)
    else:
        st.success(mensagem_alerta)

    st.markdown(f"**Pico Máximo Detetado (Nowcast/Horário):** Rajada de Vento de **{pico_vento_atual:.1f} km/h** | Precipitação Horária de **{pico_chuva_atual:.1f} mm/h**")
    st.divider()

    # Indicadores Principais (KPIs)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Precipitação Acumulada (Total)", f"{df_daily['Precipitação (mm)'].sum():.1f} mm")
    col2.metric("Temp. Média Período", f"{df_daily['Temperatura Média (°C)'].mean():.1f} °C")
    col3.metric("Rajada Máxima Prevista", f"{pico_vento_atual:.1f} km/h")
    col4.metric("Zona Ativa", concelho)

    st.divider()

    # Gráficos Interativos (Plotly)
    c_graf1, c_graf2 = st.columns(2)

    with c_graf1:
        st.subheader(f"💧 Acumulado Diário de Chuva ({concelho})")
        fig_p = px.bar(
            df_daily, x='Data', y='Precipitação (mm)', 
            color='Precipitação (mm)', 
            color_continuous_scale='Blues'
        )
        # Linha de corte IPMA para Aviso Amarelo de Chuva (10 mm/h ou acumulados equivalentes)
        fig_p.add_hline(y=15, line_dash="dash", line_color="orange", annotation_text="Limiar de Referência IPMA", annotation_position="top left")
        fig_p.update_layout(margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_p, use_container_width=True)

    with c_graf2:
        st.subheader("💨 Evolução das Rajadas de Vento (Nowcast Horário)")
        fig_t = px.line(
            df_hourly.tail(48), x='Hora', y='Rajada Vento (km/h)', 
            markers=False
        )
        # Linha de corte IPMA para Aviso Amarelo de Vento (70 km/h)
        fig_t.add_hline(y=70, line_dash="dash", line_color="orange", annotation_text="Limiar Aviso Amarelo IPMA (70 km/h)", annotation_position="top left")
        fig_t.add_hline(y=91, line_dash="dash", line_color="red", annotation_text="Limiar Aviso Laranja IPMA (91 km/h)", annotation_position="top left")
        fig_t.update_layout(margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_t, use_container_width=True)

    # Mapa Geográfico
    st.subheader(f"🗺️ Localização Geográfica — {concelho}")
    df_mapa = pd.DataFrame({'lat': [lat], 'lon': [lon]})
    st.map(df_mapa, latitude='lat', longitude='lon', zoom=11, size=400)

    # Exportação de Dados
    st.divider()
    csv = df_daily.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Exportar Dados para Relatório (CSV)",
        data=csv,
        file_name=f"meteo_ipma_{concelho.lower()}_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )
else:
    st.error("Não foi possível carregar os dados meteorológicos.")
