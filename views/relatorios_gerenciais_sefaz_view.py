# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import datetime
from sefaz_client import requisitar_sefaz

# Configuração centralizada dos relatórios gerenciais conforme o Swagger oficial SIAFE-PI
RELATORIOS_CONFIG = {
    "contabilizacao": {
        "titulo": "1. Contabilização da Folha",
        "endpoint": "folha-pagamento/contabilizacao/{exercicio}",
        "metodo": "POST",
        "icone": "📊",
        "arquivo_csv": "contabilizacao_folha"
    },
    "pagamento": {
        "titulo": "2. Inconsistências - Pagamento e Créditos",
        "endpoint": "folha-pagamento/inconsistencia-pag/{exercicio}/{mes}",
        "metodo": "GET",
        "icone": "💳",
        "arquivo_csv": "inconsistencias_pagamento"
    },
    "controle": {
        "titulo": "3. Pagamentos de Colaboradores",
        "endpoint": "folha-pagamento/pagamento-colaborador/consulta/{exercicio}/1/100",
        "metodo": "POST",
        "icone": "✅",
        "arquivo_csv": "pagamentos_colaboradores"
    }
}


def _montar_payload_post(chave_relatorio, exercicio, mes, filtros):
    """Monta o payload JSON incluindo o exercício e demais parâmetros validados no Swagger."""
    codigo_ug_sistema = str(filtros.get("codigo_ug_sistema_externo", "002")).strip()
    
    payload = {
        "exercicio": int(exercicio),
        "mes": int(mes),
        "competencia": f"{int(mes):02d}/{exercicio}",
        "tipoFolha": int(filtros.get("tipo_folha", 1)),
        "codigoUGSistemaExterno": codigo_ug_sistema,
        "codigoExterno": str(filtros.get("codigo_externo", "001"))
    }

    if chave_relatorio == "contabilizacao":
        payload["codigoRelatorio"] = str(filtros.get("codigo_relatorio", "99"))
        payload["status"] = str(filtros.get("status", "Fechado"))
        payload["exibirDocumento"] = str(filtros.get("exibir_documento", "SIM"))
        payload["exibirInconsistencia"] = str(filtros.get("exibir_inconsistencia", "NAO"))
    elif chave_relatorio == "controle":
        payload["status"] = str(filtros.get("status", "Fechado"))

    return payload


def _consultar_endpoint_sefaz(chave_relatorio, config, exercicio, mes, filtros):
    metodo = config["metodo"]
    
    if metodo == "POST":
        if chave_relatorio == "controle":
            endpoint = f"folha-pagamento/pagamento-colaborador/consulta/{int(exercicio)}/1/100"
        else:
            endpoint = config["endpoint"].format(exercicio=int(exercicio))
            
        payload = _montar_payload_post(chave_relatorio, exercicio, mes, filtros)
        try:
            resultado = requisitar_sefaz(metodo="POST", endpoint=endpoint, payload=payload)
            return resultado
        except Exception as e:
            return {"erro": True, "mensagem": f"Erro na API (POST /{endpoint}): {str(e)}"}
    else:
        endpoint = config["endpoint"].format(exercicio=int(exercicio), mes=int(mes))
        try:
            resultado = requisitar_sefaz(metodo="GET", endpoint=endpoint)
            return resultado
        except Exception as e:
            return {"erro": True, "mensagem": f"Erro na API (GET /{endpoint}): {str(e)}"}


def _normalizar_dataframe(data):
    if not data:
        return pd.DataFrame()

    if isinstance(data, dict):
        for chave_lista in ("conteudo", "registros", "itens", "lista", "data"):
            if chave_lista in data and isinstance(data[chave_lista], list):
                data = data[chave_lista]
                break
        else:
            data = [data]

    df = pd.DataFrame(data)
    if df.empty:
        return df

    for col_aninhada, prefixo in [("itens", "item_"), ("documentos", "doc_"), ("inconsistencias", "inc_")]:
        if col_aninhada in df.columns:
            tem_dados = df[col_aninhada].apply(lambda x: isinstance(x, list) and len(x) > 0).any()
            if tem_dados:
                df_explode = df.explode(col_aninhada).reset_index(drop=True)
                itens_validos = df_explode[col_aninhada].apply(lambda x: x if isinstance(x, dict) else {})
                itens_norm = pd.json_normalize(itens_validos).add_prefix(prefixo)
                df = pd.concat([df_explode.drop(columns=[col_aninhada]), itens_norm], axis=1)
            else:
                df = df.drop(columns=[col_aninhada])

    return df


