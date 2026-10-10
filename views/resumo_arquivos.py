# -*- coding: utf-8 -*-
import json
import pandas as pd
import streamlit as st

STATUS_MAP = {
    "P": "PENDENTE",
    "T": "TRANSMITIDO",
    "A": "ABERTO",
    "F": "FECHADO",
    "I": "INCONSISTENCIA DE CADASTRO",
    "O": "OUTRAS INCONSISTENCIAS",
    "E": "ERRO",
    "X": "EXCLUIDO",
    "V": "VALIDADO",
}

TIPO_REQUISICAO_MAP = {
    "COLABORADOR": "V1",
    "CREDITO": "V2",
    "ORÇAMENTARIO": "V3",
    "ORCAMENTARIO": "V3",
    "PATRONAL": "V4",
}

MESES_LISTA_PADRAO = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr",
    5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago",
    9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
}


def formatar_moeda_br(val):
    if pd.isna(val) or val is None:
        return "R$ 0,00"
    try:
        val_float = float(val)
        return (
            f"R$ {val_float:,.2f}".replace(",", "v")
            .replace(".", ",")
            .replace("v", ".")
        )
    except Exception:
        return "R$ 0,00"


def extrair_texto_payload(blob_data):
    if blob_data is None:
        return None
    try:
        if hasattr(blob_data, "read"):
            content = blob_data.read()
        else:
            content = blob_data

        raw_str = (
            content.decode("utf-8", errors="ignore")
            if isinstance(content, bytes)
            else str(content)
        )

        start, end = raw_str.find("{"), raw_str.rfind("}")
        if start != -1 and end != -1:
            return raw_str[start : end + 1]
        return raw_str.strip()
    except Exception:
        return None


def carregar_dados_arquivos(conn, ano, mes, requisicao_selecionada):
    filtro_req = ""
    params = {"ano": ano, "mes": mes}

    if requisicao_selecionada != "TODOS":
        codigo_req = TIPO_REQUISICAO_MAP.get(requisicao_selecionada.upper())
        if codigo_req:
            filtro_req = "AND sei.IND_TIPO_REQUISICAO = :tipo_req"
            params["tipo_req"] = codigo_req

    query = f"""
        SELECT 
            sei.id_siafe_evento_integracao,
            sei.data_cadastro,
            sei.mes,
            sei.ano,
            sei.status_vobys,
            sei.recibo,
            sei.codigo_sefaz,
            sei.tipo_arquivo,
            sei.IND_TIPO_REQUISICAO,
            e.sigla AS empresa_sigla,
            seip.json AS payload_blob
        FROM sw_publico.SIAFE_EVENTO_INTEGRACAO sei
        INNER JOIN SW_PUBLICO.Siafe_Evento_Integ_Payload seip 
            ON seip.id_siafe_evento_integracao = sei.id_siafe_evento_integracao
        LEFT JOIN sw_publico.empresa e ON e.id_empresa = sei.id_empresa
        WHERE sei.ANO = :ano
          AND sei.MES = :mes
          {filtro_req}
        ORDER BY sei.id_siafe_evento_integracao DESC
    """
    try:
        df_raw = pd.read_sql(query, conn, params=params)
    except Exception as e:
        st.error(f"Erro ao consultar dados no banco: {e}")
        return pd.DataFrame()

    if df_raw.empty:
        return pd.DataFrame()

    df_raw.columns = [c.lower() for c in df_raw.columns]

    registros = []
    for _, row in df_raw.iterrows():
        blob_data = row.get("payload_blob")
        json_str = extrair_texto_payload(blob_data)

        valor_bruto = 0.0
        valor_liquido = 0.0
        valor_provento = 0.0
        desconto_orcamentario = 0.0
        desconto_patronal = 0.0

        cod_sefaz_json = None
        tp_arquivo_json = None
        cod_relatorio_json = None

        ind_req = str(row.get("ind_tipo_requisicao") or "").upper()

        if json_str:
            try:
                dados = json.loads(json_str)
                cod_sefaz_json = dados.get("codigoUnidadeSistemaExterno")
                tp_arquivo_json = dados.get("codigoExterno")
                cod_relatorio_json = dados.get("codigoRelatorioFolhaPagamento")

                pagamentos = dados.get("pagamentos", [])
                if isinstance(pagamentos, list):
                    for p in pagamentos:
                        if isinstance(p, dict):
                            if "valorBruto" in p or "valorLiquido" in p:
                                valor_bruto += float(p.get("valorBruto") or 0.0)
                                valor_liquido += float(p.get("valorLiquido") or 0.0)

                            if "valor" in p:
                                valor_provento += float(p.get("valor") or 0.0)

                            if "valorDesconto" in p:
                                val_desc = float(p.get("valorDesconto") or 0.0)
                                if ind_req == "V3":
                                    desconto_orcamentario += val_desc
                                elif ind_req == "V4":
                                    desconto_patronal += val_desc
                                else:
                                    desconto_orcamentario += val_desc
            except Exception:
                pass

        id_reg = row.get("id_siafe_evento_integracao")
        dt_cad = row.get("data_cadastro")
        empresa = row.get("empresa_sigla") or cod_sefaz_json or "-"
        
        rec_raw = row.get("recibo")
        try:
            recibo = int(rec_raw) if rec_raw is not None else 0
        except Exception:
            recibo = 0

        cod_sefaz = row.get("codigo_sefaz") or cod_sefaz_json or "-"
        tp_arquivo = row.get("tipo_arquivo") or tp_arquivo_json or "-"

        st_raw = str(row.get("status_vobys") or "").upper()
        status_desc = STATUS_MAP.get(st_raw, st_raw if st_raw else "ABERTO")

        tipo_req_desc = {
            "V1": "COLABORADOR",
            "V2": "CREDITO",
            "V3": "ORÇAMENTARIO",
            "V4": "PATRONAL"
        }.get(ind_req, ind_req)

        registros.append(
            {
                "Id": id_reg,
                "Data Cadastro": dt_cad,
                "Empresa": empresa,
                "Status": status_desc,
                "Recibo": recibo,
                "Código Sefaz": cod_sefaz,
                "Tipo Requisição": tipo_req_desc,
                "Tipo de Arquivo": str(tp_arquivo),
                "Código de Relatório": cod_relatorio_json or "-",
                "Valor Bruto": float(valor_bruto),
                "Valor Líquido": float(valor_liquido),
                "Valor Provento": float(valor_provento),
                "Desconto Orçamentário": float(desconto_orcamentario),
                "Desconto Patronal": float(desconto_patronal),
            }
        )

    return pd.DataFrame(registros)


