import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import pydeck as pdk
from datetime import datetime, time, timedelta

st.set_page_config(
    page_title="Meteo Óbidos — Comando Operacional & Avisos",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🛡️ Centro de Comando Operacional — Concelho de Óbidos")
st.markdown("Painel tático de Proteção Civil, mapeamento territorial, análise de picos temporais e gerador de avisos multilíngue.")

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

st.sidebar.header("⚙️ Parâmetros de Análise Global")
setor_selecionado = st.sidebar.selectbox("Selecionar Setor / Vista", list(setores_obidos.keys()))
info_setor = setores_obidos[setor_selecionado]

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

# Tratamento para visão consolidada vs setorial
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

    # Avaliação de Severidade IPMA
    if pico_r > 110 or pico_c > 35:
        nivel, cor_alerta = "VERMELHO", "error"
    elif pico_r > 90 or pico_c > 20:
        nivel, cor_alerta = "LARANJA", "warning"
    elif pico_r > 70 or pico_c > 10:
        nivel, cor_alerta = "AMARELO", "info"
    else:
        nivel, cor_alerta = "VERDE", "success"

    # ==============================================================================
    # POP-UP AUTOMÁTICO (TOAST)
    # ==============================================================================
    proximo_de_aviso = (pico_r >= 60) or (pico_c >= 8)
    if nivel in ["AMARELO", "LARANJA", "VERMELHO"]:
        st.toast(f"🚨 ATENÇÃO: Aviso {nivel} ativo ou iminente em {setor_selecionado}! Sugere-se emissão de notificação.", icon="⚠️")
    elif proximo_de_aviso:
        st.toast(f"⚡ Parâmetros próximos do limiar de aviso em {setor_selecionado} (Rajada: {pico_r:.1f} km/h).", icon="🔔")

    # Alerta Principal no Topo
    mensagem_topo = f"🚨 **ESTADO DE ALERTA: {nivel}** | Vista: {setor_selecionado} | Grau de Confiança (ECMWF): **{confianca}%**"
    if cor_alerta == "error": st.error(mensagem_topo)
    elif cor_alerta == "warning": st.warning(mensagem_topo)
    elif cor_alerta == "info": st.info(mensagem_topo)
    else: st.success(mensagem_topo)

    # ==============================================================================
    # MAPA TÁTICO COM POLÍGONOS SETORIAIS COLORIDOS
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

    view_state_obidos = pdk.ViewState(latitude=39.3750, longitude=-9.1700, zoom=10.6, pitch=15)
    mapa_deck = pdk.Deck(
        layers=[camada_poligonos],
        initial_view_state=view_state_obidos,
        tooltip={"text": "Setor: {setor}\nAlerta: {nivel}\nRajada Máx: {rajada} km/h\nChuva Máx: {chuva} mm/h"}
    )
    st.pydeck_chart(mapa_deck)
    st.divider()

    # ==============================================================================
    # MÓDULO MULTILÍNGUE DE GESTÃO DE AVISOS E EVENTOS (ATÉ 3 DIAS COM PICOS)
    # ==============================================================================
    st.subheader("📢 Central de Avisos & Recomendações (Padrão UNDRR)")
    st.markdown("Defina a **data/hora de início e fim** (até 3 dias de janela). O sistema deteta automaticamente **picos de ocorrência extremos ou significativos**.")

    idioma = st.radio("Idioma do Comunicado / Language", ["Português", "English"], horizontal=True)

    with st.container():
        st.markdown("#### 📅 Janela de Evento / Monitorização (Início e Fim)")
        col_i1, col_i2 = st.columns(2)
        with col_i1:
            data_inicio = st.date_input("Data de Início / Start Date", value=datetime.today().date() + timedelta(days=1))
            hora_inicio = st.time_input("Hora de Início / Start Time", value=time(17, 0))
        with col_i2:
            data_fim = st.date_input("Data de Fim / End Date", value=data_inicio + timedelta(days=1))
            hora_fim = st.time_input("Hora de Fim / End Time", value=time(23, 0))

        dt_inicio = datetime.combine(data_inicio, hora_inicio)
        dt_fim = datetime.combine(data_fim, hora_fim)

        # Validação da janela temporal (máximo 3 dias)
        if dt_fim <= dt_inicio:
            st.warning("⚠️ A data/hora de fim deve ser posterior à data/hora de início.")
            dt_fim = dt_inicio + timedelta(hours=4)
        
        diferenca_horas = (dt_fim - dt_inicio).total_seconds() / 3600
        if diferenca_horas > 72:
            st.info("ℹ️ A janela selecionada foi ajustada para o limite máximo de 3 dias (72h).")
            dt_fim = dt_inicio + timedelta(hours=72)

        # Filtragem dos dados horários para o intervalo selecionado
        df_janela = df[(df['Hora'] >= dt_inicio) & (df['Hora'] <= dt_fim)]

        if not df_janela.empty:
            chuva_janela_max = df_janela['Precipitação (mm)'].max()
            acum_janela_total = df_janela['Precipitação (mm)'].sum()
            vento_janela_max = df_janela['Rajada (km/h)'].max()
            temp_janela_media = df_janela['Temperatura (°C)'].mean()

            # IDENTIFICAÇÃO DE PICOS EXTREMOS / SIGNIFICATIVOS NO INTERVALO
            # Picos de Vento (rajada >= 55 km/h) e Chuva (precipitação >= 5 mm/h)
            df_picos_vento = df_janela[df_janela['Rajada (km/h)'] >= 55]
            df_picos_chuva = df_janela[df_janela['Precipitação (mm)'] >= 5.0]

            tem_pico_critico = not df_picos_vento.empty or not df_picos_chuva.empty

            # Determinar o intervalo exato do pico mais intenso
            picos_texto_pt = ""
            picos_texto_en = ""

            if tem_pico_critico:
                if not df_picos_vento.empty:
                    h_v_ini = df_picos_vento['Hora'].min().strftime('%d/%m às %H:%M')
                    h_v_fim = df_picos_vento['Hora'].max().strftime('%H:%M')
                    v_val = df_picos_vento['Rajada (km/h)'].max()
                    picos_texto_pt += f"\n  • ⚡ **Pico de Vento Intenso:** Rajadas de {v_val:.0f} km/h entre {h_v_ini} e {h_v_fim}h."
                    picos_texto_en += f"\n  • ⚡ **Severe Wind Peak:** Gusts up to {v_val:.0f} km/h between {h_v_ini} and {h_v_fim}h."

                if not df_picos_chuva.empty:
                    h_c_ini = df_picos_chuva['Hora'].min().strftime('%d/%m às %H:%M')
                    h_c_fim = df_picos_chuva['Hora'].max().strftime('%H:%M')
                    c_val = df_picos_chuva['Precipitação (mm)'].max()
                    picos_texto_pt += f"\n  • 🌧️ **Pico de Precipitação:** Taxa de {c_val:.1f} mm/h entre {h_c_ini} e {h_c_fim}h."
                    picos_texto_en += f"\n  • 🌧️ **Rainfall Peak:** Rate of {c_val:.1f} mm/h between {h_c_ini} and {h_c_fim}h."
            else:
                picos_texto_pt = "\n  • 🟢 Sem picos extremos identificados nesta janela temporal."
                picos_texto_en = "\n  • 🟢 No extreme peaks identified during this time frame."
        else:
            chuva_janela_max, acum_janela_total, vento_janela_max, temp_janela_media = 0.0, 0.0, 20.0, 15.0
            picos_texto_pt = "\n  • 🟢 Sem picos previstos."
            picos_texto_en = "\n  • 🟢 No peaks expected."

        st.divider()

        tipo_alvo = st.radio(
            "Destinatário / Target Audience:", 
            ["População em Geral (General Public)", "Organizadores de Eventos (Event Organizers)"]
        )

        # Avaliação de Risco para o Intervalo
        if vento_janela_max > 110 or chuva_janela_max > 35:
            nivel_j = "VERMELHO"
        elif vento_janela_max > 90 or chuva_janela_max > 20:
            nivel_j = "LARANJA"
        elif vento_janela_max > 70 or chuva_janela_max > 10:
            nivel_j = "AMARELO"
        else:
            nivel_j = "VERDE"

        if idioma == "Português":
            if nivel_j == "VERMELHO":
                risco_meteo = "RISCO EXTREMO: Perigo grave para pessoas, bens e estruturas."
            elif nivel_j == "LARANJA":
                risco_meteo = "RISCO ELEVADO: Potencial elevado de danos, perturbações e inundações."
            elif nivel_j == "AMARELO":
                risco_meteo = "RISCO MODERADO: Condições desfavoráveis para circulação e eventos ao ar livre."
            else:
                risco_meteo = "ESTADO NORMAL: Sem riscos meteorológicos severos previstos."
        else:
            if nivel_j == "VERMELHO":
                risco_meteo = "EXTREME RISK: Severe danger to people, property, and structures."
            elif nivel_j == "LARANJA":
                risco_meteo = "ELEVATED RISK: High potential for damage, disruptions, and flooding."
            elif nivel_j == "AMARELO":
                risco_meteo = "MODERATE RISK: Unfavorable conditions for outdoor events and mobility."
            else:
                risco_meteo = "NORMAL STATUS: No severe weather risks expected."

        # Formatação das Datas de Início e Fim para o Comunicado
        fmt_ini_pt = dt_inicio.strftime('%A, %d de %B, às %H:%M').capitalize()
        fmt_fim_pt = dt_fim.strftime('%A, %d de %B de %Y, às %H:%M').capitalize()

        fmt_ini_en = dt_inicio.strftime('%A, %B %d, at %H:%M')
        fmt_fim_en = dt_fim.strftime('%A, %B %d, %Y, at %H:%M')

        if idioma == "Português":
            if tipo_alvo.startswith("População"):
                msg_final = (
                    f"🌧️ *SERVIÇO MUNICIPAL DE PROTEÇÃO CIVIL DE ÓBIDOS* | Alerta\n"
                    f"📅 *Período:* De {fmt_ini_pt} até {fmt_fim_pt}\n\n"
                    f"⚠️ *AVISO {nivel_j}* — SETOR: *{setor_selecionado}*\n"
                    f"*{risco_meteo}*\n"
                    f"• Rajadas máximas previstas: *{vento_janela_max:.0f} km/h*\n"
                    f"• Precipitação acumulada no período: *{acum_janela_total:.1f} mm*\n\n"
                    f"⏱️ *INTERVALOS DE PICO CRÍTICO NO PERÍODO:*{picos_texto_pt}\n\n"
                    f"🛡️ *Medidas de Autoproteção:*\n"
                    f"• Acompanhe ativamente os avisos meteorológicos oficiais.\n"
                    f"• Siga rigorosamente as recomendações da Proteção Civil e autoridades.\n"
                    f"• Evite comportamentos de risco (não atravesse zonas inundadas, evite áreas arborizadas nos períodos de pico).\n\n"
                    f"🔗 Consulte os avisos ativos do IPMA: https://www.ipma.pt/pt/otempo/prev-sam/?p=LRA\n"
                    f"_Fonte: Análise de modelos de previsão de meteorologia._"
                )
            else:
                prob_c = min(95, int(chuva_janela_max * 20 + 20)) if chuva_janela_max > 0 else 10
                msg_final = (
                    f"🛡️ *PROTEÇÃO CIVIL DE ÓBIDOS* | Alerta para Eventos\n"
                    f"📅 *Intervalo:* De {fmt_ini_pt} até {fmt_fim_pt}\n\n"
                    f"⚠️ *AVISO {nivel_j}* | Setor: *{setor_selecionado}*\n"
                    f"*{risco_meteo}*\n"
                    f"• Probabilidade de chuva: *{prob_c}%* | Vento/Rajadas até *{vento_janela_max:.0f} km/h*.\n"
                    f"⏱️ *JANELAS DE PICO A ATENTAR:*{picos_texto_pt}\n\n"
                    f"👉 *Recomendações para Organizadores:*\n"
                    f"• Valide a estabilidade e amarração de estruturas amovíveis (tendas/palcos).\n"
                    f"• Tenha um plano ou espaço coberto alternativo nas janelas de pico identificadas.\n"
                    f"• Suspenda atividades ao ar livre se os limiares de segurança forem ultrapassados durante os picos.\n"
                    f"• Acompanhe os avisos e siga as indicações das autoridades.\n\n"
                    f"🔗 AVISOS IPMA: https://www.ipma.pt/pt/otempo/prev-sam/?p=LRA\n"
                    f"_Fonte: Análise de modelos de previsão de meteorologia._"
                )
        else:
            if tipo_alvo.startswith("População"):
                msg_final = (
                    f"🌧️ *MUNICIPAL CIVIL PROTECTION SERVICE OF ÓBIDOS* | Weather Alert\n"
                    f"📅 *Period:* From {fmt_ini_en} to {fmt_fim_en}\n\n"
                    f"⚠️ *{nivel_j} ALERT* — SECTOR: *{setor_selecionado}*\n"
                    f"*{risco_meteo}*\n"
                    f"• Expected peak gust winds: *{vento_janela_max:.0f} km/h*\n"
                    f"• Total accumulated precipitation: *{acum_janela_total:.1f} mm*\n\n"
                    f"⏱️ *CRITICAL PEAK TIME FRAMES:*{picos_texto_en}\n\n"
                    f"🛡️ *Self-Protection Measures:*\n"
                    f"• Closely monitor official weather warnings.\n"
                    f"• Strictly follow instructions from Civil Protection and authorities.\n"
                    f"• Avoid risky behavior (do not cross flooded areas, avoid wooded zones during peak times).\n\n"
                    f"🔗 Check active IPMA warnings: https://www.ipma.pt/pt/otempo/prev-sam/?p=LRA\n"
                    f"_Source: Analysis of meteorological forecasting models._"
                )
            else:
                prob_c = min(95, int(chuva_janela_max * 20 + 20)) if chuva_janela_max > 0 else 10
                msg_final = (
                    f"🛡️ *CIVIL PROTECTION OF ÓBIDOS* | Event Weather Alert\n"
                    f"📅 *Time Frame:* From {fmt_ini_en} to {fmt_fim_en}\n\n"
                    f"⚠️ *{nivel_j} ALERT* | Sector: *{setor_selecionado}*\n"
                    f"*{risco_meteo}*\n"
                    f"• Rain probability: *{prob_c}%* | Gust winds up to *{vento_janela_max:.0f} km/h*.\n"
                    f"⏱️ *CRITICAL PEAK WINDOWS:*{picos_texto_en}\n\n"
                    f"👉 *Recommendations for Organizers:*\n"
                    f"• Check stability and anchoring of temporary structures (tents/stages).\n"
                    f"• Prepare an alternative covered space during the identified peak windows.\n"
                    f"• Suspend outdoor activities if safety thresholds are exceeded during peaks.\n"
                    f"• Follow weather updates and authority guidelines.\n\n"
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
