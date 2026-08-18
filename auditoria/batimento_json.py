import pandas as pd
import json

#def limpar_codigo(codigo):
#    """Remove hífens e caracteres não numéricos de códigos institucionais."""
#    return "".join(filter(str.isdigit, str(codigo)))

import re
def limpar_codigo(codigo):
    """Remove hífens e caracteres não numéricos, preservando o 'X'."""
    # Converte para string, garante letras maiúsculas e remove tudo que não for número ou X
    return re.sub(r'[^0-9X]', '', str(codigo).upper())

def limpar_cpf(cpf):
    """Padroniza CPFs removendo caracteres não numéricos."""
    return "".join(filter(str.isdigit, str(cpf)))

# No seu arquivo onde monta a query ou chama o banco:
def obter_data_referencia(ano, mes):
    if mes == 13:
        # Define o mês 13 como dezembro para fins de cálculo de vigência
        return f"{ano}-12-31" 
    return f"{ano}-{int(mes):02d}-01"


def carregar_dados_folha_oficial(conn, schema, chave, ano, mes):
    """Busca dados da folha no banco de dados com parâmetros nomeados."""
    
    # 1. Definir a data de referência
    referencia = obter_data_referencia(ano, mes)

    # 2. Query estruturada com parâmetros nomeados (:nome_parametro)
    query = f"""
    WITH Pessoas_Unificadas AS (
        -- Servidores
        SELECT 
            p.id_pessoa, p.nome, 
            COALESCE(NULLIF(ff.matr_dependente, '0'), ff.cod_institucional) AS cod_inst
        FROM {schema}.folha_func ff
        INNER JOIN {schema}.folha f ON f.id_folha = ff.id_folha
        INNER JOIN SW_PUBLICO.pessoa p ON p.id_pessoa = COALESCE(NULLIF(ff.id_pessoa_dependente, 0), ff.id_pessoa_funcionario)
        WHERE f.chave_folha = :chave AND ff.ind_remuneracao = 'S'
        
        UNION ALL
        
        -- Estagiários
        SELECT 
            p.id_pessoa, p.nome, 
            pv.cod_institucional AS cod_inst
        FROM {schema}.Estagiario_Pagamento ep
        INNER JOIN {schema}.estag_folha f ON f.id_folha = ep.id_folha
        INNER JOIN {schema}.ESTAGIARIO e ON e.id_estagiario = ep.id_estagiario
        INNER JOIN {schema}.PESSOA_VINCULO pv ON pv.id_pessoa_vinculo = e.id_pessoa_vinculo
        INNER JOIN SW_PUBLICO.pessoa p ON p.id_pessoa = pv.id_pessoa
        WHERE f.mascara = :chave
    ),
    CPFs_Vigentes AS (
        -- Sua lógica de CPF aqui...
        SELECT id_pessoa, CPF_PESSOA FROM (
            SELECT id_pessoa, CPF_PESSOA, ROW_NUMBER() OVER (PARTITION BY id_pessoa ORDER BY data_cadastro DESC) as rn
            FROM SW_PUBLICO.pessoa_doc_cpf
            WHERE (data_baixa IS NULL OR data_baixa >= LAST_DAY(TO_DATE(:data_referencia, 'YYYY-MM-DD')))
        ) WHERE rn = 1
    )
    SELECT 
        doc.CPF_PESSOA,
        pu.cod_inst AS cod_institucional,
        pu.nome
    FROM Pessoas_Unificadas pu
    LEFT JOIN CPFs_Vigentes doc ON doc.id_pessoa = pu.id_pessoa
    """

    # 3. Dicionário de parâmetros mapeando os nomes na query
    params = {
        "data_referencia": referencia,
        "chave": chave
    }
    
# EM VEZ DE pd.read_sql, FAÇA ISSO:
# Adicione isso logo antes de cursor.execute(query, params)
    print(f"Debug - Chave: {chave}, Data Ref: {referencia}")
    cursor = conn.cursor()
    cursor.execute(query, params)
    
    # Busca nomes das colunas
    colunas = [col[0] for col in cursor.description]
    # Busca linhas
    linhas = cursor.fetchall()
    
    cursor.close()
    
    # CRIAÇÃO EXPLÍCITA DO DATAFRAME (Onde o erro deve estar)
    # Se isso der erro, o problema é que você nomeou uma variável como 'Data'
    df = pd.DataFrame(linhas, columns=colunas) 
    
    return df

def Xbuscar_saldos_pendentes_por_matricula(conn, schema, chave, lista_matriculas):
    lista_str = ", ".join([f"'{m}'" for m in lista_matriculas])
    
    # O SQL deve retornar a chave limpa para o merge funcionar
    query = f"""
    SELECT 
        ff.cod_institucional AS COD_INSTITUCIONAL, 
        doc.CPF_PESSOA AS CPF_BANCO,
        frr.valor_calculado AS SALDO_LIQUIDO
    FROM {schema}.folha_func ff
    INNER JOIN {schema}.folha f ON f.id_folha = ff.id_folha
    INNER JOIN SW_PUBLICO.pessoa_doc_cpf doc ON doc.id_pessoa = ff.id_pessoa_funcionario
    INNER JOIN {schema}.folha_func_rubrica frr ON frr.id_folha_funcionario = ff.id_folha_funcionario
    INNER JOIN SW_PUBLICO.FOLHA_RUBRICA efr ON efr.id_rubrica = frr.id_rubrica
    WHERE f.chave_folha = :chave
      AND efr.cod_rubrica = 999999
      AND ff.cod_institucional IN ({lista_str})
    """
    return pd.read_sql(query, conn, params={'chave': chave})

