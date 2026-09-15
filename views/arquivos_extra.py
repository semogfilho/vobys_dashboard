# -*- coding: utf-8 -*-
import io
import json
import requests
import streamlit as st
import pandas as pd
import oracledb

# Importação da query específica do EMGERPI
from queries import get_query_json_patronal_emgerpi

# Token padrão extraído do script de transmissão
TOKEN_SEFAZ_PADRAO = "eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJBUEkgZGUgSW50ZWdyYcOnw6NvIExvZ3VzIiwic3ViIjoiMzQ3NzQ5MDQzNjgiLCJpYXQiOjE3ODk0ODUxMTQsImV4cCI6MTc4OTU3MTUxNH0.PtndHNrn5Ki_xYwZ4zh39x8WkdyvzowD_2z03lWHdbk"

# --- FUNÇÕES AUXILIARES DE CONVERSÃO E BANCO ---

def construir_payload_json(df, mes, ano, cod_unidade, cod_relatorio):
    if df is None or df.empty:
        return None

    pagamentos = []
    for _, row in df.iterrows():
        valor_desc = row['DESCONTOS']
        if isinstance(valor_desc, str):
            valor_desc = float(valor_desc.replace(',', '.'))
        else:
            valor_desc = float(valor_desc)

        pagamentos.append({
            "codigoSefaz": str(row.get('RUBRICA', '')),
            "regimePrevidenciario": str(row['TIPO_REGIME']),
            "codigoRubrica": str(row['RUBRICA']),
            "tipoVinculo": str(row['TIPO_VINCULO']),
            "valor": float(row.get('VANTAGENS', 0.0)),
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
    cursor.execute(query, params)
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

    if row and row[0]:
        json_res = row[0]
        if hasattr(json_res, 'read'):
            json_res = json_res.read()
        return str(json_res)
    return None

# --- INTEGRAÇÃO COM A API SEFAZ-PI ---

def transmitir_para_sefaz(payload_data, ano, token_jwt=None):
    if not token_jwt:
        token_jwt = st.session_state.get("token_sefaz") or st.secrets.get("TOKEN_SEFAZ", TOKEN_SEFAZ_PADRAO)

    url = f"https://tesouro.sefaz.pi.gov.br/siafe-api/folha-pagamento/contabilizacao-folha-pagamento/{ano}"
    
    headers = {
        "accept": "*/*",
        "Authorization": token_jwt.strip(),
        "Content-Type": "application/json"
    }

    if isinstance(payload_data, str):
        payload_json = json.loads(payload_data)
    else:
        payload_json = payload_data

    response = requests.post(url, headers=headers, json=payload_json, timeout=30)
    
    if response.status_code in (200, 201):
        return response.json()
    else:
        try:
            err_data = response.json()
            err_msg = err_data.get("message") or err_data.get("observacao") or response.text
        except Exception:
            err_msg = response.text
        raise Exception(f"HTTP {response.status_code}: {err_msg}")

# --- BLOCO DE RENDERIZAÇÃO DA INTERFACE ---

def render_bloco_processamento(conn, titulo, id_chave, sql, mes, ano, cod_unidade=None, cod_relatorio=None):
    # Padronização exata do nome do arquivo (ex: FP_120_9_202609_001_93)
    if cod_unidade and cod_relatorio:
        nome_arquivo_base = f"FP_{cod_unidade}_9_{ano}{int(mes):02d}_001_{cod_relatorio}"
        titulo_exibicao = f"{titulo} - {nome_arquivo_base}"
    else:
        nome_arquivo_base = f"PATRONAL_{id_chave.upper()}_{ano}{int(mes):02d}"
        titulo_exibicao = titulo

    st.subheader(titulo_exibicao)
    
    col_gerar, col_json, col_csv, col_enviar = st.columns([1.2, 1.2, 1.2, 1.2])
    
    data_key = f"df_extra_{id_chave}_{ano}_{mes}"
    json_raw_key = f"json_raw_{id_chave}_{ano}_{mes}"
    retorno_key = f"retorno_envio_{id_chave}_{ano}_{mes}"

    # 1. Botão Gerar Arquivo / JSON
    if col_gerar.button(f"⚙️ Gerar Arquivo", key=f"btn_gerar_{id_chave}"):
        try:
            with st.spinner(f"Gerando dados para {titulo}..."):
                if id_chave == "emgerpi":
                    json_str = executar_query_emgerpi(conn, ano, mes)
                    if json_str:
                        st.session_state[json_raw_key] = json_str
                        dados = json.loads(json_str)
                        st.session_state[data_key] = pd.json_normalize(dados.get("pagamentos", dados))
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
        except Exception as e:
            st.error(f"Erro ao consultar banco de dados: {str(e)}")
            st.session_state[data_key] = None

    df_gerado = st.session_state.get(data_key)
    json_raw = st.session_state.get(json_raw_key)

    # 2. Exibição das Ações de Download e Transmissão
    if df_gerado is not None and not df_gerado.empty:
        # Download JSON
        if json_raw:
            col_json.download_button(
                label="📄 Baixar JSON",
                data=json_raw.encode('utf-8'),
                file_name=f"{nome_arquivo_base}.json",
                mime="application/json",
                key=f"btn_json_{id_chave}"
            )

        # Download CSV
        col_csv.download_button(
            label="📊 Baixar CSV",
            data=converter_para_csv(df_gerado),
            file_name=f"{nome_arquivo_base}.csv",
            mime="text/csv",
            key=f"btn_csv_{id_chave}"
        )

        # Botão Enviar para a SEFAZ
        if col_enviar.button(f"🚀 Enviar Arquivo", key=f"btn_enviar_{id_chave}", type="primary"):
            with st.spinner("Transmitindo lote para a SEFAZ..."):
                try:
                    payload_para_envio = json_raw if json_raw else df_gerado
                    res_api = transmitir_para_sefaz(payload_para_envio, ano)
                    st.session_state[retorno_key] = res_api
                    st.success("Transmissão efetuada com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Falha no envio: {str(e)}")

    # 3. Métricas de Retorno da SEFAZ
    resp_sefaz = st.session_state.get(retorno_key)
    if resp_sefaz:
        st.write("---")
        col_x, col_y, col_w, col_z = st.columns([1, 1, 1.4, 1])
        with col_x:
            st.metric("Enviados", resp_sefaz.get("qtdPagamentosRecebidos", 0))
        with col_y:
            st.metric("Recibo", resp_sefaz.get("codigo", "-"))
        with col_w:
            st.metric("Data/Hora", str(resp_sefaz.get("dataHoraCadastro", "-"))[:19].replace("T", " "))
        with col_z:
            st.metric("Status", resp_sefaz.get("observacao", "-"))

    if df_gerado is not None and not df_gerado.empty:
        with st.expander("🔍 Visualizar Prévia dos Dados", expanded=False):
            st.dataframe(df_gerado, use_container_width=True)


def render(conn, ano, mes, meses_lista):
    st.title("📁 Gerador e Transmissor de Arquivos Extras")
    mes_nome = meses_lista.get(mes, str(mes))
    st.caption(f"**Competência Selecionada:** {mes_nome}/{ano}")
    st.divider()

    # 1. PATRONAL EMGERPI (FP_120_9_202609_001_93)
    render_bloco_processamento(
        conn=conn,
        titulo="1. PATRONAL EMGERPI",
        id_chave="emgerpi",
        sql=None,
        mes=mes,
        ano=ano,
        cod_unidade="120",
        cod_relatorio="93"
    )

    st.divider()

    # 2. PATRONAL EXTRA SEDUC (FP_011_9_202609_001_99)
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
        cod_relatorio="99"
    )

    st.divider()

    # 3. PATRONAL FUNPREV (FP_924_9_202609_001_90)
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
        cod_relatorio="90"
    )

    st.divider()

    # 4. PATRONAL SEDUC 011 (FP_011_9_202609_001_90)
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
        cod_relatorio="90"
    )

    st.divider()

    # 5. PATRONAL SEDUC 914 (FP_914_9_202609_001_90)
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
        cod_relatorio="90"
    )

