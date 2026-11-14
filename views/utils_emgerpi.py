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
    sql_json = get_query_json_patronal_emgerpi(ano, mes, codigo_externo)
    try:
        df_res = executar_query_func(conn, sql_json, {"ano": ano, "mes": mes, "codigo_externo": codigo_externo})
        if df_res.empty:
            return None
        
        resultados = []
        # Espera-se: Coluna 0 = ID, Coluna 1 = Status (opcional), Coluna Final = JSON
        col_id = df_res.columns[0]
        col_status = df_res.columns[1] if df_res.shape[1] > 2 else None
        col_json = df_res.columns[-1] # Sempre a última coluna para garantir flexibilidade
        
        for _, row in df_res.iterrows():
            val_id = row[col_id]
            val_status = row[col_status] if col_status and col_status in df_res.columns else "N/D"
            val_json = row[col_json]
            
            if val_json is not None:
                resultados.append({
                    "id_origem": str(val_id),
                    "status_vobys": str(val_status),
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
                val_status = row[1] if len(row) > 2 else "N/D"
                val_json = row[-1] if len(row) > 1 else row[0]
                
                if val_json is not None:
                    resultados.append({
                        "id_origem": str(val_id),
                        "status_vobys": str(val_status),
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
        target_code = str(codigo_externo).strip().zfill(3)
        todos_pagamentos = []
        lote_referencia = None

        for item in json_retorno:
            id_origem = str(item.get("id_origem", "N/D"))
            status_origem = str(item.get("status_vobys", "N/D"))
            conteudo = item.get("json_content")

            if not conteudo:
                continue

            if isinstance(conteudo, bytes):
                conteudo = conteudo.decode('utf-8', errors='ignore')

            obj = json.loads(conteudo) if isinstance(conteudo, str) else conteudo
            lotes_lista = obj if isinstance(obj, list) else [obj]

            for lote in lotes_lista:
                if isinstance(lote, dict):
                    raw_ext = lote.get("codigoExterno", "001")
                    ext_code = str(raw_ext).strip().zfill(3)
                    
                    if ext_code == target_code:
                        if lote_referencia is None:
                            lote_referencia = lote

                        pagamentos = lote.get("pagamentos", [])
                        for pag in pagamentos:
                            if isinstance(pag, dict):
                                pag_copia = dict(pag)
                                pag_copia['idSiafeEvento'] = id_origem
                                pag_copia['status'] = status_origem
                                pag_copia['codigoExterno'] = target_code
                                todos_pagamentos.append(pag_copia)

        if lote_referencia:
            lote_limpo = json.loads(json.dumps(lote_referencia))
            lote_limpo.pop("_id_arquivo_origem", None)
            lote_limpo.pop("__id_origem_temp", None)
            
            # Define 120 como unidade padrão no cabeçalho da EMGERPI
            lote_limpo["codigoUnidadeSistemaExterno"] = "120"
            lote_limpo["codigoExterno"] = target_code
            
            lote_limpo["pagamentos"] = []
            for p in todos_pagamentos:
                # Remove colunas auxiliares internas antes de serializar o JSON final de envio
                p_limpo = {k: v for k, v in p.items() if k not in ['idSiafeEvento', 'status', 'codigoExterno']}
                lote_limpo["pagamentos"].append(p_limpo)

            json_str = json.dumps(lote_limpo, ensure_ascii=False, indent=2)
            df = pd.DataFrame(todos_pagamentos)
            
            if not df.empty:
                # Organiza as colunas principais no início da tabela visualizada
                cols_principais = ['idSiafeEvento', 'status', 'codigoExterno']
                outras_cols = [c for c in df.columns if c not in cols_principais]
                df = df[cols_principais + outras_cols]

            return json_str, df
    except Exception as e:
        st.error(f"Erro ao processar JSON EMGERPI: {str(e)}")
        pass
    
    return None, pd.DataFrame()

