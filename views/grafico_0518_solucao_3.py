# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

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
        "</style>",
        unsafe_allow_html=True
    )

    titulo_grafico = "Painel de Controle de Folhas - Gr\u00E1fico de Status"
    st.title(f".. {titulo_grafico}")
    
    subtitulo = f"Distribui\u00E7\u00E3o percentual volum\u00E9trica das requisi\u00E7\u00F5es em {meses_disponiveis[mes_chave]}/{ano_selecionado}."
    st.markdown(f"**{subtitulo}**")
    st.markdown("---")

    cursor = conn.cursor()
    
    # Query ordenada por quantidade para a maior barra ficar no topo do grafico
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
        ORDER BY QTD ASC
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

            # LAYOUT EM DUAS COLUNAS
            col_grafico, col_metricas = st.columns([1.2, 1.0])
            
            with col_grafico:
                # Ajustamos o tamanho da figura para barras horizontais
                fig, ax = plt.subplots(figsize=(5.5, 3.5))
                
                cores_map = {
                    'ABERTO': '#1a73e8',
                    'ERRO': '#d93025',
                    'OUTRAS INCONSISTENCIAS': '#f2994a',
                    'INCONSISTENCIA DE CADASTRO': '#fbbc04',
                    'PENDENTE': '#9aa0a6',
                    'TRANSMITIDO': '#1e8e3e',
                    'FECHADO': '#343a40'
                }
                cores = [cores_map.get(status, '#70757a') for status in df['STATUS']]
                
                # TERCEIRA SUGESTAO: Criacao das barras horizontais (barh)
                bars = ax.barh(
                    df['STATUS'], 
                    df['QTD'], 
                    color=cores,
                    height=0.6,
                    edgecolor='none'
                )
                
                # Adiciona o texto de quantidade e percentual logo a direita de cada barra
                for bar in bars:
                    width = bar.get_width()
                    pct = (width / total_geral) * 100
                    
                    # Escreve o rotulo formatado: Ex: "461 (76.5%)"
                    ax.text(
                        width + (total_geral * 0.02), # Pequeno offset para o texto nao grudar na barra
                        bar.get_y() + bar.get_height()/2,
                        f'{int(width)} ({pct:.1f}%)',
                        va='center', 
                        ha='left', 
                        fontsize=8, 
                        weight='bold',
                        color='#333333'
                    )
                
                # Remove as linhas pretas de borda (Spines) do grafico para um visual clean
                for spine in ['top', 'right', 'bottom', 'left']:
                    ax.spines[spine].set_visible(False)
                
                # Remove os tracinhos dos eixos e o eixo X (ja que os numeros estao nas pontas das barras)
                ax.xaxis.set_visible(False)
                ax.tick_params(axis='y', colors='#333333', labelsize=8)
                
                # Da uma folga no limite do eixo X para o texto do maior valor nao ser cortado na direita
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

