import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(
    page_title="Meteo Oeste — Monitorização",
    page_icon="🌦️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Cabeçalho
st.title("🌦️ Sistema de Monitorização Meteorológica — Oeste")
st.markdown("Painel analítico integrado focado em **Óbidos, Leiria e concelhos limítrofes**.")

# Sidebar
st.sidebar.header("⚙️ Parâmetros de Seleção")
concelho = st.sidebar.selectbox(
    "Concelho / Zona",
    ["Óbidos", "Leiria", "Caldas da Rainha", "Peniche", "Torres Vedras", "Alenquer"]
)

dias = st.sidebar.slider("Janela Temporal (Dias)", min_value=1, max_value=30, value=7)
fonte_dados = st.sidebar.selectbox("Fonte de Dados Base", ["ERA5-Land (Reanálise)", "GFS Global 0.25º", "IPMA / Open-Meteo"])

# Coordenadas dos Concelhos
coords = {
    "Óbidos": [39.3607, -9.1572],
    "Leiria": [39.7436, -8.8071],
    "Caldas da Rainha": [39.4036, -9.1354],
    "Peniche": [39.3558, -9.3811],
    "Torres Vedras": [39.0918, -9.2577],
    "Alenquer": [39.0560, -9.0076]
}

# Dados Simulado/Modelo Temporal
np.random.seed(42)
datas = [datetime.now() - timedelta(days=i) for i in range(dias)]
datas.reverse()

df = pd.DataFrame({
    'Data': datas,
    'Precipitação (mm)': np.random.exponential(scale=5, size=dias).round(1),
    'Temperatura Média (°C)': (15 + np.random.normal(0, 2.5, size=dias)).round(1),
    'Vento Máximo (km/h)': (20 + np.random.exponential(12, size=dias)).round(1),
    'Humidade Relativa (%)': np.clip((65 + np.random.normal(0, 10, size=dias)), 30, 100).round(1)
})

# KPIs
col1, col2, col3, col4 = st.columns(4)
col1.metric("Precipitação Acumulada", f"{df['Precipitação (mm)'].sum():.1f} mm")
col2.metric("Temp. Média Período", f"{df['Temperatura Média (°C)'].mean():.1f} °C")
col3.metric("Rajada Máxima", f"{df['Vento Máximo (km/h)'].max():.1f} km/h")
col4.metric("Humidade Média", f"{df['Humidade Relativa (%)'].mean():.1f} %")

st.divider()

# Gráficos Interativos
c_graf1, c_graf2 = st.columns(2)

with c_graf1:
    st.subheader(f"💧 Acumulado Diário de Chuva ({concelho})")
    fig_p = px.bar(
        df, x='Data', y='Precipitação (mm)', 
        color='Precipitação (mm)', 
        color_continuous_scale='Blues'
    )
    fig_p.update_layout(margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_p, use_container_width=True)

with c_graf2:
    st.subheader("🌡️ Temperatura Média & Rajada de Vento")
    fig_t = px.line(
        df, x='Data', y=['Temperatura Média (°C)', 'Vento Máximo (km/h)'], 
        markers=True
    )
    fig_t.update_layout(margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_t, use_container_width=True)

# Mapa
st.subheader(f"🗺️ Localização Geográfica — {concelho}")
df_mapa = pd.DataFrame({
    'lat': [coords[concelho][0]], 
    'lon': [coords[concelho][1]]
})
st.map(df_mapa, latitude='lat', longitude='lon', zoom=11, size=400)

# Exportação
st.divider()
csv = df.to_csv(index=False).encode('utf-8')
st.download_button(
    label="📥 Exportar Dados da Região (CSV)",
    data=csv,
    file_name=f"meteo_{concelho.lower()}_{datetime.now().strftime('%Y%m%d')}.csv",
    mime="text/csv"
)
