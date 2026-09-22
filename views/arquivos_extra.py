# -*- coding: utf-8 -*-
import json
import requests
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import urllib3

# Desativa alertas de certificado SSL não verificado (verify=False)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Importação da query específica do EMGERPI
try:
    from queries import get_query_json_patronal_emgerpi
except ImportError:
    def get_query_json_patronal_emgerpi(ano, mes):
        return "SELECT json_data FROM dual"


# --- FUNÇÕES AUXILIARES DE CONVERSÃO E BANCO ---

def construir_payload_json(df, mes, ano, cod_unidade, cod_relatorio):
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

    payload = {
        "codigoUnidadeSistemaExterno": str(cod_unidade),
        "mes": int(mes),
        "idTipoFolha": 9,
        "codigoExterno": "001",
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

    cursor.execute(query, params_clean)
    columns = [col[0] for col in cursor.description]
    data = cursor.fetchall()
    cursor.close()
    return pd.DataFrame(data, columns=columns)


def executar_query_emgerpi(conn, ano, mes):
    sql_json = get_query_json_patronal_emgerpi(ano, mes)
    cursor = conn.cursor()
    cursor.execute(sql_json)
    row = cursor.fetchone()
    cursor.close()
    if row:
        return row[0]
    return None


# --- INTEGRAÇÃO COM A API SEFAZ-PI ---

def transmitir_para_sefaz(payload_dados, ano):
    """Função que exige estritamente credenciais presentes na sessão para autenticação e envio."""
    try:
        usuario = st.session_state.get("sefaz_cpf")
        senha = st.session_state.get("sefaz_pass")
        is_autenticado = st.session_state.get("sefaz_auth", False)

        if not is_autenticado or not usuario or not senha:
            return False, None, "Erro: Credenciais não informadas ou utilizador desconectado da SEFAZ. Por favor, autentique-se novamente."

        sefaz_sec = st.secrets.get("sefaz", {})
        base_url = sefaz_sec.get("BASE_URL") or sefaz_sec.get("base_url", "https://tesouro.sefaz.pi.gov.br/api")

        if not base_url:
            return False, None, "Erro: BASE_URL da SEFAZ não configurada nos secrets."

        if payload_dados is None:
            return False, None, "Erro: O payload de dados está vazio ou nulo."

        if isinstance(payload_dados, str):
            try:
                payload_obj = json.loads(payload_dados)
            except json.JSONDecodeError as jde:
                return False, None, f"Erro ao converter string JSON: {str(jde)}"
        else:
            payload_obj = payload_dados

        session = requests.Session()
        session.verify = False

        payload_auth = {"usuario": usuario, "senha": senha}
        r_auth = session.post(f"{base_url}/auth", json=payload_auth, timeout=10)
        r_auth.raise_for_status()

        token = r_auth.json().get("token")
        if not token:
            return False, None, "Erro: Token de autenticação não retornado pela API /auth."

        session.headers.update({"Authorization": f"Bearer {token}"})

        url_final = f"{base_url}/folha-pagamento/contabilizacao-folha-pagamento/{ano}"
        response = session.post(url_final, json=payload_obj, timeout=15)
        sucesso = response.status_code in [200, 201]

        try:
            retorno_json = response.json()
        except Exception:
            retorno_json = response.text

        return sucesso, json.dumps(payload_obj, ensure_ascii=False), retorno_json

    except requests.exceptions.HTTPError as he:
        status = he.response.status_code if he.response else "Desconhecido"
        texto = he.response.text if he.response else str(he)
        if status in (401, 403):
            st.session_state["sefaz_auth"] = False
            st.session_state.pop("sefaz_cpf", None)
            st.session_state.pop("sefaz_pass", None)
        return False, None, f"Erro HTTP {status}: {texto}"
    except Exception as e:
        return False, None, str(e)


# --- BLOCO DE RENDERIZAÇÃO DA INTERFACE ---

def render_bloco_processamento(conn, titulo, id_chave, sql, mes, ano, cod_unidade=None, cod_relatorio=None, auth_ui=None):
    if cod_unidade and cod_relatorio:
        nome_arquivo_base = f"FP_{cod_unidade}_9_{ano}{int(mes):02d}_001_{cod_relatorio}"
        titulo_exibicao = f"{titulo} - {nome_arquivo_base}"
    else:
        nome_arquivo_base = f"PATRONAL_{id_chave.upper()}_{ano}{int(mes):02d}"
        titulo_exibicao = titulo

    st.subheader(titulo_exibicao)
    
    data_key = f"df_extra_{id_chave}_{ano}_{mes}"
    json_raw_key = f"json_raw_{id_chave}_{ano}_{mes}"
    retorno_key = f"retorno_envio_{id_chave}_{ano}_{mes}"
    flag_envio_key = f"executar_envio_{id_chave}_{ano}_{mes}"

    col_gerar, col_json, col_csv, col_enviar = st.columns([1.2, 1.2, 1.2, 1.2])

    # 1. Botão Gerar Ficheiro / JSON
    if col_gerar.button(f"⚙️ Gerar Arquivo", key=f"btn_gerar_{id_chave}"):
        try:
            with st.spinner(f"A gerar dados para {titulo}..."):
                if id_chave == "emgerpi":
                    json_str = executar_query_emgerpi(conn, ano, mes)
                    if json_str:
                        st.session_state[json_raw_key] = json_str
                        dados = json.loads(json_str)
                        pagamentos = dados.get("pagamentos", dados) if isinstance(dados, dict) else dados
                        st.session_state[data_key] = pd.json_normalize(pagamentos)
                    else:
                        st.session_state[json_raw_key] = None
                        st.session_state[data_key] = pd.DataFrame()
                elif sql:
                    df = executar_query(conn, sql, {"mes": mes, "ano": ano})
                    st.session_state[data_key] = df
                    if not df.empty and cod_unidade and cod_relatorio:
                        payload_obj = construir_payload_json(df, mes, ano, cod_unidade, cod_relatorio)
                        st.session_state[json_raw_key] = json.dumps(payload_obj, ensure_ascii=False, indent=2)
                st.session_state.pop(retorno_key, None)
                st.session_state.pop(flag_envio_key, None)
        except Exception as e:
            st.error(f"Erro ao consultar base de dados: {str(e)}")
            st.session_state[data_key] = None

    df_gerado = st.session_state.get(data_key)
    json_raw = st.session_state.get(json_raw_key)

    # 2. Exibição das Ações de Download e Transmissão
    if df_gerado is not None and not df_gerado.empty:
        if json_raw:
            col_json.download_button(
                label="📄 Baixar JSON",
                data=json_raw.encode('utf-8'),
                file_name=f"{nome_arquivo_base}.json",
                mime="application/json",
                key=f"btn_json_{id_chave}"
            )

        col_csv.download_button(
            label="📊 Baixar CSV",
            data=converter_para_csv(df_gerado),
            file_name=f"{nome_arquivo_base}.csv",
            mime="text/csv",
            key=f"btn_csv_{id_chave}"
        )

        if col_enviar.button(f"🚀 Enviar Arquivo", key=f"btn_enviar_{id_chave}", type="primary"):
            if not st.session_state.get("sefaz_auth", False):
                st.session_state["tentando_enviar_sefaz"] = True
                if auth_ui and hasattr(auth_ui, "garantir_autenticacao_sefaz"):
                    auth_ui.garantir_autenticacao_sefaz(servico_nome=f"Transmissão - {titulo}")
            else:
                st.session_state[flag_envio_key] = True
                st.rerun()

        if st.session_state.get(flag_envio_key):
            if not st.session_state.get("sefaz_auth", False):
                st.warning("⚠️ É necessário autenticar-se na SEFAZ para realizar o envio.")
                st.session_state[flag_envio_key] = False
            else:
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

    # 3. Bloco Visual Moderno para Exibição do Recibo e Retorno da SEFAZ
    resp_sefaz = st.session_state.get(retorno_key)
    if resp_sefaz:
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

        if isinstance(resp_sefaz, dict):
            codigo_recibo = resp_sefaz.get("codigo", "N/D")
            qtd_recebidos = resp_sefaz.get("qtdPagamentosRecebidos", 0)
            data_hora = str(resp_sefaz.get("dataHoraCadastro", "-"))[:19].replace("T", " ")
            status_obs = resp_sefaz.get("observacao", "Sucesso")

            st.markdown(f"""
            <div class="receipt-box">
                <div class="receipt-header">✅ Comprovante de Transmissão / Recibo SIAFE</div>
                <div class="receipt-grid">
                    <div class="receipt-item">
                        <label>Nº do Recibo / Código</label>
                        <value>{codigo_recibo}</value>
                    </div>
                    <div class="receipt-item">
                        <label>Registros Aceitos</label>
                        <value>{qtd_recebidos}</value>
                    </div>
                    <div class="receipt-item">
                        <label>Data / Hora</label>
                        <value>{data_hora}</value>
                    </div>
                    <div class="receipt-item">
                        <label>Status</label>
                        <value>{status_obs}</value>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info(f"Retorno SEFAZ: {resp_sefaz}")

    # 4. Visualização e Totalização dos Dados
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

            # Cálculo dos totais
            col_v = 'valor' if 'valor' in df_exibicao.columns else ('VANTAGENS' if 'VANTAGENS' in df_exibicao.columns else None)
            col_d = 'valorDesconto' if 'valorDesconto' in df_exibicao.columns else ('DESCONTOS' if 'DESCONTOS' in df_exibicao.columns else None)
            
            tot_v = df_exibicao[col_v].sum() if col_v else 0.0
            tot_d = df_exibicao[col_d].sum() if col_d else 0.0

            # Formatação para moeda (R$)
            str_tot_v = f"R$ {tot_v:,.2f}".replace(',', 'v').replace('.', ',').replace('v', '.')
            str_tot_d = f"R$ {tot_d:,.2f}".replace(',', 'v').replace('.', ',').replace('v', '.')

            # Formatação para visualização em formato de moeda na tabela
            df_tabela_formatada = df_exibicao.copy()
            for col in cols_valores:
                if col in df_tabela_formatada.columns:
                    df_tabela_formatada[col] = df_tabela_formatada[col].apply(
                        lambda x: f"R$ {x:,.2f}".replace(',', 'v').replace('.', ',').replace('v', '.')
                    )

            # Renderização via Tabela HTML customizada com cantos arredondados e bloco de totais integrado
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
                /* Cantos arredondados na primeira e última coluna do cabeçalho */
                .custom-preview-table th:first-child {{
                    border-top-left-radius: 8px;
                }}
                .custom-preview-table th:last-child {{
                    border-top-right-radius: 8px;
                }}
                /* Alinhamento à direita nas colunas de valores */
                .custom-preview-table th:nth-last-child(-n+2), 
                .custom-preview-table td:nth-last-child(-n+2) {{
                    text-align: right !important;
                }}
                /* Bloco de Totais Integrado */
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


def render(conn, ano, mes, meses_lista=None, auth_ui=None):
    if meses_lista is None:
        meses_lista = {
            1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
            5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
            9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
        }

    st.title("📁 Gerador e Transmissor de Arquivos Extras")
    mes_nome = meses_lista.get(int(mes), str(mes))
    st.caption(f"**Competência Selecionada:** {mes_nome}/{ano}")
    st.divider()

    # 1. PATRONAL EMGERPI
    render_bloco_processamento(
        conn=conn,
        titulo="1. PATRONAL EMGERPI",
        id_chave="emgerpi",
        sql=None,
        mes=mes,
        ano=ano,
        cod_unidade="120",
        cod_relatorio="93",
        auth_ui=auth_ui
    )

    st.divider()

    # 2. PATRONAL EXTRA SEDUC
    sql_seduc_extra = """
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
      AND S.ID_TIPO_FOLHA IN (1000000) 
      AND S.TIPO_ARQUIVO = '001' 
      AND S.COD_RUBRICA IN (714401, 714406, 714451, 714456) 
      AND S.ID_FONTE IN (1000003, 1000020, 1000021, 1000040, 1000041, 1000060, 1, 2, 3) 
    GROUP BY S.ORGAO, S.COD_RUBRICA, S.NOME_RUBRICA, S.ID_REGIME 
    ORDER BY S.ORGAO, S.COD_RUBRICA, S.NOME_RUBRICA, S.ID_REGIME
    """
    render_bloco_processamento(
        conn=conn,
        titulo="2. PATRONAL EXTRA SEDUC",
        id_chave="seduc_extra",
        sql=sql_seduc_extra,
        mes=mes,
        ano=ano,
        cod_unidade="011",
        cod_relatorio="99",
        auth_ui=auth_ui
    )

    st.divider()

    # 3. PATRONAL FUNPREV
    sql_funprev = """
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
          AND FO.ID_TIPO_FOLHA IN (1000000) 
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
          AND FO.ID_TIPO_FOLHA IN (1000000) 
          AND FR.COD_RUBRICA IN (714400, 714403, 714405, 714410, 714436, 714450, 714460, 714455, 714420, 714452, 714470, 714475, 714480) 
        GROUP BY FO.TIPO_FOLHA_SEFAZ, FR.COD_RUBRICA, FI.ID_REGIME 
    ) S 
    GROUP BY S.RUBRICA, S.DESCRIMINACAO, S.ID_REGIME
    """
    render_bloco_processamento(
        conn=conn,
        titulo="3. PATRONAL FUNPREV",
        id_chave="funprev",
        sql=sql_funprev,
        mes=mes,
        ano=ano,
        cod_unidade="924",
        cod_relatorio="90",
        auth_ui=auth_ui
    )

    st.divider()

    # 4. PATRONAL SEDUC 011
    sql_seduc_011 = """
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
      AND S.ID_TIPO_FOLHA IN (1000000) 
      AND S.TIPO_ARQUIVO = '001' 
      AND S.COD_RUBRICA IN (714400, 714403, 714405, 714410, 714436, 714450, 714455, 714460) 
      AND S.ID_FONTE IN (4, 5, 6, 7, 8, 9, 1000000, 1000001, 1000002, 1000004, 1000022, 1000023, 1000024, 1000090, 1000100, 1000101, 1000120, 1000121, 1000122, 1000140) 
    GROUP BY S.ORGAO, S.COD_RUBRICA, S.NOME_RUBRICA, S.ID_REGIME 
    ORDER BY S.ORGAO, S.COD_RUBRICA, S.NOME_RUBRICA, S.ID_REGIME
    """
    render_bloco_processamento(
        conn=conn,
        titulo="4. PATRONAL SEDUC 011",
        id_chave="seduc_011",
        sql=sql_seduc_011,
        mes=mes,
        ano=ano,
        cod_unidade="011",
        cod_relatorio="90",
        auth_ui=auth_ui
    )

    st.divider()

    # 5. PATRONAL SEDUC 914
    sql_seduc_914 = """
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
      AND S.ID_TIPO_FOLHA IN (1000000) 
      AND S.TIPO_ARQUIVO = '001' 
      AND S.COD_RUBRICA IN (714400, 714403, 714405, 714410, 714436, 714450, 714455, 714460) 
      AND S.ID_FONTE IN (1000003, 1000020, 1000021, 1000040, 1000041, 1000060, 1, 2, 3) 
    GROUP BY S.ORGAO, S.COD_RUBRICA, S.NOME_RUBRICA, S.ID_REGIME 
    ORDER BY S.ORGAO, S.COD_RUBRICA, S.NOME_RUBRICA, S.ID_REGIME
    """
    render_bloco_processamento(
        conn=conn,
        titulo="5. PATRONAL SEDUC 914",
        id_chave="seduc_914",
        sql=sql_seduc_914,
        mes=mes,
        ano=ano,
        cod_unidade="914",
        cod_relatorio="90",
        auth_ui=auth_ui
    )

