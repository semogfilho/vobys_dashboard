# -*- coding: utf-8 -*-
import json
import time
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import sys
import os

# Adiciona a raiz do projeto ao path para garantir a importação correta do sefaz_client
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Importações necessárias para o auth_ui e cliente SEFAZ
import auth_ui
from sefaz_client import requisitar_sefaz

# Importação das funções específicas do EMGERPI
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


# --- FUNÇÕES AUXILIARES DE CONVERSÃO E BANCO ---

def buscar_lista_numeros_suplementares(conn, ano, mes):
    if conn is None:
        return []

    queries_busca = [
        """
        SELECT DISTINCT TO_NUMBER(REGEXP_SUBSTR(FO.TIPO_ARQUIVO, '^\d+$')) AS SUP
        FROM SW_SEDUC.FOLHA FO
        WHERE FO.ANO = :ano
          AND FO.MES = :mes
          AND FO.ID_TIPO_FOLHA NOT IN (1000000)
          AND FO.TIPO_ARQUIVO IS NOT NULL
          AND FO.TIPO_ARQUIVO <> '001'
        """,
        """
        SELECT DISTINCT TO_NUMBER(REGEXP_SUBSTR(FO.TIPO_ARQUIVO, '^\d+$')) AS SUP
        FROM SW_FUNPREV.FOLHA FO
        WHERE FO.ANO = :ano
          AND FO.MES = :mes
          AND FO.ID_TIPO_FOLHA NOT IN (1000000)
          AND FO.TIPO_ARQUIVO IS NOT NULL
          AND FO.TIPO_ARQUIVO <> '001'
        """,
        """
        SELECT DISTINCT TO_NUMBER(REGEXP_SUBSTR(FO.TIPO_ARQUIVO, '^\d+$')) AS SUP
        FROM SW_EMGERPI.FOLHA FO
        WHERE FO.ANO = :ano
          AND FO.MES = :mes
          AND FO.ID_TIPO_FOLHA NOT IN (1000000)
          AND FO.TIPO_ARQUIVO IS NOT NULL
          AND FO.TIPO_ARQUIVO <> '001'
        """
    ]

    encontrados = set()
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

    # Varredura completa em todos os JSONs de patronal da EMGERPI para o mês/ano
    try:
        sql_json_base = get_query_json_patronal_emgerpi(ano, mes)
        sql_busca_geral = sql_json_base
        if "AND" in sql_busca_geral.upper() and "CODIGO_EXTERNO" in sql_busca_geral.upper():
            import re
            sql_busca_geral = re.sub(r"AND\s+.*CODIGO_EXTERNO.*?(?=AND|ORDER|GROUP|$)", "", sql_busca_geral, flags=re.IGNORECASE)

        df_emgerpi = executar_query(conn, sql_busca_geral, {"ano": ano, "mes": mes})
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
    cursor = conn.cursor()
    cursor.execute(sql_json)
    rows = cursor.fetchall()
    cursor.close()
    if rows:
        resultados = []
        for i, row in enumerate(rows):
            val_id = row[0] if len(row) > 1 else f"Linha_{i}"
            val_json = row[1] if len(row) > 1 else row[0]
            if val_json is not None:
                resultados.append({
                    "id_origem": str(val_id),
                    "json_content": val_json
                })
        return resultados
    return None


# --- INTEGRAÇÃO COM A API SEFAZ-PI (VIA sefaz_client) ---

def transmitir_para_sefaz(payload_dados, ano):
    try:
        if payload_dados is None:
            return False, None, "Erro: O payload de dados está vazio ou nulo."

        if isinstance(payload_dados, str):
            try:
                payload_obj = json.loads(payload_dados)
            except json.JSONDecodeError as jde:
                return False, None, f"Erro ao converter string JSON: {str(jde)}"
        else:
            payload_obj = payload_dados

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