def render(conn, ano=None, mes=None, meses_lista=None, *args, **kwargs):
    if ano is None:
        ano = st.session_state.get("ano_selecionado", st.session_state.get("ano", 2026))
    if mes is None:
        mes = st.session_state.get("mes_selecionado", st.session_state.get("mes", 8))
    if meses_lista is None:
        meses_lista = st.session_state.get("meses_lista", MESES_LISTA_PADRAO)

    nome_mes = meses_lista.get(mes, str(mes)) if isinstance(meses_lista, dict) else str(mes)

    st.markdown(
        """
        <style>
            .block-container {
                padding-top: 3.5rem !important;
                padding-bottom: 1rem !important;
            }
            h1 {
                margin-top: 0rem !important;
                padding-bottom: 0.2rem !important;
                font-size: 1.8rem !important;
            }
            hr {
                margin: 0.4rem 0 !important;
            }
            h3 {
                margin-top: 0.2rem !important;
                margin-bottom: 0.2rem !important;
                font-size: 1.2rem !important;
            }
            div[data-baseweb="popover"] {
                max-height: 220px !important;
            }
            /* Ajuste para acomodar valores monetários grandes nos cartões de métrica */
            div[data-testid="stMetricValue"] {
                font-size: 1.35rem !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title(f"📊 Totalização de Arquivos ({nome_mes}/{ano})")

    tipos_requisicao = ["TODOS", "COLABORADOR", "CREDITO", "ORÇAMENTARIO", "PATRONAL"]
    
    col_sel_req, _ = st.columns([2, 2])
    requisicao_selecionada = col_sel_req.selectbox(
        "Selecione o Tipo de Requisição:",
        options=tipos_requisicao,
        index=0
    )

    st.divider()

    with st.spinner(f"Carregando e processando arquivos ({requisicao_selecionada})..."):
        df_dados = carregar_dados_arquivos(conn, ano, mes, requisicao_selecionada)

    if df_dados.empty:
        st.warning(f"Nenhum registro encontrado para a requisição '{requisicao_selecionada}' no período.")
        return

    with st.expander("🎯 Filtros de Pesquisa / Seleção de Valores", expanded=False):
        f_col1, f_col2, f_col3, f_col4 = st.columns(4)

        empresas_disponiveis = sorted([x for x in df_dados["Empresa"].unique() if x != "-"])
        sel_empresa = f_col1.multiselect("Empresa:", options=empresas_disponiveis, placeholder="Todas")

        relatorios_disponiveis = sorted([x for x in df_dados["Código de Relatório"].unique() if x != "-"])
        sel_relatorio = f_col2.multiselect("Código de Relatório:", options=relatorios_disponiveis, placeholder="Todos")

        tipos_arq_disp = sorted([x for x in df_dados["Tipo de Arquivo"].unique() if x != "-"])
        sel_tipo_arq = f_col3.multiselect("Tipo de Arquivo:", options=tipos_arq_disp, placeholder="Todos")

        status_disponiveis = sorted([x for x in df_dados["Status"].unique() if x != "-"])
        sel_status = f_col4.multiselect("Status:", options=status_disponiveis, placeholder="Todos")

    df_filtrado = df_dados.copy()

    if sel_empresa:
        df_filtrado = df_filtrado[df_filtrado["Empresa"].isin(sel_empresa)]
    if sel_relatorio:
        df_filtrado = df_filtrado[df_filtrado["Código de Relatório"].isin(sel_relatorio)]
    if sel_tipo_arq:
        df_filtrado = df_filtrado[df_filtrado["Tipo de Arquivo"].isin(sel_tipo_arq)]
    if sel_status:
        df_filtrado = df_filtrado[df_filtrado["Status"].isin(sel_status)]

    # --- 4. MÉTRICAS COMPACTAS COM DISTRIBUIÇÃO OTIMIZADA PARA VALORES GRANDES ---
    m_col1, m_col2, m_col3, m_col4, m_col5, m_col6 = st.columns([1, 1.8, 1.8, 1.8, 1.8, 1.8])

    m_col1.metric("Arquivos", len(df_filtrado))

    soma_bruto = df_filtrado["Valor Bruto"].sum() if not df_filtrado.empty else 0.0
    m_col2.metric("Total Bruto", formatar_moeda_br(soma_bruto))

    soma_liquido = df_filtrado["Valor Líquido"].sum() if not df_filtrado.empty else 0.0
    m_col3.metric("Total Líquido", formatar_moeda_br(soma_liquido))

    soma_provento = df_filtrado["Valor Provento"].sum() if not df_filtrado.empty else 0.0
    m_col4.metric("Total Provento", formatar_moeda_br(soma_provento))

    soma_desc_orc = df_filtrado["Desconto Orçamentário"].sum() if not df_filtrado.empty else 0.0
    m_col5.metric("Desc. Orçamentário", formatar_moeda_br(soma_desc_orc))

    soma_desc_patr = df_filtrado["Desconto Patronal"].sum() if not df_filtrado.empty else 0.0
    m_col6.metric("Desc. Patronal", formatar_moeda_br(soma_desc_patr))

    st.divider()

    if df_filtrado.empty:
        st.info("Nenhum registro encontrado para os filtros selecionados.")
        return

    st.markdown("### 🔍 Agrupamento Dinâmico")
    opcoes_agrupamento = [
        "Empresa",
        "Código de Relatório",
        "Código Sefaz",
        "Tipo Requisição",
        "Tipo de Arquivo",
        "Status",
        "Recibo",
    ]

    campos_agrupamento = st.multiselect(
        "Selecione os campos para agrupar e totalizar os valores:",
        options=opcoes_agrupamento,
        default=["Empresa", "Código de Relatório", "Tipo de Arquivo", "Status", "Recibo"],
        help="Marque os campos para agrupar e calcular os somatórios",
    )

    if campos_agrupamento:
        df_resumo = (
            df_filtrado.groupby(campos_agrupamento, as_index=False)
            .agg(
                Valor_Bruto=("Valor Bruto", "sum"),
                Valor_Liquido=("Valor Líquido", "sum"),
                Valor_Provento=("Valor Provento", "sum"),
                Desconto_Orcamentario=("Desconto Orçamentário", "sum"),
                Desconto_Patronal=("Desconto Patronal", "sum"),
            )
        )

        st.caption(
            f"Exibindo resumo agrupado por: **{', '.join(campos_agrupamento)}**"
        )
        st.dataframe(
            df_resumo,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Recibo": st.column_config.NumberColumn("Recibo", format="%d"),
                "Valor_Bruto": st.column_config.NumberColumn("Valor Bruto (R$)", format="R$ %.2f"),
                "Valor_Liquido": st.column_config.NumberColumn("Valor Líquido (R$)", format="R$ %.2f"),
                "Valor_Provento": st.column_config.NumberColumn("Valor Provento (R$)", format="R$ %.2f"),
                "Desconto_Orcamentario": st.column_config.NumberColumn("Desc. Orçamentário (R$)", format="R$ %.2f"),
                "Desconto_Patronal": st.column_config.NumberColumn("Desc. Patronal (R$)", format="R$ %.2f"),
            },
        )
    else:
        st.info(
            "Nenhum filtro de agrupamento selecionado. Exibindo a listagem detalhada de registros:"
        )
        st.dataframe(
            df_filtrado,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Recibo": st.column_config.NumberColumn("Recibo", format="%d"),
                "Valor Bruto": st.column_config.NumberColumn("Valor Bruto (R$)", format="R$ %.2f"),
                "Valor Líquido": st.column_config.NumberColumn("Valor Líquido (R$)", format="R$ %.2f"),
                "Valor Provento": st.column_config.NumberColumn("Valor Provento (R$)", format="R$ %.2f"),
                "Desconto Orçamentário": st.column_config.NumberColumn("Desc. Orçamentário (R$)", format="R$ %.2f"),
                "Desconto Patronal": st.column_config.NumberColumn("Desc. Patronal (R$)", format="R$ %.2f"),
            },
        )

