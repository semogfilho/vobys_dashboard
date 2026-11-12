# -*- coding: utf-8 -*-
import json
import pandas as pd
import streamlit as st

try:
    from queries import get_query_json_patronal_emgerpi
except ImportError:
    def get_query_json_patronal_emgerpi(ano, mes, codigo_externo=None):
        return "SELECT json_data FROM dual"

def executar_query_emgerpi(conn, ano, mes, codigo_externo, executar_query_func):
    # Passa o codigo_externo para a query filtrar na origem
    sql_json = get_query_json_patronal_emgerpi(ano, mes, codigo_externo)
    try:
        df_res = executar_query_func(conn, sql_json, {"ano": ano, "mes": mes, "codigo_externo": codigo_externo})
        if df_res.empty:
            return None
        
        resultados = []
        col_id = df_res.columns[0]
        col_json = df_res.columns[1] if df_res.shape[1] > 1 else df_res.columns[0]
        
        for _, row in df_res.iterrows():
            val_id = row[col_id]
            val_json = row[col_json]
            if val_json is not None:
                resultados.append({
                    "id_origem": str(val_id),
                    "json_content": val_json
                })
        return resultados
    except Exception as e:
        try:
            cursor = conn.cursor()
            cursor.execute(sql_json)
            rows = cursor.fetchall()
            cursor.close()
            if not rows:
                return None
            
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
        except Exception as err:
            st.error(f"Erro ao executar query EMGERPI: {str(err)}")
            return None

def processar_dados_emgerpi(json_retorno, codigo_externo):
    if not json_retorno:
        return None, pd.DataFrame()
    
    try:
        lista_lotes = []
        
        for item in json_retorno:
            id_origem = item.get("id_origem", "N/D")
            conteudo = item.get("json_content")

            if not conteudo:
                continue

            if isinstance(conteudo, bytes):
                conteudo = conteudo.decode('utf-8', errors='ignore')

            obj = json.loads(conteudo) if isinstance(conteudo, str) else conteudo
            if isinstance(obj, list):
                for sub_obj in obj:
                    if isinstance(sub_obj, dict):
                        lista_lotes.append((id_origem, sub_obj))
            elif isinstance(obj, dict):
                lista_lotes.append((id_origem, obj))

        target_code = str(codigo_externo).strip().zfill(3)

        lote_filtrado = None
        id_origem_encontrado = "N/D"

        for id_orig, lote in lista_lotes:
            if isinstance(lote, dict):
                raw_ext = lote.get("codigoExterno", "001")
                ext_code = str(raw_ext).strip().zfill(3)
                if ext_code == target_code:
                    lote_filtrado = lote
                    id_origem_encontrado = id_orig
                    break

        if not lote_filtrado and len(lista_lotes) == 1:
            id_origem_encontrado, lote_filtrado = lista_lotes[0]

        if lote_filtrado:
            lote_limpo = json.loads(json.dumps(lote_filtrado))
            lote_limpo.pop("_id_arquivo_origem", None)
            lote_limpo.pop("__id_origem_temp", None)

            lote_limpo["codigoExterno"] = target_code
            json_str = json.dumps(lote_limpo, ensure_ascii=False, indent=2)
            
            pagamentos = lote_limpo.get("pagamentos", [])
            df = pd.json_normalize(pagamentos)
            
            if not df.empty:
                df['idSiafeEvento'] = id_origem_encontrado
                df['codigoExterno'] = target_code
                df['alvoSelecionado'] = target_code
                
                cols = ['idSiafeEvento', 'codigoExterno', 'alvoSelecionado'] + [c for c in df.columns if c not in ['idSiafeEvento', 'codigoExterno', 'alvoSelecionado']]
                df = df[cols]

            return json_str, df
    except Exception as e:
        st.error(f"Erro ao processar JSON: {str(e)}")
        pass
    
    return None, pd.DataFrame()

