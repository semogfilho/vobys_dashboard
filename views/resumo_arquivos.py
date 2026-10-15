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


def carregar_dados_arquivos(conn, ano, mes, requisicoes_selecionadas):
    filtro_req = ""
    params = {"ano": ano, "mes": mes}

    if requisicoes_selecionadas and "TODOS" not in [r.upper() for r in requisicoes_selecionadas]:
        codigos_req = [
            TIPO_REQUISICAO_MAP.get(r.upper())
            for r in requisicoes_selecionadas
            if TIPO_REQUISICAO_MAP.get(r.upper())
        ]
        if codigos_req:
            param_names = [f":req_{i}" for i in range(len(codigos_req))]
            filtro_req = f"AND sei.IND_TIPO_REQUISICAO IN ({', '.join(param_names)})"
            for i, cod in enumerate(codigos_req):
                params[f"req_{i}"] = cod

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
        id_tipo_folha_json = "-"

        ind_req = str(row.get("ind_tipo_requisicao") or "").upper()

        if json_str:
            try:
                dados = json.loads(json_str)
                cod_sefaz_json = dados.get("codigoUnidadeSistemaExterno")
                tp_arquivo_json = dados.get("codigoExterno")
                cod_relatorio_json = dados.get("codigoRelatorioFolhaPagamento")
                
                id_tf = dados.get("idTipoFolha")
                if id_tf is not None:
                    id_tipo_folha_json = str(id_tf)

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

        cod_sefaz = str(row.get("codigo_sefaz") or cod_sefaz_json or "-")
        tp_arquivo = str(row.get("tipo_arquivo") or tp_arquivo_json or "-")

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
                "Tipo de Arquivo": tp_arquivo,
                "Código de Relatório": cod_relatorio_json or "-",
                "idTipoFolha": id_tipo_folha_json,
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
            div[data-testid="stMetricValue"] {
                font-size: 1.35rem !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title(f"📊 Totalização de Arquivos ({nome_mes}/{ano})")

    tipos_requisicao_opcoes = ["COLABORADOR", "CREDITO", "ORÇAMENTARIO", "PATRONAL"]
    
    col_sel_req, _ = st.columns([3, 1])
    requisicoes_selecionadas = col_sel_req.multiselect(
        "Selecione o(s) Tipo(s) de Requisição:",
        options=tipos_requisicao_opcoes,
        default=[],
        placeholder="Todos os Tipos"
    )

    st.divider()

    desc_spinner = ", ".join(requisicoes_selecionadas) if requisicoes_selecionadas else "Todos"
    with st.spinner(f"Carregando e processando arquivos ({desc_spinner})..."):
        df_dados = carregar_dados_arquivos(conn, ano, mes, requisicoes_selecionadas)

    if df_dados.empty:
        st.warning("Nenhum registro encontrado para os tipos de requisição selecionados no período.")
        return

    # --- FILTROS DE PESQUISA ---
    with st.expander("🎯 Filtros de Pesquisa / Seleção de Valores", expanded=False):
        f_col1, f_col2, f_col3, f_col4, f_col5, f_col6 = st.columns(6)

        empresas_unicas = [x for x in df_dados["Empresa"].unique() if x != "-"]
        if any(str(x).startswith("EMGERPI") for x in empresas_unicas):
            if "EMGERPI" not in empresas_unicas:
                empresas_unicas.append("EMGERPI")
        empresas_disponiveis = sorted(empresas_unicas)

        sel_empresa = f_col1.multiselect("Empresa:", options=empresas_disponiveis, placeholder="Todas")

        relatorios_disponiveis = sorted([x for x in df_dados["Código de Relatório"].unique() if x != "-"])
        sel_relatorio = f_col2.multiselect("Código de Relatório:", options=relatorios_disponiveis, placeholder="Todos")

        tipos_folha_disp = sorted([x for x in df_dados["idTipoFolha"].unique() if x != "-"])
        sel_tipo_folha = f_col3.multiselect("Tipo de Folha:", options=tipos_folha_disp, placeholder="Todas")

        cod_sefaz_disp = sorted([x for x in df_dados["Código Sefaz"].unique() if x != "-"])
        sel_cod_sefaz = f_col4.multiselect("Código Sefaz:", options=cod_sefaz_disp, placeholder="Todos")

        tipos_arq_disp = sorted([x for x in df_dados["Tipo de Arquivo"].unique() if x != "-"])
        sel_tipo_arq = f_col5.multiselect("Tipo de Arquivo:", options=tipos_arq_disp, placeholder="Todos")

        status_disponiveis = sorted([x for x in df_dados["Status"].unique() if x != "-"])
        sel_status = f_col6.multiselect("Status:", options=status_disponiveis, placeholder="Todos")

    df_filtrado = df_dados.copy()

    if sel_empresa:
        empresas_efetivas = set()
        for emp in sel_empresa:
            if emp == "EMGERPI":
                matches = [x for x in df_dados["Empresa"].unique() if str(x).startswith("EMGERPI")]
                empresas_efetivas.update(matches)
            else:
                empresas_efetivas.add(emp)
        df_filtrado = df_filtrado[df_filtrado["Empresa"].isin(list(empresas_efetivas))]

    if sel_relatorio:
        df_filtrado = df_filtrado[df_filtrado["Código de Relatório"].isin(sel_relatorio)]
    if sel_tipo_folha:
        df_filtrado = df_filtrado[df_filtrado["idTipoFolha"].isin(sel_tipo_folha)]
    if sel_cod_sefaz:
        df_filtrado = df_filtrado[df_filtrado["Código Sefaz"].isin(sel_cod_sefaz)]
    if sel_tipo_arq:
        df_filtrado = df_filtrado[df_filtrado["Tipo de Arquivo"].isin(sel_tipo_arq)]
    if sel_status:
        df_filtrado = df_filtrado[df_filtrado["Status"].isin(sel_status)]

    # --- EXCLUSÃO DE EXCLUIDO E VALIDADO DAS SOMATÓRIAS ---
    df_para_somatoria = df_filtrado[~df_filtrado["Status"].isin(["EXCLUIDO", "VALIDADO"])]
    
    # Desconsiderar o líquido dos registros de CRÉDITO (V2) na somatória global e validação
    df_somatoria_liquido = df_para_somatoria[df_para_somatoria["Tipo Requisição"] != "CREDITO"]

    # --- MÉTRICAS COMPACTAS COM DISTRIBUIÇÃO OTIMIZADA ---
    m_col1, m_col2, m_col3, m_col4, m_col5, m_col6 = st.columns([1, 1.8, 1.8, 1.8, 1.8, 1.8])

    m_col1.metric("Arquivos", len(df_filtrado))

    soma_bruto = df_para_somatoria["Valor Bruto"].sum() if not df_para_somatoria.empty else 0.0
    m_col2.metric("Total Bruto", formatar_moeda_br(soma_bruto))

    soma_liquido = df_somatoria_liquido["Valor Líquido"].sum() if not df_somatoria_liquido.empty else 0.0
    m_col3.metric("Total Líquido", formatar_moeda_br(soma_liquido))

    soma_provento = df_para_somatoria["Valor Provento"].sum() if not df_para_somatoria.empty else 0.0
    m_col4.metric("Total Provento", formatar_moeda_br(soma_provento))

    soma_desc_orc = df_para_somatoria["Desconto Orçamentário"].sum() if not df_para_somatoria.empty else 0.0
    m_col5.metric("Desc. Orçamentário", formatar_moeda_br(soma_desc_orc))

    soma_desc_patr = df_para_somatoria["Desconto Patronal"].sum() if not df_para_somatoria.empty else 0.0
    m_col6.metric("Desc. Patronal", formatar_moeda_br(soma_desc_patr))

    # --- ALERTA DE DIVERGÊNCIA MATEMÁTICA ---
    liquido_esperado = soma_provento - soma_desc_orc
    diferenca = round(soma_liquido - liquido_esperado, 2)

    if abs(diferenca) > 0.01:
        diff_fmt = formatar_moeda_br(abs(diferenca))
        st.warning(
            f"⚠️ **Atenção:** Existe uma divergência de **{diff_fmt}** entre o "
            f"Valor Líquido e a relação (Proventos - Descontos)."
        )

    st.divider()

    if df_filtrado.empty:
        st.info("Nenhum registro encontrado para os filtros selecionados.")
        return

    # --- AGRUPAMENTO DINÂMICO ---
    with st.expander("🔍 Agrupamento Dinâmico de Registros", expanded=False):
        opcoes_agrupamento = [
            "Id",
            "Empresa",
            "Código de Relatório",
            "idTipoFolha",
            "Código Sefaz",
            "Tipo Requisição",
            "Tipo de Arquivo",
            "Status",
            "Recibo",
        ]

        campos_agrupamento = st.multiselect(
            "Selecione os campos para agrupar e totalizar os valores:",
            options=opcoes_agrupamento,
            default=["Id", "Empresa", "Código de Relatório", "idTipoFolha", "Código Sefaz", "Tipo de Arquivo", "Status", "Recibo"],
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
                    "Id": st.column_config.NumberColumn("Id", format="%d"),
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
                    "Id": st.column_config.NumberColumn("Id", format="%d"),
                    "Recibo": st.column_config.NumberColumn("Recibo", format="%d"),
                    "Valor Bruto": st.column_config.NumberColumn("Valor Bruto (R$)", format="R$ %.2f"),
                    "Valor Líquido": st.column_config.NumberColumn("Valor Líquido (R$)", format="R$ %.2f"),
                    "Valor Provento": st.column_config.NumberColumn("Valor Provento (R$)", format="R$ %.2f"),
                    "Desconto Orçamentário": st.column_config.NumberColumn("Desc. Orçamentário (R$)", format="R$ %.2f"),
                    "Desconto Patronal": st.column_config.NumberColumn("Desc. Patronal (R$)", format="R$ %.2f"),
                },
            )

    # --- ISOLAMENTO E DETECÇÃO DE DESCOMPASSO (COM CÓDIGO SEFAZ) ---
    with st.expander("🚨 Recibos com Divergência Efetiva Detectados", expanded=True):
        df_v1 = df_filtrado[df_filtrado["Tipo Requisição"] == "COLABORADOR"].copy()
        df_v3 = df_filtrado[df_filtrado["Tipo Requisição"] == "ORÇAMENTARIO"].copy()

        recibos_problematicos = []
        sugestao_recibos = ""

        if not df_v1.empty and not df_v3.empty:
            for empresa_g in df_filtrado["Empresa"].unique():
                df_v1_emp = df_v1[df_v1["Empresa"] == empresa_g]
                df_v3_emp = df_v3[df_v3["Empresa"] == empresa_g]

                for cod_sefaz in df_filtrado["Código Sefaz"].unique():
                    df_v1_sef = df_v1_emp[df_v1_emp["Código Sefaz"] == cod_sefaz]
                    df_v3_sef = df_v3_emp[df_v3_emp["Código Sefaz"] == cod_sefaz]

                    for cod_rel in df_filtrado["Código de Relatório"].unique():
                        sub_v1 = df_v1_sef[df_v1_sef["Código de Relatório"] == cod_rel]
                        sub_v3 = df_v3_sef[df_v3_sef["Código de Relatório"] == cod_rel]

                        if not sub_v1.empty and not sub_v3.empty:
                            for _, r_v1 in sub_v1.iterrows():
                                val_liq_colab = r_v1["Valor Líquido"]
                                rec_v1 = r_v1["Recibo"]

                                sub_v3_work = sub_v3.copy()
                                sub_v3_work["diff_prov"] = (sub_v3_work["Valor Provento"] - val_liq_colab).abs()
                                best_match_idx = sub_v3_work["diff_prov"].idxmin()
                                r_v3 = sub_v3_work.loc[best_match_idx]

                                val_prov_orc = r_v3["Valor Provento"]
                                desc_orc = r_v3["Desconto Orçamentário"]
                                rec_v3 = r_v3["Recibo"]
                                
                                liquido_orc_esperado = val_prov_orc - desc_orc
                                diff_rec = round(val_liq_colab - liquido_orc_esperado, 2)

                                if abs(diff_rec) > 0.01:
                                    recibos_problematicos.append(
                                        {
                                            "Empresa": empresa_g,
                                            "Código Sefaz": cod_sefaz,
                                            "Código de Relatório": cod_rel,
                                            "Recibo Colaborador": rec_v1,
                                            "Recibo Orçamentário": rec_v3,
                                            "Líquido Colaborador (R$)": formatar_moeda_br(val_liq_colab),
                                            "Provento Orçamentário (R$)": formatar_moeda_br(val_prov_orc),
                                            "Desc. Orçamentário (R$)": formatar_moeda_br(desc_orc),
                                            "Diferença (R$)": formatar_moeda_br(diff_rec),
                                        }
                                    )

        if recibos_problematicos:
            df_rec_prob = pd.DataFrame(recibos_problematicos).drop_duplicates()
            st.markdown("Foram isolados com precisão os pares de recibos que apresentam descompasso interno de valores:")
            
            st.dataframe(
                df_rec_prob,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Recibo Colaborador": st.column_config.NumberColumn("Recibo Colaborador", format="%d"),
                    "Recibo Orçamentário": st.column_config.NumberColumn("Recibo Orçamentário", format="%d"),
                },
            )
            
            lista_colab = sorted(df_rec_prob["Recibo Colaborador"].unique())
            lista_orc = sorted(df_rec_prob["Recibo Orçamentário"].unique())
            str_colab = ", ".join(map(str, lista_colab))
            str_orc = ", ".join(map(str, lista_orc))
            sugestao_recibos = ", ".join(map(str, sorted(set(lista_colab + lista_orc))))

            st.markdown(
                f"💡 Recibos afetados para copiar e auditar no painel abaixo: "
                f"<span style='color: #ff4b4b; font-weight: bold; font-size: 1.1rem;'>{str_colab}</span>, "
                f"<span style='color: #ff4b4b; font-weight: bold; font-size: 1.1rem;'>{str_orc}</span>",
                unsafe_allow_html=True
            )
        else:
            st.success("Nenhum par de recibos com divergência individual encontrado para os filtros aplicados!")

    # --- MÓDULO DE INSPEÇÃO / AUDITORIA DE RECIBOS ESPECÍFICOS ---
    with st.expander("🔎 Auditoria de Recibos Específicos (Payload JSON)", expanded=False):
        st.markdown("Digite os números dos recibos que deseja inspecionar detalhadamente para comparar o conteúdo dos payloads:")
        
        val_padrao = sugestao_recibos if 'sugestao_recibos' in locals() and sugestao_recibos else "8304, 5220"
        recibos_input = st.text_input("Recibos (separados por vírgula):", value=val_padrao)
        
        if st.button("Carregar Detalhes dos Recibos"):
            try:
                lista_rec = [int(r.strip()) for r in recibos_input.split(",") if r.strip().isdigit()]
                if lista_rec:
                    query_insp = f"""
                        SELECT 
                            sei.id_siafe_evento_integracao,
                            sei.recibo AS RECIBO,
                            sei.IND_TIPO_REQUISICAO,
                            sei.status_vobys,
                            sei.tipo_arquivo,
                            seip.json AS payload_blob
                        FROM sw_publico.SIAFE_EVENTO_INTEGRACAO sei
                        JOIN SW_PUBLICO.Siafe_Evento_Integ_Payload seip 
                            ON seip.id_siafe_evento_integracao = sei.id_siafe_evento_integracao
                        WHERE sei.ANO = :ano
                          AND sei.MES = :mes
                          AND sei.RECIBO IN ({','.join(map(str, lista_rec))})
                    """
                    df_insp = pd.read_sql(query_insp, conn, params={"ano": ano, "mes": mes})
                    if not df_insp.empty:
                        for _, row_insp in df_insp.iterrows():
                            row_dict = {str(k).lower(): v for k, v in row_insp.items()}
                            rec_num = row_dict.get("recibo")
                            tp_req = row_dict.get("ind_tipo_requisicao")
                            id_int = row_dict.get("id_siafe_evento_integracao")
                            blob = row_dict.get("payload_blob")
                            
                            json_texto = extrair_texto_payload(blob)
                            
                            st.markdown(f"**Recibo: `{rec_num}` | Tipo Req: `{tp_req}` | ID Int: `{id_int}`**")
                            if json_texto:
                                try:
                                    dados_json = json.loads(json_texto)
                                    st.json(dados_json)
                                except Exception:
                                    st.text(json_texto)
                            else:
                                st.warning("Payload vazio ou inválido.")
                            st.divider()
                    else:
                        st.info("Nenhum registro encontrado para os recibos informados no período selecionado.")
            except Exception as e:
                st.error(f"Erro ao consultar recibos: {e}")

