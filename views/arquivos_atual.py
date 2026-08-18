# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import os
import re

def render(conn, ano_selecionado, mes_chave, meses_disponiveis):
    # --- CSS AVANÇADO ---
    st.markdown("""
        <style>
            .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; }
            div[data-testid="stMetric"] { background-color: #f8f9fa; padding: 10px 15px !important; border-radius: 8px !important; border: 1px solid #e9ecef !important; }
        </style>
    """, unsafe_allow_html=True)

    st.title(".. Auditoria de Integração - Batimento Bidirecional")
    st.markdown(f"**Validação cruzada (Base Lógica ⇄ Armazenamento Físico) dos layouts para {meses_disponiveis[mes_chave]}/{ano_selecionado}.**")
    st.markdown("---")

    cursor = conn.cursor()
    
    # Query mantida com a inclusão do ID_SIAFE_EVENTO_INTEGRACAO
    sql_estrategico = f"""
        SELECT 
            ID_SIAFE_EVENTO_INTEGRACAO,
            TRIM(IND_TIPO_REQUISICAO) AS TIPO,
            TRIM(CODIGO_SEFAZ) AS SEFAZ,
            SUBSTR(TRIM(TIPO_FOLHA_SEFAZ), 2, 1) AS TIPO_FOLHA,
            TRIM(TIPO_ARQUIVO) AS TIPO_ARQ,
            TRIM(CODIGO_RELATORIO) AS RELATORIO
        FROM sw_publico.SIAFE_EVENTO_INTEGRACAO
        WHERE ano = {ano_selecionado} AND mes = {int(mes_chave)}
    """

    with st.spinner("Realizando batimento bidirecional..."):
        try:
            cursor.execute(sql_estrategico)
            rows = cursor.fetchall()

            banco_contagem = {'V1': 0, 'V2': 0, 'V3': 0, 'V4': 0}
            banco_para_ftp_encontrados = {'V1': 0, 'V2': 0, 'V3': 0, 'V4': 0}
            set_arquivos_banco = set()  
            arquivos_faltantes_no_ftp = []
            arquivos_orfaos_no_banco = []
            total_arquivos_fisicos_pasta = {'V1': 0, 'V2': 0, 'V3': 0, 'V4': 0}

            # Lógica de processamento (Banco -> Físico)
            for row in rows:
                id_reg, tipo, sefaz, tipo_folha, tipo_arq, relatorio = row
                tipo_limpo = str(tipo).strip().upper() if tipo else ""
                
                if tipo_limpo in banco_contagem:
                    banco_contagem[tipo_limpo] += 1
                    pasta = '/home/vobys/ftp/data/SIAPE-COLABORADORES/' if tipo_limpo == 'V1' else ('/home/vobys/ftp/data/SIAPE-CREDITOS/' if tipo_limpo == 'V2' else '/home/vobys/ftp/data/SIAPE-FOLHAS/')
                    prefixo = 'FP_COL_' if tipo_limpo == 'V1' else ('FP_CRE_' if tipo_limpo == 'V2' else 'FP_')
                    
                    nome_base = f"{tipo_folha}_{ano_selecionado}{int(mes_chave):02d}_{tipo_arq}_{relatorio}.csv"
                    nome_arq = f"{prefixo}{sefaz}_{nome_base}"
                    
                    if os.path.exists(os.path.join(pasta, nome_arq)):
                        banco_para_ftp_encontrados[tipo_limpo] += 1
                        set_arquivos_banco.add(nome_arq)
                    else:
                        arquivos_faltantes_no_ftp.append({
                            "ID_SIAFE": id_reg,
                            "CATEGORIA": tipo_limpo,
                            "ARQUIVO_ESPERADO": nome_arq,
                            "STATUS": "Pendente de Geração Física"
                        })

            # Processamento (Físico -> Banco) omitido para brevidade, mas deve ser mantido conforme seu original
            
            # Montagem do resumo estatístico
            df_batimento = pd.DataFrame([
                {"CATEGORIA": "V4", "QTD_METADADOS": banco_contagem['V4'], "CONFIRMADOS_OK": banco_para_ftp_encontrados['V4']},
                {"CATEGORIA": "V3", "QTD_METADADOS": banco_contagem['V3'], "CONFIRMADOS_OK": banco_para_ftp_encontrados['V3']},
                {"CATEGORIA": "V1", "QTD_METADADOS": banco_contagem['V1'], "CONFIRMADOS_OK": banco_para_ftp_encontrados['V1']},
                {"CATEGORIA": "V2", "QTD_METADADOS": banco_contagem['V2'], "CONFIRMADOS_OK": banco_para_ftp_encontrados['V2']}
            ])

            # Métricas no topo
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Mapeados", sum(banco_contagem.values()))
            c2.metric("Confirmados", sum(banco_para_ftp_encontrados.values()))
            c3.metric("Pendências", len(arquivos_faltantes_no_ftp))
            c4.metric("Órfãos", len(arquivos_orfaos_no_banco))

            # Abas
            aba1, aba2, aba3 = st.tabs(["📊 Visão Geral", "📁 Arquivos Pendentes", "⚠️ Orfãos"])

            with aba1:
                st.dataframe(df_batimento, use_container_width=True)

            with aba2:
                if arquivos_faltantes_no_ftp:
                    st.dataframe(pd.DataFrame(arquivos_faltantes_no_ftp), use_container_width=True)
                else:
                    st.success("Tudo sincronizado!")
            
            with aba3:
                st.write("Conteúdo de órfãos original...")

        except Exception as e:
            st.error(f"Erro ao processar: {e}")
    cursor.close()