def Xbuscar_saldos_pendentes(conn, schema, chave, lista_cpfs):
    """Busca o saldo da rubrica 999999 validando contra a tabela de rubricas pública."""
    lista_str = ", ".join([f"'{c}'" for c in lista_cpfs])
    
    query = f"""
    SELECT 
        doc.CPF_PESSOA, 
        frr.valor_calculado as SALDO_LIQUIDO
    FROM {schema}.folha_func ff
    INNER JOIN {schema}.folha f ON f.id_folha = ff.id_folha
    INNER JOIN SW_PUBLICO.pessoa_doc_cpf doc ON doc.id_pessoa = ff.id_pessoa_funcionario
    INNER JOIN {schema}.folha_func_rubrica frr ON frr.id_folha_funcionario = ff.id_folha_funcionario
    INNER JOIN SW_PUBLICO.FOLHA_RUBRICA efr ON efr.id_rubrica = frr.id_rubrica
    WHERE f.chave_folha = :chave
      AND efr.cod_rubrica = 999999
      AND doc.CPF_PESSOA IN ({lista_str})
    """
    return pd.read_sql(query, conn, params={'chave': chave})


def buscar_json_da_tabela(conn, id_integracao):
    """Recupera o BLOB JSON da tabela de integração."""
    query = f"SELECT JSON FROM SW_PUBLICO.Siafe_Evento_Integ_Payload WHERE id_siafe_evento_integracao = {id_integracao}"
    cursor = conn.cursor()
    cursor.execute(query)
    res = cursor.fetchone()
    return res[0].read() if res and res[0] else None

def buscar_saldos_folha(conn, schema, lista_codigos, chave_folha, ano, mes):
    """
    Busca o saldo líquido unificando Servidores e Estagiários via UNION ALL.
    """
    # Formata a lista para o SQL IN
    formatacao_lista = ", ".join([f"'{c}'" for c in lista_codigos])
    
    query = f"""
    -- Parte 1: Servidores
    SELECT
        REPLACE(ff.cod_institucional, '-', '') AS cod_limpo,
        SUM(frr.valor_calculado) AS saldo_liquido
    FROM {schema}.folha_func ff
    INNER JOIN {schema}.folha f ON f.id_folha = ff.id_folha
    INNER JOIN {schema}.folha_func_rubrica frr ON frr.id_folha_funcionario = ff.id_folha_funcionario
    INNER JOIN SW_PUBLICO.FOLHA_RUBRICA efr ON efr.id_rubrica = frr.id_rubrica
    WHERE REPLACE(ff.cod_institucional, '-', '') IN ({formatacao_lista})
      AND f.chave_folha = :chave
      AND f.ano = :ano
      AND f.mes = :mes
      AND efr.cod_rubrica = 999999
    GROUP BY REPLACE(ff.cod_institucional, '-', '')
    
    UNION ALL
    
    -- Parte 2: Estagiários
    SELECT
        REPLACE(pv.cod_institucional, '-', '') AS cod_limpo,
        SUM(frr.valor) AS saldo_liquido
    FROM {schema}.Estagiario_Pagamento ff
    INNER JOIN {schema}.estag_folha f ON f.id_folha = ff.id_folha
    INNER JOIN {schema}.ESTAGIARIO e ON e.id_estagiario = ff.id_estagiario
    INNER JOIN {schema}.PESSOA_VINCULO pv ON pv.id_pessoa_vinculo = e.id_pessoa_vinculo
    INNER JOIN {schema}.estag_pagamento_rubrica frr ON frr.id_folha_estagiario = ff.id_folha_estagiario
    INNER JOIN SW_PUBLICO.FOLHA_RUBRICA efr ON efr.id_rubrica = frr.id_rubrica
    WHERE REPLACE(pv.cod_institucional, '-', '') IN ({formatacao_lista})
      AND f.mascara = :chave
      AND efr.cod_rubrica = 999999
    GROUP BY REPLACE(pv.cod_institucional, '-', '')
    """
    
    # Executa a query unificada
    return pd.read_sql(query, conn, params={'chave': chave_folha, 'ano': ano, 'mes': mes})


def processar_batimento_consolidado(conn, lista_ids, ano, mes): # <--- Adicione ano e mes
    """
    Consolida múltiplos payloads JSON e realiza o batimento contra a Folha,
    identificando dinamicamente o schema e a chave para cada ID selecionado.
    """
    try:
