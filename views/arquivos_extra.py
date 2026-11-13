# -*- coding: utf-8 -*-
import json
import time
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import sys
import os

# Adiciona a raiz do projeto ao path para garantir a importação correta
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import auth_ui
from sefaz_client import requisitar_sefaz

# Importações dos módulos específicos de cada órgão (EMGERPI e Órgãos)
try:
    from queries import get_query_json_patronal_emgerpi
except ImportError:
    def get_query_json_patronal_emgerpi(ano, mes, codigo_externo=None):
        return "SELECT json_data FROM dual"

try:
    from utils_emgerpi import executar_query_emgerpi, processar_dados_emgerpi
except ImportError:
    executar_query_emgerpi = None
    processar_dados_emgerpi = None

try:
    from utils_orgaos import get_sql_seduc_extra, get_sql_funprev, get_sql_seduc_011, get_sql_seduc_914
except ImportError:
    get_sql_seduc_extra = None
    get_sql_funprev = None
    get_sql_seduc_011 = None
    get_sql_seduc_914 = None


# --- FUNÇÕES AUXILIARES DE BANCO E CONVERSÃO GERAL ---

def executar_query(conn, query, params):
    cursor = conn.cursor()
    params_clean = {}
    for k, v in params.items():
        if k in ['mes', 'ano']:
            try:
                params_clean[k] = int(v)
            except (ValueError, TypeError):
                params_clean[k] = v
        else:
            params_clean[k] = v

    try:
        cursor.execute(query, params_clean)
    except Exception as e:
        if "DPY-4008" in str(e) or "bind placeholder" in str(e):
            try:
                query_formatada = query
                for k, v in params_clean.items():
                    query_formatada = query_formatada.replace(f":{k}", str(v))
                cursor.execute(query_formatada)
            except Exception as ex:
                cursor.close()
                raise ex
        else:
            cursor.close()
            raise e

    columns = [col[0] for col in cursor.description] if cursor.description else []
    data = cursor.fetchall() if cursor.description else []
    cursor.close()
    return pd.DataFrame(data, columns=columns)


def executar_query_emgerpi_fallback(conn, ano, mes, codigo_externo="001"):
    sql_json = get_query_json_patronal_emgerpi(ano, mes, codigo_externo)
    try:
        cursor = conn.cursor()
        cursor.execute(sql_json)
        rows = cursor.fetchall()
        cursor.close()
        if rows:
            resultados = []
            for i, row in enumerate(rows):
                val_id = row[0] if len(row) > 1 else f"Linha_{i}"
                val_json = row[-1] if len(row) > 1 else row[0]
                if val_json is not None:
                    resultados.append({
                        "id_origem": str(val_id),
                        "status_vobys": str(row[1]) if len(row) > 2 else "N/D",
                        "json_content": val_json
                    })
            return resultados
    except Exception as e:
        st.error(f"Erro no fallback EMGERPI: {str(e)}")
    return None


