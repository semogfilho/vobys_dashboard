# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

def render(conn, ano_selecionado, mes_chave, meses_disponiveis):
    # --- PADRONIZAÇÃO DE LAYOUT (CORRIGIDO) ---
    st.markdown("""
        <style>
            .block-container {
                padding-top: 1rem !important;
                padding-bottom: 1rem !important;
            }
            div[data-testid="stVerticalBlock"] > div:first-child {
                margin-top: 0px !important;
                padding-top: 0px !important;
            }
            div[data-testid="stHorizontalBlock"] {
                gap: 1.5rem !important;
            }
        </style>
    """, unsafe_allow_html=True)

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
                WHEN STATUS_VOBYS = 'V' THEN 'VALIDADO'
                WHEN STATUS_VOBYS = 'F' THEN 'FECHADO'
                WHEN STATUS_VOBYS = 'I' THEN 'INCONSISTENCIA DE CADASTRO'
                WHEN STATUS_VOBYS = 'O' THEN 'OUTRAS INCONSISTENCIAS'
                WHEN STATUS_VOBYS = 'E' THEN 'ERRO'
                WHEN STATUS_VOBYS = 'X' THEN 'EXCLUIDO'
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

            # SELETOR DE VISUALIZAÇÃO
            tipo_grafico = st.radio(
                "Visualiza\u00E7\u00E3o do Gr\u00E1fico:",
                ["Rosca (com Linhas)", "Barras Horizontais"],
                horizontal=True
            )
            st.markdown("<br>", unsafe_allow_html=True)

            # LAYOUT EM DUAS COLUNAS
            col_grafico, col_metricas = st.columns([1.2, 1.0])
            
            with col_grafico:
                cores_map = {
                    'ABERTO': '#1a73e8',
                    'ERRO': '#d93025',
                    'OUTRAS INCONSISTENCIAS': '#f2994a',
                    'INCONSISTENCIA DE CADASTRO': '#fbbc04',
                    'PENDENTE': '#9aa0a6',
                    'TRANSMITIDO': '#1e8e3e',
                    'FECHADO': '#343a40',
                    'EXCLUIDO': '#bdc1c6'
                }

                if tipo_grafico == "Rosca (com Linhas)":
                    # --- CONFIGURAÇÃO DA ROSCA ---
                    fig, ax = plt.subplots(figsize=(6.0, 4.2))
                    
                    df_rosca = df.copy()
                    cores = [cores_map.get(status, '#70757a') for status in df_rosca['STATUS']]
                    
                    retorno_pie = ax.pie(
                        df_rosca['QTD'], 
                        startangle=90, 
                        colors=cores,
                        pctdistance=0.65
                    )
                    wedges = retorno_pie[0]
                    
                    labels_info = []
                    
                    for i, p in enumerate(wedges):
                        qtd_atual = df_rosca['QTD'].iloc[i]
                        pct_atual = (qtd_atual / total_geral) * 100
                        status_atual = df_rosca['STATUS'].iloc[i]
                        
                        ang = (p.theta2 - p.theta1)/2. + p.theta1
                        y = np.sin(np.deg2rad(ang))
                        x = np.cos(np.deg2rad(ang))
                        
                        lado_direito = (x >= 0)
                        
                        # FORMATO SOLICITADO: ABERTO (503) - 83,4%
                        pct_str = f"{pct_atual:.1f}".replace('.', ',')
                        text_label = f"{status_atual} ({qtd_atual}) - {pct_str}%"
                        
                        if pct_atual >= 5.0:
                            # Percentual interno das fatias maiores tratado com vírgula
                            ax.text(
                                0.65 * x, 0.65 * y, f"{pct_str}%", 
                                ha="center", va="center", color="white", fontsize=8, weight="bold"
                            )
                            
                        labels_info.append({
                            'x_pie': x,
                            'y_pie': y,
                            'lado_direito': lado_direito,
                            'text': text_label,
                            'y_calculado': 1.25 * y
                        })
                    
                    # --- ALGORITMO ANTI-SOBREPOSIÇÃO VERTICAL ---
                    min_distancia_y = 0.18
                    
                    labels_dir = [l for l in labels_info if l['lado_direito']]
                    if len(labels_dir) > 1:
                        for k in range(1, len(labels_dir)):
                            if (labels_dir[k]['y_calculado'] - labels_dir[k-1]['y_calculado']) < min_distancia_y:
                                labels_dir[k]['y_calculado'] = labels_dir[k-1]['y_calculado'] + min_distancia_y

                    labels_esq = [l for l in labels_info if not l['lado_direito']]
                    if len(labels_esq) > 1:
                        for k in range(1, len(labels_esq)):
                            if (labels_esq[k-1]['y_calculado'] - labels_esq[k]['y_calculado']) < min_distancia_y:
                                labels_esq[k]['y_calculado'] = labels_esq[k-1]['y_calculado'] - min_distancia_y

                    # --- IMPRESSÃO DAS SETAS E TEXTOS ---
                    for l in labels_info:
                        x_seta = 1.35 * np.sign(l['x_pie']) if l['x_pie'] != 0 else 1.35
                        align = "left" if l['lado_direito'] else "right"
                        
                        ax.annotate(
                            l['text'], 
                            xy=(l['x_pie'], l['y_pie']), 
                            xytext=(x_seta, l['y_calculado']),
                            horizontalalignment=align, 
                            verticalalignment="center",
                            fontsize=7.5, 
                            weight="bold", 
                            color="#333333",
                            arrowprops=dict(
                                arrowstyle="-", 
                                color="#9aa0a6", 
                                lw=0.8, 
                                connectionstyle="arc3,rad=0"
                            )
                        )
                    
                    centre_circle = plt.Circle((0,0), 0.45, fc='white')
                    fig.gca().add_artist(centre_circle)
                    ax.axis('equal')  
                    ax.set_xlim(-2.4, 2.4)
                    ax.set_ylim(-1.6, 1.6)
                    st.pyplot(fig)
                    
                else:
                    # --- CONFIGURAÇÃO DAS BARRAS HORIZONTAIS ---
                    fig, ax = plt.subplots(figsize=(5.5, 3.5))
                    
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
                        pct_str = f"{pct:.1f}".replace('.', ',')
                        
                        # Ajustado padrão ao lado das barras horizontais: (QTD) - PCT%
                        ax.text(
                            width + (total_geral * 0.02), 
                            bar.get_y() + bar.get_height()/2,
                            f'({int(width)}) - {pct_str}%',
                            va='center', ha='left', fontsize=8, weight='bold', color='#333333'
                        )
                    
                    for spine in ['top', 'right', 'bottom', 'left']:
                        ax.spines[spine].set_visible(False)
                    
                    ax.xaxis.set_visible(False)
                    ax.tick_params(axis='y', colors='#333333', labelsize=8)
                    ax.set_xlim(0, total_geral * 1.25)
                    st.pyplot(fig)
                
            with col_metricas:
		# 1. Definição da Eficiência (regra unificada)
                total_fechados = df[df['STATUS'] == 'FECHADO']['QTD'].sum()
                total_transmitidos = df[df['STATUS'] == 'TRANSMITIDO']['QTD'].sum()
                total_abertos = df[df['STATUS'] == 'ABERTO']['QTD'].sum()
                
                taxa_eficiencia = ((total_fechados + total_transmitidos + total_abertos) / total_geral * 100) if total_geral > 0 else 0.0

                # 2. Métricas principais
                st.metric(label="Taxa de Eficiência", value=f"{taxa_eficiencia:.1f}%")
                
                # 3. Saúde Operacional dinâmica
                if taxa_eficiencia == 100.0:
                    st.success("**Saúde Operacional: 100% de sucesso!**")
                elif taxa_eficiencia >= 90.0:
                    st.warning(f"**Saúde Operacional: {taxa_eficiencia:.1f}% (Atenção necessária)**")
                else:
                    st.error(f"**Saúde Operacional: {taxa_eficiencia:.1f}% (Intervenção urgente)**")

                # 4. Detalhamento de falhas
                if total_falhas > 0:
                    pct_falhas = (total_falhas / total_geral * 100)
                    st.error(f"**Falhas Detectadas: {total_falhas} ({pct_falhas:.1f}% do total).**")
                    
                st.info(f"**Carga Trafegada: {total_geral} requisições.**")

            #    label_predom = "Status Predominante"
            #    st.metric(
            #        label=f".. {label_predom}", 
            #        value=maior_status, 
            #        delta=f"{maior_qtd} registros"
            #    )
            #    
            #    if total_falhas > 0:
            #        pct_falhas = (total_falhas / total_geral) * 100
            #        pct_falhas_str = f"{pct_falhas:.1f}".replace('.', ',')
            #        # Mensagem de inconsistência atualizada com a vírgula regionalizada
            #        msg_erro = "Falhas Detectadas: {} inconsist\u00EAncias ({}% do total)."
            #        st.error(f"**{msg_erro.format(total_falhas, pct_falhas_str)}**")
            #    else:
            #        msg_sucesso = "Sa\u00FAde Operacional: 100% de sucesso nas integra\u00E7\u00F5es deste m\u00EAs!"
            #        st.success(f"**{msg_sucesso}**")
            #        
            #    msg_info = "Carga Trafegada: Total de {} requisi\u00E7\u00F5es avaliadas."
            #    st.info(f"**{msg_info.format(total_geral)}**")

        except Exception as e:
            st.error(f"Erro ao gerar analise grafica: {e}")
            
    cursor.close()