def _renderizar_aba_relatorio(chave_relatorio, config, exercicio, mes):
    with st.expander("ℹ️ Detalhes Técnicos da Rota (Swagger)", expanded=False):
        col1, col2 = st.columns(2)
        col1.caption(f"**Método / Rota:** `{config['metodo']} /{config['endpoint'].format(exercicio=exercicio, mes=mes, pagina=1, total_registros=100)}`")
        col2.caption(f"**Competência:** {mes:02d}/{exercicio}")

    c1, c2, c3 = st.columns([2, 1, 1])

    ug_sistema_externo = c1.text_input("Cód. UG Sistema (USE):", value="002", key=f"ug_sis_{chave_relatorio}")
    tipo_folha = c2.number_input("Tipo Folha:", min_value=1, max_value=99, value=1, step=1, key=f"tf_{chave_relatorio}")
    codigo_externo = c3.text_input("Cód. Externo:", value="001", key=f"ce_{chave_relatorio}")

    filtros = {
        "codigo_ug_sistema_externo": ug_sistema_externo,
        "tipo_folha": tipo_folha,
        "codigo_externo": codigo_externo,
        "status": "Fechado",
        "codigo_relatorio": "99",
        "exibir_documento": "SIM",
        "exibir_inconsistencia": "NAO"
    }

    if chave_relatorio == "contabilizacao":
        cc1, cc2, cc3 = st.columns(3)
        filtros["codigo_relatorio"] = cc1.text_input("Cód. Relatório:", value="99", key=f"cr_{chave_relatorio}")
        filtros["exibir_documento"] = cc2.selectbox("Exibir Documento:", ["SIM", "NAO"], key=f"ed_{chave_relatorio}")
        filtros["exibir_inconsistencia"] = cc3.selectbox("Exibir Inconsistência:", ["NAO", "SIM"], key=f"ei_{chave_relatorio}")

    session_key = f"dados_sefaz_{chave_relatorio}_{exercicio}_{mes}_{ug_sistema_externo}"

    if st.button(f"Consultar {config['titulo']}", key=f"btn_{chave_relatorio}", type="primary"):
        with st.spinner(f"Consultando SEFAZ para {mes:02d}/{exercicio} (USE: {ug_sistema_externo})..."):
            resultado = _consultar_endpoint_sefaz(chave_relatorio, config, exercicio, mes, filtros)
            st.session_state[session_key] = resultado

    data = st.session_state.get(session_key)
    if data is None:
        return

    if isinstance(data, dict) and data.get("erro"):
        st.error(f"⚠️ {data.get('mensagem', 'Erro desconhecido na API')}")
        return

    if isinstance(data, (list, dict)):
        df_final = _normalizar_dataframe(data)

        if df_final.empty:
            st.info("Nenhum registro retornado pela SEFAZ para os parâmetros informados.")
            with st.expander("🔍 Ver JSON bruto retornado pela API"):
                st.json(data)
            return

        col_info, col_dl = st.columns([3, 1])
        col_info.success(f"**{len(df_final)}** registro(s) obtido(s) com sucesso da SEFAZ.")

        csv_bytes = df_final.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")
        col_dl.download_button(
            label="📥 Exportar CSV",
            data=csv_bytes,
            file_name=f"{config['arquivo_csv']}_{exercicio}_{mes:02d}_use_{ug_sistema_externo}.csv",
            mime="text/csv",
            key=f"dl_{chave_relatorio}"
        )

        st.dataframe(df_final, use_container_width=True, hide_index=True)

        with st.expander("🔍 Ver JSON bruto retornado pela API"):
            st.json(data)
    else:
        st.error(f"⚠️ Retorno inesperado da API: {data}")


def renderizar_relatorios_gerenciais_sefaz(exercicio, mes):
    st.subheader(f"📑 Relatórios Gerenciais SIAFE ({mes:02d}/{exercicio})")
    st.caption(f"Última atualização da tela: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

    abas = st.tabs([
        f"{cfg['icone']} {cfg['titulo']}" for cfg in RELATORIOS_CONFIG.values()
    ])

    for aba, (chave, cfg) in zip(abas, RELATORIOS_CONFIG.items()):
        with aba:
            _renderizar_aba_relatorio(chave, cfg, exercicio, mes)


def render(conn, ano, mes, meses_lista=None, *args, **kwargs):
    renderizar_relatorios_gerenciais_sefaz(int(ano), int(mes))