def buscar_lista_numeros_suplementares(conn, ano, mes):
    if conn is None:
        return []

    encontrados = set()
    queries_busca = [
        """
        SELECT DISTINCT TO_NUMBER(REGEXP_SUBSTR(FO.TIPO_ARQUIVO, '^\d+$')) AS SUP
        FROM SW_SEDUC.FOLHA FO
        WHERE FO.ANO = :ano AND FO.MES = :mes AND FO.ID_TIPO_FOLHA NOT IN (1000000) AND FO.TIPO_ARQUIVO IS NOT NULL AND FO.TIPO_ARQUIVO <> '001'
        """,
        """
        SELECT DISTINCT TO_NUMBER(REGEXP_SUBSTR(FO.TIPO_ARQUIVO, '^\d+$')) AS SUP
        FROM SW_FUNPREV.FOLHA FO
        WHERE FO.ANO = :ano AND FO.MES = :mes AND FO.ID_TIPO_FOLHA NOT IN (1000000) AND FO.TIPO_ARQUIVO IS NOT NULL AND FO.TIPO_ARQUIVO <> '001'
        """,
        """
        SELECT DISTINCT TO_NUMBER(REGEXP_SUBSTR(FO.TIPO_ARQUIVO, '^\d+$')) AS SUP
        FROM SW_EMGERPI.FOLHA FO
        WHERE FO.ANO = :ano AND FO.MES = :mes AND FO.ID_TIPO_FOLHA NOT IN (1000000) AND FO.TIPO_ARQUIVO IS NOT NULL AND FO.TIPO_ARQUIVO <> '001'
        """
    ]

    for q in queries_busca:
        try:
            df_res = executar_query(conn, q, {"ano": ano, "mes": mes})
            if not df_res.empty:
                for val in df_res.iloc[:, 0].dropna():
                    try:
                        num = int(val)
                        if num >= 2:
                            encontrados.add(num)
                    except Exception:
                        continue
        except Exception:
            continue

    try:
        sql_json_base = get_query_json_patronal_emgerpi(ano, mes)
        if "AND" in sql_json_base.upper() and "CODIGO_EXTERNO" in sql_json_base.upper():
            import re
            sql_json_base = re.sub(r"AND\s+.*CODIGO_EXTERNO.*?(?=AND|ORDER|GROUP|$)", "", sql_json_base, flags=re.IGNORECASE)

        df_emgerpi = executar_query(conn, sql_json_base, {"ano": ano, "mes": mes})
        if not df_emgerpi.empty:
            for col in df_emgerpi.columns:
                for val in df_emgerpi[col].dropna():
                    val_str = str(val)
                    if "codigoExterno" in val_str:
                        import re
                        matches = re.findall(r'"codigoExterno"\s*:\s*"([^"]+)"', val_str)
                        for ext_code in matches:
                            if ext_code.isdigit():
                                num = int(ext_code)
                                if num >= 2:
                                    encontrados.add(num)
    except Exception:
        pass

    lista_nums = sorted(list(encontrados))
    return [f"{n:03d}" for n in lista_nums]


def construir_payload_json(df, mes, ano, cod_unidade, cod_relatorio, codigo_externo="001"):
    if df is None or df.empty:
        return None

    pagamentos = []
    for _, row in df.iterrows():
        valor_desc = row.get('DESCONTOS', 0.0)
        if isinstance(valor_desc, str):
            valor_desc = float(valor_desc.replace(',', '.'))
        else:
            valor_desc = float(valor_desc)

        valor_vant = row.get('VANTAGENS', 0.0)
        if isinstance(valor_vant, str):
            valor_vant = float(valor_vant.replace(',', '.'))
        else:
            valor_vant = float(valor_vant)

        pagamentos.append({
            "codigoSefaz": str(row.get('RUBRICA', '')),
            "regimePrevidenciario": str(row.get('TIPO_REGIME', '')),
            "codigoRubrica": str(row.get('RUBRICA', '')),
            "tipoVinculo": str(row.get('TIPO_VINCULO', '')),
            "valor": float(valor_vant),
            "valorDesconto": round(valor_desc, 2)
        })

    id_tipo_folha = 8 if str(cod_unidade) == "120" else 9

    payload = {
        "codigoUnidadeSistemaExterno": str(cod_unidade),
        "mes": int(mes),
        "idTipoFolha": id_tipo_folha,
        "codigoExterno": str(codigo_externo),
        "codigoRelatorioFolhaPagamento": str(cod_relatorio),
        "competencia": f"{int(mes):02d}/{ano}",
        "pagamentos": pagamentos
    }

    return payload


def converter_para_csv(df):
    return df.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')


def transmitir_para_sefaz(payload_dados, ano):
    try:
        if payload_dados is None:
            return False, None, "Erro: O payload de dados está vazio ou nulo."

        payload_obj = json.loads(payload_dados) if isinstance(payload_dados, str) else payload_dados
        endpoint = f"folha-pagamento/contabilizacao-folha-pagamento/{ano}"
        resultado = requisitar_sefaz("POST", endpoint, payload=payload_obj)

        if isinstance(resultado, dict) and resultado.get("erro"):
            err_msg = resultado.get("mensagem", "Erro desconhecido na API")
            if "HTTP 401" in err_msg or "HTTP 403" in err_msg:
                st.session_state["sefaz_auth"] = False
                st.session_state.pop("sefaz_cpf", None)
                st.session_state.pop("sefaz_pass", None)
            return False, json.dumps(payload_obj, ensure_ascii=False), err_msg

        return True, json.dumps(payload_obj, ensure_ascii=False), resultado
    except Exception as e:
        return False, None, str(e)


