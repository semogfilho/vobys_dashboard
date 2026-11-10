# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

def render(conn, ano_selecionado, mes_chave, meses_disponiveis):
    # --- REDUCAO AGRESSIVA DE ESPACOS PELO CSS ---
    st.markdown(
        "<style>"
        "   .block-container {"
        "       padding-top: 0.5rem !important;"
        "       padding-bottom: 0.5rem !important;"
        "   }"
        "   div[data-testid='stVerticalBlock'] > div:first-child {"
        "       margin-top: 0px !important;"
        "       padding-top: 0px !important;"
        "   }"
        "   /* Espacamento interno menor entre elements das colunas */"
        "   div[data-testid='stHorizontalBlock'] {"
        "       gap: 1.5rem !important;"
        "   }"
        "   /* Estilizacao para deixar o radio inline mais elegante */"
        "   div[data-testid='stRadio'] > label {"
        "       font-weight: bold !important;"
        "       color: #333333 !important;"
        "   }"
        "</style>",
        unsafe_allow_html=True
    )

    titulo_grafico = "Painel de Controle de Folhas - Gr\u00E1fico de Status"
    st.title(f".. {titulo_grafico}")
    
    subtitulo = f"Distribui\u00E7\u00E3o percentual volum\u00E9trica das requisi\u00E7\u00F5es em {meses_disponiveis[mes_chave]}/{ano_selecionado}."
    st.markdown(f"**{subtitulo}**")
    st.markdown("---")

    cursor = conn.cursor()
    
    # Query trazendo os dados base
    sql = f"""
        SELECT 
            CASE 
                WHEN STATUS_VOBYS = 'P' THEN 'PENDENTE'
                WHEN STATUS_VOBYS = 'T' THEN 'TRANSMITIDO'
                WHEN STATUS_VOBYS = 'A' THEN 'ABERTO'
                WHEN STATUS_VOBYS = 'F' THEN 'FECHADO'
                WHEN STATUS_VOBYS = 'I' THEN 'INCONSISTENCIA DE CADASTRO'
                WHEN STATUS_VOBYS = 'O' THEN 'OUTRAS INCONSISTENCIAS'
                WHEN STATUS_VOBYS = 'E' THEN 'ERRO'
                ELSE 'ABERTO'
            END AS STATUS,
            COUNT(*) AS QTD
        FROM sw_publico.SIAFE_EVENTO_INTEGRACAO
        WHERE ANO = {ano_selecionado} AND MES = {int(mes_chave)}
        GROUP BY STATUS_VOBYS
    """

    with st.spinner("Gerando analise grafica..."):
        try:
            cursor.execute(sql)
            rows = cursor.fetchall()
            
            if not rows:
                st.info(f"Nenhum dado encontrado para gerar o grafico em {meses_disponiveis[mes_chave]}/{ano_selecionado}.")
                cursor.close()
                return
            
            df = pd.DataFrame(rows, columns=['STATUS', 'QTD'])
            df['QTD'] = df['QTD'].astype(int)
            
            total_geral = df['QTD'].sum()
            
            # Filtro de falhas
            df_erros = df[df['STATUS'].str.contains('ERRO|INCONSISTENCIA', na=False)]
            total_falhas = df_erros['QTD'].sum()
            
            row_max = df.loc[df['QTD'].idxmax()]
            maior_status = row_max['STATUS']
            maior_qtd = row_max['QTD']

            # NOVO SELETOR: Posicionado exatamente onde você desenhou o "TIPO"
            tipo_grafico = st.radio(
                "Visualiza\u00E7\u00E3o do Gr\u00E1fico:",
                ["Gr\u00E1fico de Rosca", "Gr\u00E1fico de Barras"],
                horizontal=True
            )
            st.markdown("<br>", unsafe_allow_html=True)

            # LAYOUT EM DUAS COLUNAS
            col_grafico, col_metricas = st.columns([1.2, 1.0])
            
            with col_grafico:
                # Paleta de Cores unificada para ambos os cenários
                cores_map = {
                    'ABERTO': '#1a73e8',
                    'ERRO': '#d93025',
                    'OUTRAS INCONSISTENCIAS': '#f2994a',
                    'INCONSISTENCIA DE CADASTRO': '#fbbc04',
                    'PENDENTE': '#9aa0a6',
                    'TRANSMITIDO': '#1e8e3e',
                    'FECHADO': '#343a40'
                }

                if tipo_grafico == "Gr\u00E1fico de Rosca":
                    # --- CONFIGURACAO DA SOLUCAO 1 (ROSCA COM CALLOUTS) ---
                    fig, ax = plt.subplots(figsize=(5.8, 3.8))
                    
                    # Ordenacao original para a rosca bater com seus testes anteriores
                    df_rosca = df.copy()
                    cores = [cores_map.get(status, '#70757a') for status in df_rosca['STATUS']]
                    
                    retorno_pie = ax.pie(
                        df_rosca['QTD'], 
                        startangle=90, 
                        colors=cores,
                        pctdistance=0.65
                    )
                    wedges = retorno_pie[0]
                    
                    for i, p in enumerate(wedges):
                        qtd_atual = df_rosca['QTD'].iloc[i]
                        pct_atual = (qtd_atual / total_geral) * 100
                        status_atual = df_rosca['STATUS'].iloc[i]
                        
                        ang = (p.theta2 - p.theta1)/2. + p.theta1
                        y = np.sin(np.deg2rad(ang))
                        x = np.cos(np.deg2rad(ang))
                        
                        horizontalalignment = {-1: "right", 1: "left"}[int(np.sign(x))]
                        connectionstyle = f"angle,angleA=0,angleB={ang}"
                        
                        if pct_atual < 5.0:
                            text_label = f"{status_atual} ({pct_atual:.1f}%)"
                            offset_y = 1.3 * y
                            if 80 < ang < 100: 
                                offset_y += 0.15
                            
                            ax.annotate(
                                text_label, xy=(x, y), xytext=(1.4 * np.sign(x), offset_y),
                                horizontalalignment=horizontalalignment, verticalalignment="center",
                                fontsize=7.5, weight="bold", color="#333333",
                                arrowprops=dict(arrowstyle="-", color="#9aa0a6", lw=0.8, connectionstyle=connectionstyle)
                            )
                        else:
                            ax.annotate(
                                status_atual, xy=(x, y), xytext=(1.4 * np.sign(x), 1.3 * y),
                                horizontalalignment=horizontalalignment, verticalalignment="center",
                                fontsize=7.5, weight="bold", color="#333333",
                                arrowprops=dict(arrowstyle="-", color="#9aa0a6", lw=0.8, connectionstyle=connectionstyle)
                            )
                            ax.text(
                                0.65 * x, 0.65 * y, f"{pct_atual:.1f}%", 
                                ha="center", va="center", color="white", fontsize=8, weight="bold"
                            )
                    
                    centre_circle = plt.Circle((0,0), 0.45, fc='white')
                    fig.gca().add_artist(centre_circle)
                    ax.axis('equal')  
                    ax.set_xlim(-2.0, 2.0)
                    ax.set_ylim(-1.6, 1.6)
                    
                else:
                    # --- CONFIGURACAO DA SOLUCAO 3 (BARRAS HORIZONTAIS) ---
                    fig, ax = plt.subplots(figsize=(5.5, 3.5))
                    
                    # Barras horizontais exigem ordenacao ASC para o maior ficar no topo
                    df_barras = df.sort_values(by='QTD', ascending=True)
                    cores = [cores_map.get(status, '#70757a') for status in df_barras['STATUS']]
                    
                    bars = ax.barh(
                        df_barras['STATUS'], 
                        df_barras['QTD'], 
                        color=cores,
                        height=0.6,
                        edgecolor='none'
                    )
                    
                    for bar in bars:
                        width = bar.get_width()
                        pct = (width / total_geral) * 100
                        
                        ax.text(
                            width + (total_geral * 0.02), 
                            bar.get_y() + bar.get_height()/2,
                            f'{int(width)} ({pct:.1f}%)',
                            va='center', ha='left', fontsize=8, weight='bold', color='#333333'
                        )
                    
                    for spine in ['top', 'right', 'bottom', 'left']:
                        ax.spines[spine].set_visible(False)
                    
                    ax.xaxis.set_visible(False)
                    ax.tick_params(axis='y', colors='#333333', labelsize=8)
                    ax.set_xlim(0, total_geral * 1.25)

                plt.tight_layout()
                st.pyplot(fig)
                
            with col_metricas:
                label_predom = "Status Predominante"
                st.metric(
                    label=f".. {label_predom}", 
                    value=maior_status, 
                    delta=f"{maior_qtd} registros"
                )
                
                if total_falhas > 0:
                    pct_falhas = (total_falhas / total_geral) * 100
                    msg_erro = "Falhas Detectadas: {} inconsist\u00EAncias ({:.1f}% do total)."
                    st.error(f"**{msg_erro.format(total_falhas, pct_falhas)}**")
                else:
                    msg_sucesso = "Sa\u00FAde Operacional: 100% de sucesso nas integra\u00E7\u00F5es deste m\u00EAs!"
                    st.success(f"**{msg_sucesso}**")
                    
                msg_info = "Carga Trafegada: Total de {} requisi\u00E7\u00F5es avaliadas."
                st.info(f"**{msg_info.format(total_geral)}**")

        except Exception as e:
            st.error(f"Erro ao gerar analise grafica: {e}")
            
    cursor.close()

