import pandas as pd
import json

def limpar_codigo(codigo):
    """Remove hífens e caracteres não numéricos de códigos institucionais."""
    return "".join(filter(str.isdigit, str(codigo)))

def limpar_cpf(cpf):
    """Padroniza CPFs removendo caracteres não numéricos."""
    return "".join(filter(str.isdigit, str(cpf)))

def carregar_dados_folha_oficial(conn, chave):
    """Busca dados da folha no banco de dados."""
    query = f"""
    SELECT doc.CPF_PESSOA, ff.COD_INSTITUCIONAL, p.NOME
    FROM SW_SSPPI.folha_func ff
    INNER JOIN SW_SSPPI.folha f ON f.id_folha = ff.id_folha
    INNER JOIN SW_PUBLICO.pessoa p ON p.id_pessoa = ff.id_pessoa_funcionario
    LEFT JOIN SW_PUBLICO.pessoa_doc_cpf doc ON doc.id_pessoa = ff.id_pessoa_funcionario
    WHERE f.chave_folha = '{chave}'
    """
    return pd.read_sql(query, conn)

def buscar_json_da_tabela(conn, id_integracao):
    """Recupera o BLOB JSON da tabela de integração."""
    query = f"SELECT JSON FROM SW_PUBLICO.Siafe_Evento_Integ_Payload WHERE id_siafe_evento_integracao = {id_integracao}"
    cursor = conn.cursor()
    cursor.execute(query)
    res = cursor.fetchone()
    return res[0].read() if res and res[0] else None

def realizar_batimento(conn, chave, id_integracao):
    """
    Executa o batimento entre Folha e JSON SEFAZ com mapeamento dinâmico.
    """
    try:
        # 1. Extração
        df_folha = carregar_dados_folha_oficial(conn, chave)
        blob_data = buscar_json_da_tabela(conn, id_integracao)

        if df_folha.empty:
            return pd.DataFrame(), pd.DataFrame(), f"Nenhum dado encontrado para a chave {chave}."
        if blob_data is None:
            return pd.DataFrame(), pd.DataFrame(), f"Payload JSON vazio para o ID {id_integracao}."

        # 2. Extração resiliente
        raw_str = blob_data.decode('utf-8', errors='ignore')
        start_idx = raw_str.find('{')
        end_idx = raw_str.rfind('}')
        
        if start_idx == -1 or end_idx == -1:
            return pd.DataFrame(), pd.DataFrame(), "Estrutura JSON não encontrada no blob."

        json_str = raw_str[start_idx:end_idx + 1]
        data = json.loads(json_str)

        if 'pagamentos' not in data:
            return pd.DataFrame(), pd.DataFrame(), "JSON válido, mas chave 'pagamentos' ausente."

        # 3. Processamento Dinâmico (Mapeamento de colunas)
        df_json = pd.DataFrame(data['pagamentos'])
        
        # Mapeamento: DE (nome no JSON) -> PARA (nome padrão que o batimento usa)
        mapping = {
            'codigoColaborador': 'codigoCredor',
            'matriculaColaborador': 'matriculaCredor',
            'nomeColaborador': 'nomeCredor'
        }
        df_json.rename(columns=mapping, inplace=True)

        # 4. Padronização e Batimento
        df_folha['CPF_LIMPO'] = df_folha['CPF_PESSOA'].apply(limpar_cpf)
        df_json['CPF_LIMPO'] = df_json['codigoCredor'].apply(limpar_cpf)

        df_folha['COD_LIMPO'] = df_folha['COD_INSTITUCIONAL'].apply(limpar_codigo)
        df_json['MATRICULA_LIMPA'] = df_json['matriculaCredor'].apply(limpar_codigo)

        df_folha['chave'] = df_folha['CPF_LIMPO'] + "_" + df_folha['COD_LIMPO']
        df_json['chave'] = df_json['CPF_LIMPO'] + "_" + df_json['MATRICULA_LIMPA']

        # 5. Ordenação (Segura)
        ordem_colunas = ['nomeCredor', 'matriculaCredor', 'codigoCredor', 'CPF_LIMPO', 'MATRICULA_LIMPA', 'chave', 'valorBruto', 'valorLiquido', 'dataPagamento']
        df_json = df_json[[col for col in ordem_colunas if col in df_json.columns]]

        # 6. Cruzamento
        dif_folha = df_folha[~df_folha['chave'].isin(df_json['chave'])]
        dif_json = df_json[~df_json['chave'].isin(df_folha['chave'])]

        return dif_folha, dif_json, None

    except Exception as e:
        return pd.DataFrame(), pd.DataFrame(), f"Erro crítico: {str(e)}"

