# -*- coding: utf-8 -*-
import json
import pandas as pd
import streamlit as st

# Mapeamento oficial de status VOBYS
STATUS_MAP = {
    "P": "PENDENTE",
    "T": "TRANSMITIDO",
    "A": "ABERTO",
    "F": "FECHADO",
    "I": "INCONSISTENCIA DE CADASTRO",
    "O": "OUTRAS INCONSISTENCIAS",
    "E": "ERRO",
}


def extrair_texto_payload(blob_data):
    """Extrai a string JSON do BLOB/CLOB lidando com buffers e delimitadores."""
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


def carregar_dados_patronais(conn, ano, mes):
    """Consulta os registros patronais (IND_TIPO_REQUISICAO = 'V4') buscando o JSON

    na tabela Siafe_Evento_Integ_Payload e a sigla na tabela de empresa.
    """
    query = """
        SELECT 
            sei.id_siafe_evento_integracao,
            sei.data_cadastro,
            sei.mes,
            sei.ano,
            sei.status_vobys,
            sei.recibo,
            sei.codigo_sefaz,
            sei.tipo_arquivo,
            sei.chave_folha,
            e.sigla AS empresa_sigla,
            seip.json AS payload_blob
        FROM sw_publico.SIAFE_EVENTO_INTEGRACAO sei
        INNER JOIN SW_PUBLICO.Siafe_Evento_Integ_Payload seip 
            ON seip.id_siafe_evento_integracao = sei.id_siafe_evento_integracao
        LEFT JOIN sw_publico.empresa e ON e.id_empresa = sei.id_empresa
        WHERE sei.IND_TIPO_REQUISICAO = 'V4'
          AND sei.ANO = :ano
          AND sei.MES = :mes
        ORDER BY sei.id_siafe_evento_integracao DESC
    """
    try:
        df_raw = pd.read_sql(query, conn, params={"ano": ano, "mes": mes})
    except Exception as e:
        st.error(f"Erro ao consultar dados no banco: {e}")
        return pd.DataFrame()

    if df_raw.empty:
        return pd.DataFrame()

    # Garantir nomes das colunas em minúsculo
    df_raw.columns = [c.lower() for c in df_raw.columns]

    registros = []
    for _, row in df_raw.iterrows():
        blob_data = row.get("payload_blob")
        json_str = extrair_texto_payload(blob_data)

        total_desconto = 0.0
        cod_sefaz_json = None
        tp_arquivo_json = None
        cod_relatorio_json = None

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
                            val = p.get("valorDesconto", 0.0)
                            if val is not None:
                                total_desconto += float(val)
            except Exception:
                pass

        id_reg = row.get("id_siafe_evento_integracao")
        dt_cad = row.get("data_cadastro")
        empresa = row.get("empresa_sigla") or cod_sefaz_json or "-"
        recibo = row.get("recibo") or "-"
        cod_sefaz = row.get("codigo_sefaz") or cod_sefaz_json or "-"
        tp_arquivo = row.get("tipo_arquivo") or tp_arquivo_json or "-"
        chave_folha = row.get("chave_folha") or "-"

        st_raw = str(row.get("status_vobys") or "").upper()
        status_desc = STATUS_MAP.get(st_raw, st_raw if st_raw else "ABERTO")

        registros.append(
            {
                "Id": id_reg,
                "Data Cadastro": dt_cad,
                "Empresa": empresa,
                "Mês": row.get("mes") or mes,
                "Ano": row.get("ano") or ano,
                "Status": status_desc,
                "Recibo": recibo,
                "Código Sefaz": cod_sefaz,
                "Tipo de Arquivo": tp_arquivo,
                "Código de Relatório": cod_relatorio_json or "-",
                "Chave Folha": chave_folha,
                "Total Desconto": total_desconto,
            }
        )

    return pd.DataFrame(registros)


def render(conn, ano, mes, meses_lista):
    st.title(f"📊 Totalização de Arquivos Patronais ({meses_lista[mes]}/{ano})")

    with st.spinner("Carregando e processando arquivos patronais..."):
        df_patronal = carregar_dados_patronais(conn, ano, mes)

    if df_patronal.empty:
        st.warning("Nenhum arquivo Patronal encontrado para o período.")
        return

    opcoes_agrupamento = [
        "Empresa",
        "Código de Relatório",
        "Código Sefaz",
        "Tipo de Arquivo",
        "Mês",
        "Ano",
        "Status",
        "Recibo",
    ]

    st.markdown("### 🔍 Agrupamento Dinâmico")
    campos_agrupamento = st.multiselect(
        "Selecione os campos para agrupar e totalizar os valores:",
        options=opcoes_agrupamento,
        default=["Empresa", "Código de Relatório"],
        help="Marque os campos para agrupar e calcular a quantidade de arquivos e o somatório do valorDesconto",
    )

    st.divider()

    col1, col2 = st.columns(2)
    col1.metric("Total de Arquivos", len(df_patronal))

    soma_total = df_patronal["Total Desconto"].sum()
    soma_fmt = (
        f"R$ {soma_total:,.2f}".replace(",", "v")
        .replace(".", ",")
        .replace("v", ".")
    )
    col2.metric("Somatório Geral (R$)", soma_fmt)

    st.divider()

    if campos_agrupamento:
        df_resumo = (
            df_patronal.groupby(campos_agrupamento, as_index=False)
            .agg(
                Qtd_Arquivos=("Id", "count"),
                Total_Valor_Desconto=("Total Desconto", "sum"),
            )
            .sort_values(by="Total_Valor_Desconto", ascending=False)
        )

        st.caption(
            f"Exibindo resumo agrupado por: **{', '.join(campos_agrupamento)}**"
        )
        st.dataframe(
            df_resumo,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Total_Valor_Desconto": st.column_config.NumberColumn(
                    "Total valorDesconto (R$)", format="R$ %.2f"
                ),
                "Qtd_Arquivos": st.column_config.NumberColumn(
                    "Qtd. Arquivos", format="%d"
                ),
            },
        )
    else:
        st.info(
            "Nenhum filtro de agrupamento selecionado. Exibindo a listagem detalhada de registros:"
        )
        st.dataframe(
            df_patronal,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Total Desconto": st.column_config.NumberColumn(
                    "valorDesconto Total (R$)", format="R$ %.2f"
                )
            },
        )

