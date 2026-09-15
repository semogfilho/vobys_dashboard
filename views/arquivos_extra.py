# -*- coding: utf-8 -*-
import io
import json
import streamlit as st
import pandas as pd
import oracledb

# Importação da query específica do EMGERPI
from queries import get_query_json_patronal_emgerpi

# --- FUNÇÕES AUXILIARES DE CONVERSÃO E MONTAGEM ---

def construir_payload_json(df, mes, ano, cod_unidade, cod_relatorio):
    """
    Constrói a estrutura JSON genérica para as patronais SEDUC e FUNPREV.
    """
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

    return json.dumps(payload, indent=4, ensure_ascii=False).encode('utf-8')

def converter_para_csv(df):
    return df.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')

def converter_para_json_padrao(df):
    return df.to_json(orient="records", force_ascii=False, indent=2).encode('utf-8')

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
        
        json_str = str(json_res)
        
        try:
            return pd.read_json(io.StringIO(json_str))
        except Exception:
            dados = json.loads(json_str)
            return pd.json_normalize(dados)
            
    return pd.DataFrame()

# --- BLOCOS DE INTERFACE ---

def render_bloco_processamento(conn, titulo, id_chave, sql, mes, ano, cod_unidade=None, cod_relatorio=None):
    st.subheader(titulo)
    
    col_gerar, col_json, col_csv, col_enviar = st.columns([1.2, 1.2, 1.2, 1.2])
    data_key = f"df_extra_{id_chave}_{ano}_{mes}"

    if col_gerar.button(f"⚙️ Gerar Arquivo", key=f"btn_gerar_{id_chave}"):
        try:
            with st.spinner(f"Gerando dados para {titulo}..."):
                if id_chave == "emgerpi":
                    df = executar_query_emgerpi(conn, ano, mes)
                elif sql:
                    df = executar_query(conn, sql, {"mes": mes, "ano": ano})
                else:
                    df = pd.DataFrame()
                st.session_state[data_key] = df
        except Exception as e:
            st.error(f"Erro ao consultar banco de dados: {str(e)}")
            st.session_state[data_key] = None

    df_gerado = st.session_state.get(data_key)

    if df_gerado is not None:
        if not df_gerado.empty:
            # Definição do formato JSON e do nome padronizado do arquivo
            if cod_unidade and cod_relatorio:
                dados_json = construir_payload_json(df_gerado, mes, ano, cod_unidade, cod_relatorio)
                nome_json = f"FP_{cod_unidade}_9_{ano}{mes:02d}_001_{cod_relatorio}.json"
            else:
                dados_json = converter_para_json_padrao(df_gerado)
                nome_json = f"{id_chave}_{mes:02d}_{ano}.json"

            # Botão JSON
            col_json.download_button(
                label="📄 Baixar JSON",
                data=dados_json,
                file_name=nome_json,
                mime="application/json",
                key=f"btn_json_{id_chave}"
            )

            # Botão CSV
            col_csv.download_button(
                label="📊 Baixar CSV",
                data=converter_para_csv(df_gerado),
                file_name=f"{id_chave}_{mes:02d}_{ano}.csv",
                mime="text/csv",
                key=f"btn_csv_{id_chave}"
            )

            # Botão Enviar
            if col_enviar.button(f"🚀 Enviar Arquivo", key=f"btn_enviar_{id_chave}"):
                with st.spinner("Transmitindo arquivo..."):
                    st.success(f"✅ Arquivo ({id_chave.upper()}) transmitido com sucesso!")

            st.dataframe(df_gerado, use_container_width=True)
        else:
            st.warning("⚠️ Nenhum registro encontrado para a competência selecionada.")


def render(conn, ano, mes, meses_lista):
    st.title("📁 Gerador e Transmissor de Arquivos Extras")
    mes_nome = meses_lista.get(mes, str(mes))
    st.caption(f"**Competência Selecionada:** {mes_nome}/{ano}")
    st.divider()

    # --- 1. PATRONAL EMGERPI ---
    render_bloco_processamento(
        conn=conn,
        titulo="1. PATRONAL EMGERPI",
        id_chave="emgerpi",
        sql=None,
        mes=mes,
        ano=ano
    )

    st.divider()

    # --- 2. PATRONAL EXTRA SEDUC ---
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

    # --- 3. PATRONAL FUNPREV ---
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

    # --- 4. PATRONAL SEDUC 011 ---
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

    # --- 5. PATRONAL SEDUC 914 ---
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