def consultar_recibo_sefaz(ano, mes, cod_unidade, cod_relatorio, codigo_externo):
    try:
        tipo_folha_val = 8 if str(cod_unidade) == "120" else 9
        payload_consulta = {
            "mes": int(mes),
            "competencia": f"{int(mes):02d}/{ano}",
            "tipoFolha": tipo_folha_val,
            "codigoUGSistemaExterno": str(cod_unidade),
            "codigoExterno": str(codigo_externo),
            "codigoRelatorio": str(cod_relatorio)
        }
        endpoint = f"folha-pagamento/contabilizacao/{ano}"
        resultado = requisitar_sefaz("POST", endpoint, payload=payload_consulta)

        if isinstance(resultado, dict) and resultado.get("erro"):
            err_msg = resultado.get("mensagem", "Erro desconhecido na API")
            if "HTTP 401" in err_msg or "HTTP 403" in err_msg:
                st.session_state["sefaz_auth"] = False
                st.session_state.pop("sefaz_cpf", None)
                st.session_state.pop("sefaz_pass", None)
            return False, err_msg

        return True, resultado
    except Exception as e:
        return False, str(e)


# --- BLOCO MESTRE DE RENDERIZAÇÃO DE INTERFACE ---

def render_bloco_processamento(
    conn,
    titulo,
    id_chave,
    sql,
    mes,
    ano,
    cod_unidade=None,
    cod_relatorio=None,
    auth_ui=None,
    seletor_folha_global="Ordinária",
    numero_suplementar="002"
):
    if seletor_folha_global == "Suplementar":
        num_sup_limpo = str(numero_suplementar).strip()
        codigo_externo = num_sup_limpo.zfill(3) if num_sup_limpo.isdigit() and int(num_sup_limpo) >= 2 else "002"
        if callable(sql):
            sql = sql("suplementar", codigo_externo)
    else:
        codigo_externo = "001"
        if callable(sql):
            sql = sql("ordinaria", "001")

    if cod_unidade and cod_relatorio:
        tipo_folha_val = 8 if str(cod_unidade) == "120" else 9
        nome_arquivo_base = f"FP_{cod_unidade}_{tipo_folha_val}_{ano}{int(mes):02d}_{codigo_externo}_{cod_relatorio}"
    else:
        nome_arquivo_base = f"PATRONAL_{id_chave.upper()}_{ano}{int(mes):02d}_{codigo_externo}"

    st.subheader(f"{titulo} - {nome_arquivo_base}")
    
    data_key = f"df_extra_{id_chave}_{ano}_{mes}_{codigo_externo}"
    json_raw_key = f"json_raw_{id_chave}_{ano}_{mes}_{codigo_externo}"
    retorno_key = f"retorno_envio_{id_chave}_{ano}_{mes}_{codigo_externo}"
    flag_envio_key = f"executar_envio_{id_chave}_{ano}_{mes}_{codigo_externo}"
    flag_consulta_key = f"executar_consulta_{id_chave}_{ano}_{mes}_{codigo_externo}"

    col_gerar, col_json, col_csv, col_enviar, col_consultar = st.columns([1.2, 1.2, 1.2, 1.2, 1.2])

    if col_gerar.button(f"⚙️ Gerar Arquivo", key=f"btn_gerar_{id_chave}_{codigo_externo}"):
        try:
            with st.spinner(f"A gerar dados para {titulo}..."):
                if id_chave == "emgerpi":
                    if executar_query_emgerpi is not None and processar_dados_emgerpi is not None:
                        json_retorno = executar_query_emgerpi(conn, ano, mes, codigo_externo, executar_query)
                        json_str, df = processar_dados_emgerpi(json_retorno, codigo_externo)
                        st.session_state[json_raw_key] = json_str
                        st.session_state[data_key] = df
                    else:
                        json_retorno = executar_query_emgerpi_fallback(conn, ano, mes, codigo_externo)
                        if json_retorno and len(json_retorno) > 0:
                            conteudo = json_retorno[0].get("json_content")
                            dados_json_obj = json.loads(conteudo) if isinstance(conteudo, str) else conteudo
                            if isinstance(dados_json_obj, dict):
                                dados_json_obj["codigoExterno"] = str(codigo_externo)
                                st.session_state[json_raw_key] = json.dumps(dados_json_obj, ensure_ascii=False, indent=2)
                                pagamentos = dados_json_obj.get("pagamentos", [])
                                st.session_state[data_key] = pd.json_normalize(pagamentos)
                            else:
                                st.session_state[json_raw_key] = None
                                st.session_state[data_key] = pd.DataFrame()
                        else:
                            st.session_state[json_raw_key] = None
                            st.session_state[data_key] = pd.DataFrame()
                elif sql:
                    df = executar_query(conn, sql, {"mes": mes, "ano": ano})
                    st.session_state[data_key] = df
                    if not df.empty and cod_unidade and cod_relatorio:
                        payload_obj = construir_payload_json(df, mes, ano, cod_unidade, cod_relatorio, codigo_externo)
                        st.session_state[json_raw_key] = json.dumps(payload_obj, ensure_ascii=False, indent=2)

                # Feedback visual caso venha vazio
                df_verificacao = st.session_state.get(data_key)
                if df_verificacao is None or df_verificacao.empty:
                    st.warning(f"⚠️ Nenhum registro encontrado para gerar o arquivo de {titulo} ({ano}/{int(mes):02d} - Ext: {codigo_externo}).")

                st.session_state.pop(retorno_key, None)
                st.session_state.pop(flag_envio_key, None)
                st.session_state.pop(flag_consulta_key, None)
        except Exception as e:
            st.error(f"Erro ao consultar base de dados: {str(e)}")
            st.session_state[data_key] = None

    df_gerado = st.session_state.get(data_key)
    json_raw = st.session_state.get(json_raw_key)

    if col_consultar.button(f"🔍 Consultar Recibo", key=f"btn_consultar_{id_chave}_{codigo_externo}"):
        st.session_state[flag_consulta_key] = True
        st.rerun()

    if df_gerado is not None and not df_gerado.empty:
        if json_raw:
            col_json.download_button(
                label="📄 Baixar JSON",
                data=json_raw.encode('utf-8'),
                file_name=f"{nome_arquivo_base}.json",
                mime="application/json",
                key=f"btn_json_{id_chave}_{codigo_externo}"
            )

        col_csv.download_button(
            label="📊 Baixar CSV",
            data=converter_para_csv(df_gerado),
            file_name=f"{nome_arquivo_base}.csv",
            mime="text/csv",
            key=f"btn_csv_{id_chave}_{codigo_externo}"
        )

        if col_enviar.button(f"🚀 Enviar Arquivo", key=f"btn_enviar_{id_chave}_{codigo_externo}", type="primary"):
            if auth_ui and hasattr(auth_ui, "verificar_credenciais_sefaz") and not auth_ui.verificar_credenciais_sefaz():
                st.stop()
            elif not auth_ui and not st.session_state.get("sefaz_auth", False):
                st.warning("⚠️ Credenciais da SEFAZ não válidas. Autentique-se.")
                st.stop()

            st.session_state[flag_envio_key] = True
            st.rerun()

        if st.session_state.get(flag_envio_key):
            payload_para_envio = json_raw if json_raw else df_gerado
            with st.spinner("A transmitir lote para a SEFAZ..."):
                sucesso, json_str, retorno = transmitir_para_sefaz(payload_para_envio, ano)
                st.session_state[flag_envio_key] = False
                st.session_state[retorno_key] = retorno
                if sucesso:
                    st.success("Transmissão efetuada com sucesso!")
                    st.rerun()
                else:
                    st.error(f"Erro na transmissão: {retorno}")

    if st.session_state.get(flag_consulta_key):
        with st.spinner("A consultar recibo na SEFAZ..."):
            sucesso, retorno = consultar_recibo_sefaz(ano, mes, cod_unidade, cod_relatorio, codigo_externo)
            st.session_state[flag_consulta_key] = False
            st.session_state[retorno_key] = retorno  
            if sucesso:
                st.success("Consulta realizada com sucesso!")
                st.rerun()
            else:
                st.error(f"Erro na consulta: {retorno}")

    resp_sefaz = st.session_state.get(retorno_key)
    if resp_sefaz is not None:
        dados_recibo = resp_sefaz[0] if isinstance(resp_sefaz, list) and len(resp_sefaz) > 0 else resp_sefaz

        st.markdown("""
        <style>
            .receipt-box {
                background: linear-gradient(135deg, rgba(40, 167, 69, 0.08) 0%, rgba(23, 162, 184, 0.08) 100%);
                border: 1px solid rgba(40, 167, 69, 0.3);
                border-radius: 8px;
                padding: 14px 18px;
                margin-top: 12px;
                margin-bottom: 12px;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            }
            .receipt-header {
                font-size: 13px;
                font-weight: 700;
                color: #28a745;
                margin-bottom: 8px;
                display: flex;
                align-items: center;
                gap: 6px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            .receipt-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                gap: 12px;
            }
            .receipt-item label {
                font-size: 11px;
                color: #666;
                font-weight: 500;
                display: block;
                text-transform: uppercase;
            }
            .receipt-item value {
                font-size: 14px;
                font-weight: 700;
                color: #31333F;
            }
        </style>
        """, unsafe_allow_html=True)

        if isinstance(dados_recibo, dict):
            codigo_recibo = dados_recibo.get("codigo") or dados_recibo.get("numeroRecibo") or dados_recibo.get("id") or "N/D"
            competencia_rec = dados_recibo.get("competencia") or dados_recibo.get("mesAno") or "-"
            status_obs = dados_recibo.get("status") or dados_recibo.get("situacao") or "Sucesso"
            val_bruto = dados_recibo.get("valorTotalBruto") or dados_recibo.get("valor") or 0.0
            val_liquido = dados_recibo.get("valorTotalLiquido") or 0.0
            
            try:
                val_bruto = float(val_bruto)
                val_liquido = float(val_liquido)
            except (ValueError, TypeError):
                val_bruto = 0.0
                val_liquido = 0.0

            st.markdown(f"""
            <div class="receipt-box">
                <div class="receipt-header">✅ Comprovante de Transmissão / Recibo SIAFE</div>
                <div class="receipt-grid">
                    <div class="receipt-item">
                        <label>Nº do Recibo / Código</label>
                        <value>{codigo_recibo}</value>
                    </div>
                    <div class="receipt-item">
                        <label>Competência</label>
                        <value>{competencia_rec}</value>
                    </div>
                    <div class="receipt-item">
                        <label>Status</label>
                        <value>{status_obs}</value>
                    </div>
                    <div class="receipt-item">
                        <label>Valor Bruto</label>
                        <value>R$ {val_bruto:,.2f}</value>
                    </div>
                    <div class="receipt-item">
                        <label>Valor Líquido</label>
                        <value>R$ {val_liquido:,.2f}</value>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
                
        elif isinstance(resp_sefaz, list) and len(resp_sefaz) == 0:
            st.warning("⚠️ A consulta retornou uma lista vazia. Nenhum registo encontrado para os parâmetros informados.")
        else:
            st.info(f"Retorno SEFAZ: {resp_sefaz}")

    if df_gerado is not None and not df_gerado.empty:
        with st.expander("🔍 Visualizar Prévia dos Dados", expanded=False):
            df_exibicao = df_gerado.copy()
            
            # Transforma idSiafeEvento em link HTML se o status não for VALIDADO
            if 'idSiafeEvento' in df_exibicao.columns and 'status' in df_exibicao.columns:
                def formatar_id_link(row):
                    ev_id = str(row['idSiafeEvento'])
                    st_val = str(row['status']).strip().upper()
                    if st_val != 'VALIDADO':
                        url = f"https://siape.sead.pi.gov.br/adm/sead/gerencial/gerencial/integracao-sistema-financeiro-siafe/informacoes-a-transmitir/evento-transmissao/{ev_id}"
                        return f'<a href="{url}" target="_blank" style="color: #0066cc; text-decoration: underline; font-weight: 600;">{ev_id}</a>'
                    return ev_id

                df_exibicao['idSiafeEvento'] = df_exibicao.apply(formatar_id_link, axis=1)

            cols_valores = ['VANTAGENS', 'DESCONTOS', 'valor', 'valorDesconto']
            for col in cols_valores:
                if col in df_exibicao.columns:
                    if pd.api.types.is_numeric_dtype(df_exibicao[col]):
                        df_exibicao[col] = pd.to_numeric(df_exibicao[col], errors='coerce').fillna(0.0)
                    else:
                        def converter_para_float(val):
                            if pd.isna(val):
                                return 0.0
                            val_str = str(val).strip().replace('R$', '').strip()
                            if not val_str:
                                return 0.0
                            if ',' in val_str and '.' in val_str:
                                val_str = val_str.replace('.', '').replace(',', '.')
                            elif ',' in val_str:
                                val_str = val_str.replace(',', '.')
                            try:
                                return float(val_str)
                            except ValueError:
                                return 0.0

                        df_exibicao[col] = df_exibicao[col].apply(converter_para_float)

            col_v = 'valor' if 'valor' in df_exibicao.columns else ('VANTAGENS' if 'VANTAGENS' in df_exibicao.columns else None)
            col_d = 'valorDesconto' if 'valorDesconto' in df_exibicao.columns else ('DESCONTOS' if 'DESCONTOS' in df_exibicao.columns else None)
            
            tot_v = df_exibicao[col_v].sum() if col_v else 0.0
            tot_d = df_exibicao[col_d].sum() if col_d else 0.0

            str_tot_v = f"R$ {tot_v:,.2f}".replace(',', 'v').replace('.', ',').replace('v', '.')
            str_tot_d = f"R$ {tot_d:,.2f}".replace(',', 'v').replace('.', ',').replace('v', '.')

            df_tabela_formatada = df_exibicao.copy()
            for col in cols_valores:
                if col in df_tabela_formatada.columns:
                    df_tabela_formatada[col] = df_tabela_formatada[col].apply(
                        lambda x: f"R$ {x:,.2f}".replace(',', 'v').replace('.', ',').replace('v', '.') if isinstance(x, (int, float)) else x
                    )

            html_tabela = df_tabela_formatada.to_html(index=True, classes="custom-preview-table", escape=False)
            
            html_completo = f"""
            <style>
                .preview-container {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                    border: 1px solid rgba(150, 150, 150, 0.2);
                    border-radius: 8px;
                    overflow: hidden;
                    background-color: transparent;
                    margin-bottom: 10px;
                }}
                .table-scroll {{
                    overflow-x: auto;
                }}
                .custom-preview-table {{
                    width: 100%;
                    border-collapse: collapse;
                    font-size: 13px;
                    color: #31333F;
                    margin: 0;
                }}
                .custom-preview-table th, .custom-preview-table td {{
                    padding: 8px 12px;
                    border-bottom: 1px solid rgba(150, 150, 150, 0.15);
                    text-align: left;
                }}
                .custom-preview-table th {{
                    font-weight: 600;
                    background-color: rgba(150, 150, 150, 0.08);
                    border-top: none;
                }}
                .custom-preview-table th:first-child {{
                    border-top-left-radius: 8px;
                }}
                .custom-preview-table th:last-child {{
                    border-top-right-radius: 8px;
                }}
                .custom-preview-table th:nth-last-child(-n+2), 
                .custom-preview-table td:nth-last-child(-n+2) {{
                    text-align: right !important;
                }}
                .totals-footer {{
                    display: flex;
                    justify-content: flex-end;
                    gap: 30px;
                    padding: 12px 20px;
                    background-color: rgba(150, 150, 150, 0.04);
                    border-top: 1px solid rgba(150, 150, 150, 0.2);
                }}
                .total-item {{
                    text-align: right;
                }}
                .total-label {{
                    font-size: 11px;
                    color: #666;
                    font-weight: 500;
                    margin-bottom: 2px;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }}
                .total-value {{
                    font-size: 17px;
                    font-weight: 700;
                    color: #31333F;
                }}
            </style>
            <div class="preview-container">
                <div class="table-scroll">
                    {html_tabela}
                </div>
                <div class="totals-footer">
                    <div class="total-item">
                        <div class="total-label">Total Valor/Vantagens</div>
                        <div class="total-value">{str_tot_v}</div>
                    </div>
                    <div class="total-item">
                        <div class="total-label">Total Desconto</div>
                        <div class="total-value">{str_tot_d}</div>
                    </div>
                </div>
            </div>
            """
            
            altura_componente = min(max(180, (len(df_tabela_formatada) + 1) * 39 + 60), 450)
            components.html(html_completo, height=altura_componente, scrolling=True)


def render(conn, ano, mes, meses_lista=None):
    if meses_lista is None:
        meses_lista = {
            1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
            5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
            9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
        }

    st.title("📁 Gerador e Transmissor de Arquivos Extras")
    mes_nome = meses_lista.get(int(mes), str(mes))
    
    col_comp, col_painel = st.columns([1.2, 4])
    
    with col_comp:
        st.caption(f"**Competência:** {mes_nome}/{ano}")
        
    with col_painel:
        cache_key_sup = f"lista_sup_{ano}_{mes}"
        if cache_key_sup not in st.session_state:
            st.session_state[cache_key_sup] = buscar_lista_numeros_suplementares(conn, ano, mes)
        opcoes_sup = st.session_state[cache_key_sup]

        lista_opcoes = ["001"] + [str(s) for s in opcoes_sup] if opcoes_sup else ["001"]

        state_selecao_key = f"tipo_ou_sup_selecionado_{ano}_{mes}"
        if state_selecao_key not in st.session_state:
            st.session_state[state_selecao_key] = "001"

        current_val = st.session_state[state_selecao_key]
        if current_val not in lista_opcoes:
            current_val = "001"
            st.session_state[state_selecao_key] = "001"

        idx_atual = lista_opcoes.index(current_val)

        st.markdown("""
        <div style="display: flex; border: 1px solid rgba(150, 150, 150, 0.25); border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px; background-color: #f8f9fa; font-size: 11px; font-weight: 700; color: #555; text-transform: uppercase;">
            <div style="width: 90px; padding: 7px 10px; text-align: center; border-right: 1px solid rgba(150, 150, 150, 0.2);">Ordinária</div>
            <div style="flex-grow: 1; padding: 7px 10px; text-align: center;">Suplementar</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div style="border: 1px solid rgba(150, 150, 150, 0.25); border-bottom-left-radius: 6px; border-bottom-right-radius: 6px; padding: 6px 12px; background: #ffffff; margin-bottom: 12px;">', unsafe_allow_html=True)
        sel_unico = st.radio(
            "Seleção de Tipo de Folha",
            options=lista_opcoes,
            index=idx_atual,
            horizontal=True,
            label_visibility="collapsed",
            key=f"radio_unico_geral_{ano}_{mes}"
        )
        st.markdown('</div>', unsafe_allow_html=True)

        if sel_unico:
            st.session_state[state_selecao_key] = sel_unico

        if st.session_state[state_selecao_key] == "001":
            tipo_folha_global = "Ordinária"
            numero_suplementar = "001"
        else:
            tipo_folha_global = "Suplementar"
            numero_suplementar = st.session_state[state_selecao_key]

    render_bloco_processamento(conn, "1. PATRONAL EMGERPI", "emgerpi", None, mes, ano, "120", "93", auth_ui, tipo_folha_global, numero_suplementar)
    st.divider()

    render_bloco_processamento(conn, "2. PATRONAL EXTRA SEDUC", "seduc_extra", get_sql_seduc_extra, mes, ano, "011", "99", auth_ui, tipo_folha_global, numero_suplementar)
    st.divider()

    render_bloco_processamento(conn, "3. PATRONAL FUNPREV", "funprev", get_sql_funprev, mes, ano, "924", "90", auth_ui, tipo_folha_global, numero_suplementar)
    st.divider()

    render_bloco_processamento(conn, "4. PATRONAL SEDUC 011", "seduc_011", get_sql_seduc_011, mes, ano, "011", "90", auth_ui, tipo_folha_global, numero_suplementar)
    st.divider()

    render_bloco_processamento(conn, "5. PATRONAL SEDUC 914", "seduc_914", get_sql_seduc_914, mes, ano, "914", "90", auth_ui, tipo_folha_global, numero_suplementar)