# --- BLOCO DE RENDERIZAÇÃO DA INTERFACE ---

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
        if num_sup_limpo.isdigit() and int(num_sup_limpo) >= 2:
            codigo_externo = num_sup_limpo.zfill(3)
        else:
            codigo_externo = "002" 
        if callable(sql):
            sql = sql("suplementar", codigo_externo)
    else:
        codigo_externo = "001"
        if callable(sql):
            sql = sql("ordinaria", "001")

    if cod_unidade and cod_relatorio:
        tipo_folha_val = 8 if str(cod_unidade) == "120" else 9
        nome_arquivo_base = f"FP_{cod_unidade}_{tipo_folha_val}_{ano}{int(mes):02d}_{codigo_externo}_{cod_relatorio}"
        titulo_exibicao = f"{titulo} - {nome_arquivo_base}"
    else:
        nome_arquivo_base = f"PATRONAL_{id_chave.upper()}_{ano}{int(mes):02d}_{codigo_externo}"
        titulo_exibicao = f"{titulo} - {nome_arquivo_base}"

    st.subheader(titulo_exibicao)
    
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
            if auth_ui and hasattr(auth_ui, "verificar_credenciais_sefaz"):
                if not auth_ui.verificar_credenciais_sefaz():
                    st.stop()
            else:
                if not st.session_state.get("sefaz_auth", False):
                    st.warning("⚠️ Credenciais da SEFAZ não válidas. Por favor, autentique-se.")
                    st.stop()

            st.session_state[flag_envio_key] = True
            st.rerun()

        if st.session_state.get(flag_envio_key):
            payload_para_envio = json_raw if json_raw else df_gerado
            if payload_para_envio is None:
                st.error("Nenhum dado válido para envio.")
                st.session_state[flag_envio_key] = False
            else:
                with st.spinner("A transmitir lote para a SEFAZ..."):
                    sucesso, json_str, retorno = transmitir_para_sefaz(payload_para_envio, ano)
                    st.session_state[flag_envio_key] = False
                    st.session_state[retorno_key] = retorno

                    if sucesso:
                        st.success("Transmissão efetuada com sucesso!")
                        st.rerun()
                    else:
                        if any(err in str(retorno) for err in ["401", "403", "Unauthorized"]):
                            st.session_state["sefaz_auth"] = False
                            st.session_state.pop("sefaz_cpf", None)
                            st.session_state.pop("sefaz_pass", None)
                            st.error("Sessão expirada ou credenciais inválidas. Por favor, autentique-se novamente.")
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
                        lambda x: f"R$ {x:,.2f}".replace(',', 'v').replace('.', ',').replace('v', '.')
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

        # Lista unificada combinando Ordinária '001' + opções suplementares disponíveis
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
        <style>
            .unified-table {
                border: 1px solid rgba(150, 150, 150, 0.25);
                border-radius: 8px;
                overflow: hidden;
                background: #ffffff;
                box-shadow: 0 1px 3px rgba(0,0,0,0.02);
                margin-top: 2px;
                margin-bottom: 10px;
            }
            .unified-header {
                display: grid;
                grid-template-columns: 1fr 3fr;
                background-color: #f8f9fa;
                border-bottom: 1px solid rgba(150, 150, 150, 0.2);
                font-size: 11px;
                font-weight: 700;
                color: #555;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                text-align: center;
            }
            .unified-th {
                padding: 7px 10px;
            }
            .unified-th:first-child {
                border-right: 1px solid rgba(150, 150, 150, 0.2);
            }
        </style>
        <div class="unified-table">
            <div class="unified-header">
                <div class="unified-th">Ordinária</div>
                <div class="unified-th">Suplementar</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Único st.radio unificado garantindo exclusão mútua nativa e fluida
        sel_unificado = st.radio(
            "Tipo de Folha",
            options=lista_opcoes,
            index=idx_atual,
            horizontal=True,
            label_visibility="collapsed",
            key=f"radio_unificado_{ano}_{mes}"
        )

        if sel_unificado:
            st.session_state[state_selecao_key] = sel_unificado

        # Define as variáveis globais finais com base na única seleção ativa
        if st.session_state[state_selecao_key] == "001":
            tipo_folha_global = "Ordinária"
            numero_suplementar = "001"
        else:
            tipo_folha_global = "Suplementar"
            numero_suplementar = st.session_state[state_selecao_key]

    render_bloco_processamento(
        conn=conn,
        titulo="1. PATRONAL EMGERPI",
        id_chave="emgerpi",
        sql=None,
        mes=mes,
        ano=ano,
        cod_unidade="120",
        cod_relatorio="93",
        auth_ui=auth_ui,
        seletor_folha_global=tipo_folha_global,
        numero_suplementar=numero_suplementar
    )

    st.divider()

    def get_sql_seduc_extra(tipo, cod_sup="002"):
        tipo_arquivo_val = cod_sup if tipo == "suplementar" else "001"
        condicao_tipo_folha = "S.ID_TIPO_FOLHA IN (1000000)" if tipo == "ordinaria" else "S.ID_TIPO_FOLHA NOT IN (1000000)"
        
        return f"""
        SELECT 
            CASE 
                WHEN S.COD_RUBRICA IN (714401, 714406) THEN '963' 
                WHEN S.COD_RUBRICA IN (714451, 714456) THEN '944' 
            END AS RUBRICA, 
            S.NOME_RUBRICA AS DESCRIMINACAO, 
            CASE 
                WHEN S.ID_REGIME IN (2, 9, 1000003) THEN 'RPPS' 
                ELSE 'RGPS' 
            END AS TIPO_REGIME, 
            CASE 
                WHEN S.ID_REGIME IN (9, 1000003) THEN 'MILITAR' 
                ELSE 'CIVIL' 
            END AS TIPO_VINCULO, 
            0 AS VANTAGENS, 
            REPLACE(TO_CHAR(SUM(S.VALOR_CALCULADO)), ',', '.') AS DESCONTOS 
        FROM ( 
            SELECT 
                'SEDUC' AS ORGAO, 
                FR.NOME_RUBRICA, 
                FR.TIPO, 
                FF.VALOR_CALCULADO, 
                FR.COD_RUBRICA, 
                FI.ID_REGIME, 
                FC.MES, 
                FC.ANO, 
                FO.ID_TIPO_FOLHA, 
                FO.TIPO_ARQUIVO, 
                FO.ID_FONTE 
            FROM SW_SEDUC.FOLHA_CONTRACHEQUE FC 
            JOIN SW_SEDUC.FOLHA FO ON FO.ID_FOLHA = FC.ID_FOLHA 
            JOIN SW_SEDUC.FUNCIONARIO_INGRESSO FI ON FI.ID_FUNCIONARIO = FC.ID_FUNCIONARIO 
            JOIN SW_SEDUC.FOLHA_FICHA_FINANCEIRA FF ON FF.ID_FOLHA_FUNCIONARIO = FC.ID_FOLHA_FUNCIONARIO 
            JOIN SW_PUBLICO.FOLHA_RUBRICA FR ON FR.ID_RUBRICA = FF.ID_RUBRICA 
        ) S 
        WHERE S.MES = :mes 
          AND S.ANO = :ano 
          AND {condicao_tipo_folha} 
          AND S.TIPO_ARQUIVO = '{tipo_arquivo_val}' 
          AND S.COD_RUBRICA IN (714401, 714406, 714451, 714456) 
          AND S.ID_FONTE IN (1000003, 1000020, 1000021, 1000040, 1000041, 1000060, 1, 2, 3) 
        GROUP BY S.ORGAO, S.COD_RUBRICA, S.NOME_RUBRICA, S.ID_REGIME 
        ORDER BY S.ORGAO, S.COD_RUBRICA, S.NOME_RUBRICA, S.ID_REGIME
        """

    render_bloco_processamento(
        conn=conn,
        titulo="2. PATRONAL EXTRA SEDUC",
        id_chave="seduc_extra",
        sql=get_sql_seduc_extra,
        mes=mes,
        ano=ano,
        cod_unidade="011",
        cod_relatorio="99",
        auth_ui=auth_ui,
        seletor_folha_global=tipo_folha_global,
        numero_suplementar=numero_suplementar
    )

    st.divider()

    def get_sql_funprev(tipo, cod_sup="002"):
        condicao_tipo_folha = "FO.ID_TIPO_FOLHA IN (1000000)" if tipo == "ordinaria" else "NOT FO.ID_TIPO_FOLHA IN (1000000)"
        condicao_tipo_arquivo = "" if tipo == "ordinaria" else f"AND (FO.TIPO_ARQUIVO = '{cod_sup}' OR FO.TIPO_ARQUIVO IS NULL)"
        
        return f"""
        SELECT 
            RUBRICA, 
            DESCRIMINACAO, 
            'RPPS' AS TIPO_REGIME, 
            CASE 
                WHEN S.ID_REGIME IN (9, 1000003) THEN 'MILITAR' 
                ELSE 'CIVIL' 
            END AS TIPO_VINCULO, 
            0 AS VANTAGENS, 
            REPLACE(TO_CHAR(SUM(S.VALOR_CALCULADO)), ',', '.') AS DESCONTOS 
        FROM ( 
            SELECT 
                CASE 
                    WHEN FR.COD_RUBRICA IN (714470, 714475, 714480) THEN SUM(FF.VALOR_CALCULADO * -1) 
                    ELSE SUM(FF.VALOR_CALCULADO) 
                END AS VALOR_CALCULADO, 
                FR.COD_RUBRICA, 
                CASE 
                    WHEN FO.TIPO_FOLHA_SEFAZ = 'C7' THEN '934' 
                    ELSE '924' 
                END AS RUBRICA, 
                CASE 
                    WHEN FO.TIPO_FOLHA_SEFAZ = 'C7' THEN 'PIAUIPREV - Patronal - Pensionista' 
                    ELSE 'PIAUIPREV - Patronal - Aposentado' 
                END AS DESCRIMINACAO, 
                FI.ID_REGIME 
            FROM SW_FUNPREV.FOLHA_CONTRACHEQUE FC 
            JOIN SW_FUNPREV.FOLHA FO ON FO.ID_FOLHA = FC.ID_FOLHA 
            JOIN SW_FUNPREV.FUNCIONARIO_INGRESSO FI ON FI.ID_FUNCIONARIO = FC.ID_FUNCIONARIO 
            JOIN SW_FUNPREV.FOLHA_FICHA_FINANCEIRA FF ON FF.ID_FOLHA_FUNCIONARIO = FC.ID_FOLHA_FUNCIONARIO 
            JOIN SW_PUBLICO.FOLHA_RUBRICA FR ON FR.ID_RUBRICA = FF.ID_RUBRICA 
            WHERE FO.MES = :mes 
              AND FO.ANO = :ano 
              AND {condicao_tipo_folha} 
              {condicao_tipo_arquivo}
              AND FC.ID_PENSIONISTA IS NULL 
              AND FC.ID_PENSIONISTA_PA IS NULL 
              AND FR.COD_RUBRICA IN (714400, 714403, 714405, 714410, 714436, 714450, 714460, 714455, 714420, 714452, 714470, 714475, 714480) 
            GROUP BY FO.TIPO_FOLHA_SEFAZ, FR.COD_RUBRICA, FI.ID_REGIME 
            
            UNION ALL 
            
            SELECT 
                CASE 
                    WHEN FR.COD_RUBRICA IN (714470, 714475, 714480) THEN SUM(FF.VALOR_CALCULADO * -1) 
                    ELSE SUM(FF.VALOR_CALCULADO) 
                END AS VALOR_CALCULADO, 
                FR.COD_RUBRICA, 
                '934' AS RUBRICA, 
                'PIAUIPREV - Patronal - Pensionista' AS DESCRIMINACAO, 
                FI.ID_REGIME 
            FROM SW_FUNPREV.FOLHA_CONTRACHEQUE FC 
            JOIN SW_FUNPREV.FOLHA FO ON FO.ID_FOLHA = FC.ID_FOLHA 
            JOIN SW_FUNPREV.FUNC_PENSAO_CIVIL PC ON PC.ID_PENSIONISTA = FC.ID_PENSIONISTA 
            JOIN SW_FUNPREV.FUNCIONARIO_INGRESSO FI ON FI.ID_FUNCIONARIO = PC.ID_FUNCIONARIO 
            JOIN SW_FUNPREV.FOLHA_FICHA_FINANCEIRA FF ON FF.ID_FOLHA_FUNCIONARIO = FC.ID_FOLHA_FUNCIONARIO 
            JOIN SW_PUBLICO.FOLHA_RUBRICA FR ON FR.ID_RUBRICA = FF.ID_RUBRICA 
            WHERE FO.MES = :mes 
              AND FO.ANO = :ano 
              AND {condicao_tipo_folha} 
              {condicao_tipo_arquivo}
              AND FR.COD_RUBRICA IN (714400, 714403, 714405, 714410, 714436, 714450, 714460, 714455, 714420, 714452, 714470, 714475, 714480) 
            GROUP BY FO.TIPO_FOLHA_SEFAZ, FR.COD_RUBRICA, FI.ID_REGIME 
        ) S 
        GROUP BY S.RUBRICA, S.DESCRIMINACAO, S.ID_REGIME
        """

    render_bloco_processamento(
        conn=conn,
        titulo="3. PATRONAL FUNPREV",
        id_chave="funprev",
        sql=get_sql_funprev,
        mes=mes,
        ano=ano,
        cod_unidade="924",
        cod_relatorio="90",
        auth_ui=auth_ui,
        seletor_folha_global=tipo_folha_global,
        numero_suplementar=numero_suplementar
    )

    st.divider()

    def get_sql_seduc_011(tipo, cod_sup="002"):
        tipo_arquivo_val = cod_sup if tipo == "suplementar" else "001"
        condicao_tipo_folha = "S.ID_TIPO_FOLHA IN (1000000)" if tipo == "ordinaria" else "S.ID_TIPO_FOLHA NOT IN (1000000)"
        
        return f"""
        SELECT 
            CASE 
                WHEN S.COD_RUBRICA IN (714400, 714403, 714405, 714410) THEN '901' 
                WHEN S.COD_RUBRICA IN (714436, 714450, 714455, 714460) THEN '900' 
            END AS RUBRICA, 
            S.NOME_RUBRICA AS DESCRIMINACAO, 
            CASE 
                WHEN S.ID_REGIME IN (2, 9, 1000003) THEN 'RPPS' 
                ELSE 'RGPS' 
            END AS TIPO_REGIME, 
            CASE 
                WHEN S.ID_REGIME IN (9, 1000003) THEN 'MILITAR' 
                ELSE 'CIVIL' 
            END AS TIPO_VINCULO, 
            0 AS VANTAGENS, 
            REPLACE(TO_CHAR(SUM(S.VALOR_CALCULADO)), ',', '.') AS DESCONTOS 
        FROM ( 
            SELECT 
                'SEDUC' AS ORGAO, 
                FR.NOME_RUBRICA, 
                FR.TIPO, 
                FF.VALOR_CALCULADO, 
                FR.COD_RUBRICA, 
                FI.ID_REGIME, 
                FC.MES, 
                FC.ANO, 
                FO.ID_TIPO_FOLHA, 
                FO.TIPO_ARQUIVO, 
                FO.ID_FONTE 
            FROM SW_SEDUC.FOLHA_CONTRACHEQUE FC 
            JOIN SW_SEDUC.FOLHA FO ON FO.ID_FOLHA = FC.ID_FOLHA 
            JOIN SW_SEDUC.FUNCIONARIO_INGRESSO FI ON FI.ID_FUNCIONARIO = FC.ID_FUNCIONARIO 
            JOIN SW_SEDUC.FOLHA_FICHA_FINANCEIRA FF ON FF.ID_FOLHA_FUNCIONARIO = FC.ID_FOLHA_FUNCIONARIO 
            JOIN SW_PUBLICO.FOLHA_RUBRICA FR ON FR.ID_RUBRICA = FF.ID_RUBRICA 
        ) S 
        WHERE S.MES = :mes 
          AND S.ANO = :ano 
          AND {condicao_tipo_folha} 
          AND S.TIPO_ARQUIVO = '{tipo_arquivo_val}' 
          AND S.COD_RUBRICA IN (714400, 714403, 714405, 714410, 714436, 714450, 714455, 714460) 
          AND S.ID_FONTE IN (4, 5, 6, 7, 8, 9, 1000000, 1000001, 1000002, 1000004, 1000022, 1000023, 1000024, 1000090, 1000100, 1000101, 1000120, 1000121, 1000122, 1000140) 
        GROUP BY S.ORGAO, S.COD_RUBRICA, S.NOME_RUBRICA, S.ID_REGIME 
        ORDER BY S.ORGAO, S.COD_RUBRICA, S.NOME_RUBRICA, S.ID_REGIME
        """

    render_bloco_processamento(
        conn=conn,
        titulo="4. PATRONAL SEDUC 011",
        id_chave="seduc_011",
        sql=get_sql_seduc_011,
        mes=mes,
        ano=ano,
        cod_unidade="011",
        cod_relatorio="90",
        auth_ui=auth_ui,
        seletor_folha_global=tipo_folha_global,
        numero_suplementar=numero_suplementar
    )

    st.divider()

    def get_sql_seduc_914(tipo, cod_sup="002"):
        tipo_arquivo_val = cod_sup if tipo == "suplementar" else "001"
        condicao_tipo_folha = "S.ID_TIPO_FOLHA IN (1000000)" if tipo == "ordinaria" else "S.ID_TIPO_FOLHA NOT IN (1000000)"
        
        return f"""
        SELECT 
            CASE 
                WHEN S.COD_RUBRICA IN (714400, 714403, 714405, 714410) THEN '901' 
                WHEN S.COD_RUBRICA IN (714436, 714450, 714455, 714460) THEN '900' 
            END AS RUBRICA, 
            S.NOME_RUBRICA AS DESCRIMINACAO, 
            CASE 
                WHEN S.ID_REGIME IN (2, 9, 1000003) THEN 'RPPS' 
                ELSE 'RGPS' 
            END AS TIPO_REGIME, 
            CASE 
                WHEN S.ID_REGIME IN (9, 1000003) THEN 'MILITAR' 
                ELSE 'CIVIL' 
            END AS TIPO_VINCULO, 
            0 AS VANTAGENS, 
            REPLACE(TO_CHAR(SUM(S.VALOR_CALCULADO)), ',', '.') AS DESCONTOS 
        FROM ( 
            SELECT 
                'SEDUC' AS ORGAO, 
                FR.NOME_RUBRICA, 
                FR.TIPO, 
                FF.VALOR_CALCULADO, 
                FR.COD_RUBRICA, 
                FI.ID_REGIME, 
                FC.MES, 
                FC.ANO, 
                FO.ID_TIPO_FOLHA, 
                FO.TIPO_ARQUIVO, 
                FO.ID_FONTE 
            FROM SW_SEDUC.FOLHA_CONTRACHEQUE FC 
            JOIN SW_SEDUC.FOLHA FO ON FO.ID_FOLHA = FC.ID_FOLHA 
            JOIN SW_SEDUC.FUNCIONARIO_INGRESSO FI ON FI.ID_FUNCIONARIO = FC.ID_FUNCIONARIO 
            JOIN SW_SEDUC.FOLHA_FICHA_FINANCEIRA FF ON FF.ID_FOLHA_FUNCIONARIO = FC.ID_FOLHA_FUNCIONARIO 
            JOIN SW_PUBLICO.FOLHA_RUBRICA FR ON FR.ID_RUBRICA = FF.ID_RUBRICA 
        ) S 
        WHERE S.MES = :mes 
          AND S.ANO = :ano 
          AND {condicao_tipo_folha} 
          AND S.TIPO_ARQUIVO = '{tipo_arquivo_val}' 
          AND S.COD_RUBRICA IN (714400, 714403, 714405, 714410, 714436, 714450, 714455, 714460) 
          AND S.ID_FONTE IN (1000003, 1000020, 1000021, 1000040, 1000041, 1000060, 1, 2, 3) 
        GROUP BY S.ORGAO, S.COD_RUBRICA, S.NOME_RUBRICA, S.ID_REGIME 
        ORDER BY S.ORGAO, S.COD_RUBRICA, S.NOME_RUBRICA, S.ID_REGIME
        """

    render_bloco_processamento(
        conn=conn,
        titulo="5. PATRONAL SEDUC 914",
        id_chave="seduc_914",
        sql=get_sql_seduc_914,
        mes=mes,
        ano=ano,
        cod_unidade="914",
        cod_relatorio="90",
        auth_ui=auth_ui,
        seletor_folha_global=tipo_folha_global,
        numero_suplementar=numero_suplementar
    )

