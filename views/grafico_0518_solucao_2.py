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
        "   /* Estilizacao para a legenda em formato de lista limpa */"
        "   .legenda-item {"
        "       display: flex;"
        "       align-items: center;"
        "       margin-bottom: 6px;"
        "       font-size: 13px;"
        "       font-weight: bold;"
        "       color: #333333;"
        "   }"
        "   .legenda-quadrado {"
        "       width: 12px;"
        "       height: 12px;"
        "       margin-right: 8px;"
        "       border-radius: 3px;"
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
    
    # Query limpa sem acentos para evitar problemas de codec no Linux
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
        ORDER BY QTD DESC
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
            col_grafico, col_metricas = st.columns([1.1, 1.1])
            
            with col_grafico:
                # Tamanho ideal para focar puramente no desenho da rosca
                fig, ax = plt.subplots(figsize=(3.8, 3.8))
                
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
                
                # SEGUNDA SUGESTAO: O grafico nao possui NENHUM texto acoplado (sem labels, sem autopct)
                ax.pie(
                    df['QTD'], 
                    startangle=90, 
                    colors=cores,
                    wedgeprops=dict(width=0.4, edgecolor='white', linewidth=2)
                )
                
                ax.axis('equal')  
                plt.tight_layout()
                st.pyplot(fig)
                
                st.markdown("---")
                # Renderizacao da Legenda Limpa e Explicativa logo abaixo do grafico
                st.markdown("**Legenda Detalhada:**")
                for _, row in df.iterrows():
                    status_nome = row['STATUS']
                    qtd_val = row['QTD']
                    pct_val = (qtd_val / total_geral) * 100
                    cor_hex = cores_map.get(status_nome, '#70757a')
                    
                    # HTML Customizado para simular a legenda perfeita com quadradinho colorido
                    st.markdown(
                        f'<div class="legenda-item">'
                        f'  <div class="legenda-quadrado" style="background-color: {cor_hex};"></div>'
                        f'  {status_nome}: {qtd_val} ({pct_val:.1f}%)'
                        f'</div>', 
                        unsafe_allow_html=True
                    )
                
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

