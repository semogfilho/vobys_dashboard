# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import os
import re
from datetime import datetime  # <--- IMPORT NECESSÁRIO PARA FORMATAR A DATA

def render(conn, ano_selecionado, mes_chave, meses_disponiveis):
    # --- CSS AVANÇADO PARA PADRONIZAÇÃO DO LAYOUT ---
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
            div[data-testid="stMetric"] {
                background-color: #f8f9fa;
                padding: 10px 15px !important;
                border-radius: 8px !important;
                border: 1px solid #e9ecef !important;
            }
        </style>
    """, unsafe_allow_html=True)

    titulo_limpo = "Auditoria de Integração - Batimento Bidirecional"
    st.title(f".. {titulo_limpo}")

    competencia_texto = f"{meses_disponiveis[mes_chave]}/{ano_selecionado}"
    st.markdown(f"**Validação cruzada (Base Lógica ⇄ Armazenamento Físico) dos layouts para {competencia_texto}.**")
    st.markdown("---")

    cursor = conn.cursor()

    sql_estrategico = f"""
        SELECT
            ID_SIAFE_EVENTO_INTEGRACAO,
            e.SIGLA,
            TRIM(ind_tipo_requisicao) AS TIPO,
            TRIM(codigo_sefaz) AS SEFAZ,
            SUBSTR(TRIM(tipo_folha_sefaz), 2, 1) AS TIPO_FOLHA,
            TRIM(tipo_arquivo) AS TIPO_ARQ,
            TRIM(codigo_relatorio) AS RELATORIO
        FROM sw_publico.SIAFE_EVENTO_INTEGRACAO si
        join sw_publico.empresa e on si.id_empresa=e.id_empresa
        WHERE ano = {ano_selecionado} AND mes = {int(mes_chave)}
    """

    with st.spinner("Realizando batimento bidirecional..."):
        try:
            cursor.execute(sql_estrategico)
            rows = cursor.fetchall()

            # --- 1. PROCESSAMENTO: BANCO -> FÍSICO ---
            banco_contagem = {'V1': 0, 'V2': 0, 'V3': 0, 'V4': 0}
            banco_para_ftp_encontrados = {'V1': 0, 'V2': 0, 'V3': 0, 'V4': 0}

            set_arquivos_banco = set()
            arquivos_faltantes_no_ftp = []

            for id_reg, id_sigla, tipo, sefaz, tipo_folha, tipo_arq, relatorio in rows:
                if not tipo:
                    continue
                tipo_limpo = str(tipo).strip().upper()

                if tipo_limpo in banco_contagem:
                    banco_contagem[tipo_limpo] += 1

                    if tipo_limpo == 'V1':
                        pasta, prefixo = '/home/vobys/ftp/data/SIAPE-COLABORADORES/', 'FP_COL_'
                    elif tipo_limpo == 'V2':
                        pasta, prefixo = '/home/vobys/ftp/data/SIAPE-CREDITOS/', 'FP_CRE_'
                    else:
                        pasta, prefixo = '/home/vobys/ftp/data/SIAPE-FOLHAS/', 'FP_'

                    nome_base = f"{tipo_folha}_{ano_selecionado}{int(mes_chave):02d}_{tipo_arq}_{relatorio}.csv"

                    caminho_principal = os.path.join(pasta, f"{prefixo}{sefaz}_{nome_base}")
                    sefaz_lpad = str(sefaz).zfill(3)
                    caminho_alternativo = os.path.join(pasta, f"{prefixo}{sefaz_lpad}_{nome_base}")

                    nome_arq_principal = f"{prefixo}{sefaz}_{nome_base}"
                    nome_arq_alternativo = f"{prefixo}{sefaz_lpad}_{nome_base}"

                    if os.path.exists(caminho_principal):
                        banco_para_ftp_encontrados[tipo_limpo] += 1
                        set_arquivos_banco.add(nome_arq_principal)
                    elif os.path.exists(caminho_alternativo):
                        banco_para_ftp_encontrados[tipo_limpo] += 1
                        set_arquivos_banco.add(nome_arq_alternativo)
                    else:
                        categoria_desc = "SIAPE-COLABORADORES (V1)" if tipo_limpo == 'V1' else ("SIAPE-CREDITOS (V2)" if tipo_limpo == 'V2' else ("SIAPE-FOLHA_ORCAMENTARIO (V3)" if tipo_limpo == 'V3' else "SIAPE_FOLHA_PATRONAL (V4)"))
                        arquivos_faltantes_no_ftp.append({
                            "ID_SIAPE": id_reg,
                            "SIGLA": id_sigla,
                            "CATEGORIA": categoria_desc,
                            "ARQUIVO_ESPERADO": nome_arq_alternativo,
                            "STATUS": "Pendente de Geração Física"
                        })

            # --- 2. PROCESSAMENTO REVERSO: FÍSICO -> BANCO ---
            pastas_alvo = [
                ('/home/vobys/ftp/data/SIAPE-COLABORADORES/', 'V1'),
                ('/home/vobys/ftp/data/SIAPE-CREDITOS/', 'V2'),
                ('/home/vobys/ftp/data/SIAPE-FOLHAS/', 'V3_V4')
            ]

            total_arquivos_fisicos_pasta = {'V1': 0, 'V2': 0, 'V3': 0, 'V4': 0}
            arquivos_orfaos_no_banco = []
            competencia_busca = f"{ano_selecionado}{int(mes_chave):02d}"

            for pasta, tipo_escopo in pastas_alvo:
                if os.path.exists(pasta):
                    for arquivo in os.listdir(pasta):
                        if arquivo.endswith('.csv') and competencia_busca in arquivo:

                            if tipo_escopo == 'V1':
                                total_arquivos_fisicos_pasta['V1'] += 1
                            elif tipo_escopo == 'V2':
                                total_arquivos_fisicos_pasta['V2'] += 1
                            elif tipo_escopo == 'V3_V4':
                                if re.search(r'_[89]_', arquivo):
                                    total_arquivos_fisicos_pasta['V4'] += 1
                                else:
                                    total_arquivos_fisicos_pasta['V3'] += 1

                            if arquivo not in set_arquivos_banco:
                                if 'FP_COL_' in arquivo:
                                    nome_categoria = "SIAPE-COLABORADORES (V1)"
                                    caminho_completo = os.path.join('/home/vobys/ftp/data/SIAPE-COLABORADORES/', arquivo)
                                elif 'FP_CRE_' in arquivo:
                                    nome_categoria = "SIAPE-CREDITOS (V2)"
                                    caminho_completo = os.path.join('/home/vobys/ftp/data/SIAPE-CREDITOS/', arquivo)
                                else:
                                    if re.search(r'_[89]_', arquivo):
                                        nome_categoria = "SIAPE_FOLHA_PATRONAL (V4)"
                                    else:
                                        nome_categoria = "SIAPE-FOLHA_ORCAMENTARIO (V3)"
                                    caminho_completo = os.path.join('/home/vobys/ftp/data/SIAPE-FOLHAS/', arquivo)

                                # Captura a data de modificação do arquivo físico
                                timestamp_modificacao = os.path.getmtime(caminho_completo)
                                data_arquivo_str = datetime.fromtimestamp(timestamp_modificacao).strftime('%d/%m/%Y %H:%M:%S')

                                arquivos_orfaos_no_banco.append({
                                    "CATEGORIA": nome_categoria,
                                    "ARQUIVO_ENCONTRADO": arquivo,
                                    "DATA_MODIFICACAO": data_arquivo_str,  # <--- NOVA COLUNA ADICIONADA
                                    "CAMINHO_COMPLETO": caminho_completo,
                                    "STATUS": "Não Mapeado nos Metadados"
                                })

            # --- 3. MONTAGEM E ESTILIZAÇÃO DO PAINEL ---
            batimento_dados = [
                {"CATEGORIA": "SIAPE_FOLHA_PATRONAL (V4)", "QTD_METADADOS": banco_contagem['V4'], "CONFIRMADOS_OK": banco_para_ftp_encontrados['V4'], "QTD_STORAGE_REAL": total_arquivos_fisicos_pasta['V4']},
                {"CATEGORIA": "SIAPE-FOLHA_ORCAMENTARIO (V3)", "QTD_METADADOS": banco_contagem['V3'], "CONFIRMADOS_OK": banco_para_ftp_encontrados['V3'], "QTD_STORAGE_REAL": total_arquivos_fisicos_pasta['V3']},
                {"CATEGORIA": "SIAPE-COLABORADORES (V1)", "QTD_METADADOS": banco_contagem['V1'], "CONFIRMADOS_OK": banco_para_ftp_encontrados['V1'], "QTD_STORAGE_REAL": total_arquivos_fisicos_pasta['V1']},
                {"CATEGORIA": "SIAPE-CREDITOS (V2)", "QTD_METADADOS": banco_contagem['V2'], "CONFIRMADOS_OK": banco_para_ftp_encontrados['V2'], "QTD_STORAGE_REAL": total_arquivos_fisicos_pasta['V2']}
            ]

            df_batimento = pd.DataFrame(batimento_dados)

            total_banco_geral = sum(banco_contagem.values())
            total_arquivos_confirmados = sum(banco_para_ftp_encontrados.values())
            total_orfaos = len(arquivos_orfaos_no_banco)
            total_faltantes = len(arquivos_faltantes_no_ftp)

            # --- CARDS DE PERFORMANCE ---
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric(label="Mapeados (Metadados)", value=f"{total_banco_geral}")
            with c2:
                st.metric(label="Confirmados no Storage", value=f"{total_arquivos_confirmados}", delta=f"{total_arquivos_confirmados} integrados")
            with c3:
                st.metric(
                    label="Pendências de Arquivo",
                    value=f"{total_faltantes}",
                    delta=f"{total_faltantes} ausentes" if total_faltantes > 0 else "OK",
                    delta_color="inverse" if total_faltantes > 0 else "normal"
                )
            with c4:
                st.metric(
                    label="Arquivos não Mapeados",
                    value=f"{total_orfaos}",
                    delta=f"{total_orfaos} órfãos" if total_orfaos > 0 else "Limpo",
                    delta_color="inverse" if total_orfaos > 0 else "normal"
                )

            st.markdown("<br>", unsafe_allow_html=True)

            # --- ABAS DE ANÁLISE CORPORATIVA ---
            aba1, aba2, aba3 = st.tabs(["📊 Visão Geral do Batimento", "📁 Arquivos Pendentes no Storage", "⚠️ Arquivos Sem Vínculo de Integração"])

            with aba1:
                st.markdown("### Resumo Estatístico de Coerência")

                def aplicar_cores_resumo(row):
                    banco = row['QTD_METADADOS']
                    ok = row['CONFIRMADOS_OK']
                    fisico = row['QTD_STORAGE_REAL']
                    if ok < banco:
                        return ['background-color: #fff5f5; color: #c92a2a; font-weight: bold;'] * len(row)
                    elif fisico > ok:
                        return ['background-color: #fff9db; color: #f59f00; font-weight: normal;'] * len(row)
                    else:
                        return ['background-color: #f4fbf7; color: #2b8a3e; font-weight: normal;'] * len(row)

                df_estilizado = df_batimento.style.apply(aplicar_cores_resumo, axis=1)

                st.dataframe(
                    df_estilizado,
                    width='stretch',
                    hide_index=True,
                    column_config={
                        "CATEGORIA": st.column_config.TextColumn("LAYOUT ANALISADO"),
                        "QTD_METADADOS": st.column_config.NumberColumn("QTD REGISTRADA NOS METADADOS", format="%d"),
                        "CONFIRMADOS_OK": st.column_config.NumberColumn("CONFIRMADOS NO STORAGE", format="%d"),
                        "QTD_STORAGE_REAL": st.column_config.NumberColumn("TOTAL DE ARQUIVOS NA PASTA", format="%d")
                    }
                )

                st.markdown("""
                <div style='display: flex; gap: 15px; font-size: 12px; margin-top: 5px; color: #666;'>
                    <span>🟢 <span style='color:#2b8a3e; font-weight:bold;'>Verde</span>: Sincronia Integral</span>
                    <span>🟡 <span style='color:#f59f00; font-weight:bold;'>Amarelo</span>: Arquivos sobressalentes na pasta</span>
                    <span>🔴 <span style='color:#c92a2a; font-weight:bold;'>Vermelho</span>: Registros pendentes de arquivo físico</span>
                </div>
                """, unsafe_allow_html=True)

                if total_faltantes == 0 and total_orfaos == 0:
                    st.success("🎉 **Auditoria Concluída:** Sincronia de 100% atingida entre o mapeamento lógico e os diretórios do Storage.")

            with aba2:
                st.markdown("### 🔍 Protocolos de Integração aguardando a chegada do arquivo correspondente")
                if arquivos_faltantes_no_ftp:
                    df_falta = pd.DataFrame(arquivos_faltantes_no_ftp)
                    st.dataframe(
                        df_falta,
                        width='stretch',
                        hide_index=True,
                        column_config={
                            "CATEGORIA": st.column_config.TextColumn("LAYOUT ALVO"),
                            "ARQUIVO_ESPERADO": st.column_config.TextColumn("NOME DO ARQUIVO AUSENTE"),
                            "STATUS": st.column_config.TextColumn("STATUS DA AUDITORIA")
                        }
                    )
                else:
                    st.success("✅ Todos os registros lógicos possuem seus respectivos arquivos validados.")

            with aba3:
                st.markdown("### 🏴‍☠️ Arquivos físicos encontrados no Storage sem vínculo nos registros de integração")
                if arquivos_orfaos_no_banco:
                    df_orfaos = pd.DataFrame(arquivos_orfaos_no_banco)
                    # Ordena pelo nome do arquivo ou caminho completo
                    df_orfaos = df_orfaos.sort_values(by='CAMINHO_COMPLETO', ascending=True)

                    st.dataframe(
                        df_orfaos,
                        width='stretch',
                        hide_index=True,
                        column_config={
                            "CATEGORIA": st.column_config.TextColumn("DIRETÓRIO DA PASTA"),
                            "ARQUIVO_ENCONTRADO": st.column_config.TextColumn("NOME DO ARQUIVO FÍSICO"),
                            "DATA_MODIFICACAO": st.column_config.TextColumn("DATA DO ARQUIVO"),  # <--- CONFIGURAÇÃO DA NOVA COLUNA
                            "CAMINHO_COMPLETO": st.column_config.TextColumn("ENDEREÇO ABSOLUTO"),
                            "STATUS": st.column_config.TextColumn("STATUS DA AUDITORIA")
                        }
                    )
                else:
                    st.success("✅ Nenhum arquivo sobressalente. Estrutura do Storage totalmente limpa.")

        except Exception as e:
            st.error(f"Erro ao processar auditoria analítica: {e}")

    cursor.close()