# 1. Busca os metadados
        placeholders = ', '.join([f':{i+1}' for i in range(len(lista_ids))])
        query_meta = f"""
            SELECT sei.id_siafe_evento_integracao, seip.json, sei.chave_folha, 
                   upper('sw_'||e.sigla) as schema_nome
            FROM sw_publico.SIAFE_EVENTO_INTEGRACAO sei
            INNER JOIN SW_PUBLICO.Siafe_Evento_Integ_Payload seip 
                ON seip.id_siafe_evento_integracao = sei.id_siafe_evento_integracao
            LEFT JOIN sw_publico.empresa e ON e.id_empresa = sei.id_empresa
            WHERE sei.id_siafe_evento_integracao IN ({placeholders})  
        """
        df_payloads = pd.read_sql(query_meta, conn, params=tuple(lista_ids))
        
        df_payloads.columns = [c.lower() for c in df_payloads.columns]
        # --------------------------------------------------

        if df_payloads.empty:
            return pd.DataFrame(), pd.DataFrame(), "Nenhum payload encontrado..."


        lista_dfs_json = []
        lista_dfs_folha = []

        # 2. Iteração dinâmica por schema e chave
        for _, row in df_payloads.iterrows():
            schema = row['schema_nome']
            chave = row['chave_folha']
            blob_data = row['json']

            # A. Carrega dados da folha específica do schema
            #df_folha = carregar_dados_folha_oficial(conn, schema, chave)
            df_folha = carregar_dados_folha_oficial(conn, schema, chave, ano, mes)
	    # --- ADIÇÃO DE METADADOS ---
            df_folha['ORGAO'] = schema  # Adiciona a coluna do órgão
            df_folha['CHAVE_FOLHA'] = chave  # Adiciona a coluna da chave
            # ---------------------------

            lista_dfs_folha.append(df_folha)

            # B. Processa o JSON (BLOB)
            if hasattr(blob_data, 'read'):
                content = blob_data.read()
            else:
                content = blob_data
            
            raw_str = content.decode('utf-8', errors='ignore') if isinstance(content, bytes) else str(content)
            
            start, end = raw_str.find('{'), raw_str.rfind('}')
            if start != -1 and end != -1:
                data = json.loads(raw_str[start:end + 1])
                if 'pagamentos' in data:
                    df_temp = pd.DataFrame(data['pagamentos'])
                    mapping = {
                        'codigoColaborador': 'codigoCredor',
                        'matriculaColaborador': 'matriculaCredor',
                        'nomeColaborador': 'nomeCredor'
                    }
                    df_temp.rename(columns=mapping, inplace=True)
                    lista_dfs_json.append(df_temp)

        # 3. Consolidação Final
# 3. Consolidação Final com verificação de segurança
        if not lista_dfs_folha:
            return pd.DataFrame(), pd.DataFrame(), "Nenhum dado de folha foi carregado."

        df_folha_total = pd.concat(lista_dfs_folha, ignore_index=True)
        df_json_total = pd.concat(lista_dfs_json, ignore_index=True)

        # 4. Padronização e Cruzamento
        df_folha_total['CPF_LIMPO'] = df_folha_total['CPF_PESSOA'].apply(limpar_cpf)
        df_json_total['CPF_LIMPO'] = df_json_total['codigoCredor'].apply(limpar_cpf)

        df_folha_total['COD_LIMPO'] = df_folha_total['COD_INSTITUCIONAL'].apply(limpar_codigo)
        df_json_total['MATRICULA_LIMPA'] = df_json_total['matriculaCredor'].apply(limpar_codigo)

        df_folha_total['chave'] = df_folha_total['CPF_LIMPO'] + "_" + df_folha_total['COD_LIMPO']
        df_json_total['chave'] = df_json_total['CPF_LIMPO'] + "_" + df_json_total['MATRICULA_LIMPA']

        dif_folha = df_folha_total[~df_folha_total['chave'].isin(df_json_total['chave'])]
        dif_json = df_json_total[~df_json_total['chave'].isin(df_folha_total['chave'])]


        # Após consolidar os DataFrames:
        total_folha = len(df_folha_total)
        total_json = len(df_json_total)

        # Cálculo das divergências
        dif_folha = df_folha_total[~df_folha_total['chave'].isin(df_json_total['chave'])]
        dif_json = df_json_total[~df_json_total['chave'].isin(df_folha_total['chave'])]

        # Cálculo da porcentagem (evitando divisão por zero)
        pct_dif_folha = (len(dif_folha) / total_folha * 100) if total_folha > 0 else 0
        pct_dif_json = (len(dif_json) / total_json * 100) if total_json > 0 else 0

# Retorna: dif_folha, dif_json, pct, pct, erro, df_folha_total, df_json_total
        return dif_folha, dif_json, pct_dif_folha, pct_dif_json, None, df_folha_total, df_json_total

    except Exception as e:
        # Retorna DataFrames vazios e None para os objetos totais para evitar erro de desempacotamento
        return pd.DataFrame(), pd.DataFrame(), 0, 0, f"Erro crítico no processamento: {str(e)}", pd.DataFrame(), pd.DataFrame()

