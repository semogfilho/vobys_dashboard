# auditoria/novos_dados_bancario.py
import streamlit as st
import unicodedata  # <--- ADICIONE ESTA LINHA NO TOPO
import pandas as pd
import re  # ADICIONE ESTA LINHA AQUI
import requests
import json

def buscar_dados_completos(conn, schema, cod_institucional):
    sql = f"""
        SELECT 
            doc.cpf_pessoa AS CPF, 
            phn.nome AS NOME, 
            p.data_nascimento AS DATANASCIMENTO,
            pis.PISPASEP AS NUMEROPISPASEPNIT, 
            upe.cod_unidade_federacao AS UF, 
            mpe.cod_municipio_ibge AS CODIGOMUNICIPIO, 
            pe.cep AS CEP,
            pe.logradouro || ', ' || pe.numero_endereco || 
            CASE 
                WHEN pe.complemento_endereco IS NOT NULL THEN ' - ' || pe.complemento_endereco 
                ELSE '' 
            END AS ENDERECO,
            pe.bairro_endereco AS BAIRRO,
            pe.ddd        ||pe.telefone_residencia  TELEFONE,
            pe.ddd_celular||pe.celular  TELEFONE2, 
            pe.ddd_celular||pe.celular AS CELULAR, 
            NULL AS FAX,
            p.email AS EMAIL,
            pbb.cod_banco AS CODIGOBANCO,
            pba.cod_agencia AS CODIGOAGENCIA,
            pb.conta_corrente AS NUMEROCONTA,
            0 AS FLGCONTAPOUPANCA,
            'ATIVO' AS STATUS,
            ff.cod_institucional AS IDFUNCIONAL
        FROM {schema}.folha_func ff
        INNER JOIN {schema}.folha f ON f.id_folha = ff.id_folha
        INNER JOIN SW_PUBLICO.pessoa p ON p.id_pessoa = ff.ID_PESSOA_FUNCIONARIO
        LEFT JOIN SW_PUBLICO.pessoa_historico_nomes phn ON phn.id_pessoa = p.id_pessoa AND phn.data_fim IS NULL
        LEFT JOIN SW_PUBLICO.pessoa_doc_cpf doc ON doc.id_pessoa = p.id_pessoa
        LEFT JOIN SW_PUBLICO.pessoa_endereco pe ON pe.id_pessoa = p.id_pessoa AND pe.data_fim IS NULL
        LEFT JOIN sw_publico.PESSOA_DOC_PISPASEP pis on  pis.id_pessoa=p.id_pessoa AND pis.data_baixa IS NULL
        LEFT JOIN SW_PUBLICO.RHB_CEP_UNIDADE_FEDERACAO upe ON upe.id_unidade_federacao = pe.id_unidade_federacao
        LEFT JOIN SW_PUBLICO.RHB_CEP_MUNICIPIO_IBGE mpe ON mpe.id_municipio = pe.id_municipio
        LEFT JOIN SW_PUBLICO.Pessoa_Banco pb ON pb.id_pessoa = p.id_pessoa AND pb.data_fim IS NULL
        LEFT JOIN SW_PUBLICO.RHB_BANCO_AGENCIA pba ON pba.id_agencia = pb.id_agencia
        LEFT JOIN SW_PUBLICO.RHB_BANCO pbb ON pbb.id_banco = pba.id_banco
        WHERE ff.cod_institucional = :cod
    """
    try:
        df = pd.read_sql(sql, conn, params={'cod': cod_institucional})
        if not df.empty:
            # Força o retorno de um dicionário limpo
            return df.iloc[0].to_dict()
        return None
    except Exception as e:
        print(f"Erro crítico no SQL: {e}") # Isso aparecerá no terminal do servidor
        return None

def remover_acentos(texto):
    """
    Remove acentos de uma string, mantendo a letra base.
    Ex: 'FÁTIMA' -> 'FATIMA'
    """
    if pd.isnull(texto): # Garante compatibilidade com Pandas/NULLs
        return None
    
    # Converte para string explicitamente e remove espaços extras
    texto_str = str(texto).strip()
    
    # Normaliza para decompor caracteres (ex: Á -> A + ´)
    # A forma 'NFKD' é a mais recomendada para essa decomposição.
    texto_normalizado = unicodedata.normalize('NFKD', texto_str)
    
    # Filtra mantendo apenas caracteres que NÃO são marcas de acentuação (non-spacing marks)
    texto_sem_acentos = "".join(
        [c for c in texto_normalizado if not unicodedata.combining(c)]
    )
    
    return texto_sem_acentos

def limpar_numeros(valor):
    if valor:
        return re.sub(r'\D', '', str(valor))
    return None

def montar_json_sefaz(row):
    return {
        "cpf": limpar_numeros(row['CPF']), # Alterado de dados para row
        "nome": remover_acentos(row['NOME']).upper() if pd.notnull(row['NOME']) else None,
        "dataNascimento": row['DATANASCIMENTO'].strftime('%Y-%m-%d') if pd.notnull(row['DATANASCIMENTO']) else None,
        "numeroPisPasepNit": row['NUMEROPISPASEPNIT'],
        "uf": row['UF'],
        "codigoMunicipio": row['CODIGOMUNICIPIO'],
        "cep": limpar_numeros(row['CEP']), # Alterado de dados para row
        "endereco": str(row['ENDERECO']).upper().strip() if pd.notnull(row['ENDERECO']) else None,
        "bairro": str(row['BAIRRO']).upper().strip() if pd.notnull(row['BAIRRO']) else None,
        "telefone": limpar_numeros(row['TELEFONE']), # Alterado de dados para row
        "telefone2": limpar_numeros(row['TELEFONE2']), # Alterado de dados para row
        "celular": limpar_numeros(row['CELULAR']), # Alterado de dados para row
        "fax": limpar_numeros(row['FAX']), # Alterado de dados para row
        "email": remover_acentos(row['EMAIL']).lower() if pd.notnull(row['EMAIL']) else None,
        "dadosBancarios": [{
            "codigoBanco": row['CODIGOBANCO'],
            "codigoAgencia": str(row['CODIGOAGENCIA']).split('-')[0],
            "numeroConta": str(row['NUMEROCONTA']).replace(' ', '').replace('.', '').replace('-', ''),
            "flgContaPoupanca": bool(row['FLGCONTAPOUPANCA'] == 1),
            "status": row['STATUS'],
            "idFuncional": str(row['IDFUNCIONAL']).strip().replace('-', '')
        }]
    }


def enviar_para_sefaz(payload):
    usuario = st.session_state.get("sefaz_cpf", st.secrets["sefaz"]["SIAFE_CPF"])
    senha = st.session_state.get("sefaz_pass", st.secrets["sefaz"]["SIAFE_SENHA"])
    BASE_URL = st.secrets["sefaz"]["BASE_URL"]
    URL_FINAL = f"{BASE_URL}/apoio-geral/pessoa-fisica/2026"
    # Se não houver, cai no secrets (fallback)
 
    try:
        session = requests.Session()
        session.verify = False

       # Ajuste aqui: chamando as credenciais corretamente do dicionário config
        payload_auth = {"usuario": usuario, "senha": senha}
        r_auth = session.post(f"{BASE_URL}/auth", json=payload_auth, timeout=10)
        r_auth.raise_for_status()

        token = r_auth.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})

        # 2. DEBUG (agora a sessão e os headers existem!)
        print("DEBUG: Headers enviados:", session.headers)
        print("DEBUG: Payload enviado:", payload)

        # 3. Envio dos dados
        response = session.post(URL_FINAL, json=payload, timeout=10)
        # Retorna sucesso se o código for 200 ou 201 (criado)
        sucesso = response.status_code in [200, 201]
        
        return sucesso, json.dumps(payload), response.text

    except Exception as e:
        return False, None, str(e)


def obter_schemas_dinamicos(conn):
    # 1. Debug de verificação de conexão (Loga no journal/terminal)
    if conn is None:
        print("DEBUG: Conexão (conn) é None!")
        return []

    cursor = None
    try:
        cursor = conn.cursor()
        
        # Query otimizada com GROUP BY/HAVING (mais rápida e performática)
        sql = """
        SELECT owner
        FROM all_tables
        WHERE owner LIKE 'SW_%'
          AND owner NOT IN ('SW_PUBLICO', 'SW_MODELO', 'SW_BACKUP')
          AND table_name IN ('FOLHA_FUNC', 'FOLHA', 'FUNCIONARIO')
        GROUP BY owner
        HAVING COUNT(DISTINCT table_name) = 3
        """
        
        cursor.execute(sql)
        schemas = [row[0] for row in cursor.fetchall()]
        
        # Debug de sucesso (Opcional: print no terminal para confirmar quantidade)
        print(f"DEBUG: Schemas encontrados com sucesso: {len(schemas)}")
        
        return schemas

    except Exception as e:
        # 2. Captura e exibe o erro na tela (evita a página branca)
        # O st.exception renderiza o erro completo (stack trace) no seu dashboard
        st.error("Erro ao processar busca de schemas. Verifique o log abaixo:")
        st.exception(e)
        
        # Log para o journal/terminal para diagnóstico posterior
        print(f"DEBUG: Ocorreu um erro crítico na query: {str(e)}")
        
        return [] # Retorno seguro para a aplicação continuar rodando

    finally:
        if cursor:
            cursor.close()


def listar_novatos_bancario_com_status(conn, ano, mes):
    # 1. Busca os novos colaboradores
    df_novatos = listar_novatos_bancario(conn, ano, mes)
    
    # GARANTIA: Sempre retorna um DataFrame, nunca None
    if df_novatos is None or df_novatos.empty:
        return pd.DataFrame(columns=['ORGAO', 'COD_INSTITUCIONAL', 'NOME_ATUAL', 'CPF', 'ENVIADO'])

    # 2. Busca os enviados
    #try:
    #    df_enviados = pd.read_sql("SELECT CPF FROM AUDITORIA_ENVIOS_SEFAZ", conn)
    #except Exception:
    #    df_enviados = pd.DataFrame(columns=['CPF'])

    # 3. Faz o merge (garantindo que CPF exista)
    #if 'CPF' in df_novatos.columns:
    #    df_novatos['ENVIADO'] = df_novatos['CPF'].isin(df_enviados['CPF']).map({True: 'SIM', False: 'NÃO'})
    #else:
    #    df_novatos['ENVIADO'] = 'NÃO'

    return df_novatos

def registrar_envio(conn, lista, json_payload, retorno_status):
    user_sefaz = st.session_state.get("sefaz_cpf", "DESCONHECIDO")
    user_sistema = st.session_state.get("login_atual", "SISTEMA")
    usuario_final = f"{user_sistema}_{user_sefaz}" # Exemplo de concatenação

    cursor = conn.cursor()
    try:
        print(f"DEBUG: Tentando recriar {len(lista)} registros no Oracle...")

        # Bloco PL/SQL Anônimo: executa Delete + Insert na mesma viagem de rede
        sql_block = """
        BEGIN
            DELETE FROM AUDITORIA_ENVIOS_SEFAZ 
            WHERE CPF = :cpf AND MATRICULA = :matricula;

            INSERT INTO AUDITORIA_ENVIOS_SEFAZ (ID_ENVIO, CPF, MATRICULA, NOME, DATA_ENVIO, JSON_ENVIO, RETORNO_API, USUARIO_ENVIO)
            VALUES (SEQ_AUD_ENVIOS_SEFAZ.NEXTVAL, :cpf, :matricula, :nome, SYSDATE, :json, :ret, :usuario_envio);
        END;
        """
        
        dados = [
            {
                'cpf': item['CPF'], 
                'matricula': str(item['COD_INSTITUCIONAL']), 
                'nome': item['NOME_ATUAL'], 
                'json': json_payload, 
                'ret': retorno_status,
                'usuario_envio': usuario_final # Adicionado aqui
            } 
            for item in lista
        ]

        cursor.executemany(sql_block, dados)
        conn.commit()
        
        print("DEBUG: DELETE + INSERT (COMMIT) realizado com sucesso!")
        st.cache_data.clear()
        st.success("Dados atualizados e cache limpo!")

    except Exception as e:
        print(f"ERRO CRÍTICO NO BANCO: {str(e)}")
        conn.rollback() 
        raise e 
    finally:
        cursor.close()

def buscar_detalhe_erro_no_banco(conn, cpf):
    try:
        cursor = conn.cursor()
        # Busca o último log de erro para aquele CPF
        sql = """
        SELECT retorno_api 
        FROM AUDITORIA_ENVIOS_SEFAZ 
        WHERE cpf = :cpf 
        ORDER BY data_envio DESC 
        FETCH FIRST 1 ROWS ONLY
        """
        cursor.execute(sql, cpf=cpf)
        res = cursor.fetchone()
        cursor.close()
        return res[0] if res else "Nenhum log encontrado para este CPF."
    except Exception as e:
        return f"Erro ao buscar log no banco: {str(e)}"

def listar_novatos_bancario(conn, ano, mes):
    """
    Lista novatos bancários otimizada: busca schemas que possuem movimento 
    na competência antes de iterar, evitando processar schemas vazios.
    """
    mes_int = int(mes) if str(mes).isdigit() else mes_map.get(mes, 1) # Assumindo mes_map definido
    ano_int = int(ano)

    # 1. Filtro dinâmico: busca apenas schemas que tiveram movimento real no mês/ano
    # Isso reduz drasticamente as iterações de 90 para apenas os ativos (ex: 5 a 10)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT owner 
        FROM all_tables 
        WHERE table_name = 'FOLHA_FUNC' 
        AND owner LIKE 'SW_%'
        AND owner !='SW_FUNPREV'
    """)
    todos_schemas = [row[0] for row in cursor.fetchall()]
    
    # Validação inteligente: filtra apenas os que têm dados na competência
    schemas_ativos = []
    for schema in todos_schemas:
        try:
            # Verifica se o schema tem registros para o mes/ano antes de rodar o SELECT pesado
            check_sql = f"SELECT 1 FROM {schema}.folha f WHERE f.mes = {mes_int} AND f.ano = {int(ano)} AND ROWNUM = 1"
            cursor.execute(check_sql)
            if cursor.fetchone():
                schemas_ativos.append(schema)
        except:
            continue
    cursor.close()

    # 2. Executa a extração apenas nos schemas ativos
    dfs = []
    for schema in schemas_ativos:
        # Consulta otimizada com JOINs diretos
        sql = f"""
        SELECT '{schema.replace('SW_', '')}' AS ORGAO, ff.cod_institucional, phn.nome AS NOME_ATUAL, doc.cpf_pessoa AS CPF, f_tab.chave_folha as CHAVE_FOLHA,
       -- O Oracle usará o índice se a lógica for idêntica à do índice criado
        CASE 
           WHEN hist.retorno_api IS NULL THEN 'NÃO'
           WHEN (CASE WHEN INSTR((hist.retorno_api), 'sucesso') > 0 THEN 1 ELSE 0 END) = 1 THEN 'SIM'
           ELSE 'ERRO'
        END AS ENVIADO
        FROM {schema}.folha_func ff
        INNER JOIN {schema}.folha f_tab ON f_tab.id_folha = ff.id_folha
        INNER JOIN sw_publico.pessoa p ON p.id_pessoa = FF.ID_PESSOA_FUNCIONARIO
        INNER JOIN sw_publico.pessoa_historico_nomes phn ON phn.id_pessoa = p.id_pessoa and phn.data_fim is null
        LEFT JOIN sw_publico.pessoa_doc_cpf doc ON doc.id_pessoa = p.id_pessoa
        LEFT JOIN AUDITORIA_ENVIOS_SEFAZ hist 
            -- ON REGEXP_REPLACE(hist.cpf, '[^0-9]', '') = REGEXP_REPLACE(doc.cpf_pessoa, '[^0-9]', '')
            ON hist.cpf = doc.cpf_pessoa  -- JOIN direto, extremamente rápido
        WHERE f_tab.mes = {mes_int} AND f_tab.ano = {ano_int}
          -- Filtro 1: Garantia de ser NOVATO (Não existe em competências anteriores)
          AND NOT EXISTS (
              SELECT 1 FROM {schema}.folha_func ff_ant
              WHERE ff_ant.id_pessoa_funcionario = ff.id_pessoa_funcionario 
                    and ff_ant.cod_institucional     = ff.cod_institucional
                    and ff_ant.id_folha              < ff.id_folha
                    -- AND (f_ant.ano < {ano_int} OR (f_ant.ano = {ano_int} AND f_ant.mes < {mes_int}))
          )
          AND NOT EXISTS (
              SELECT 1 FROM sw_funprev.folha_func ff_ant
              WHERE ff_ant.id_pessoa_funcionario = ff.id_pessoa_funcionario 
                    and ff_ant.cod_institucional     = ff.cod_institucional
                    and ff_ant.id_folha              < ff.id_folha
          )
        """
        try:
            df = pd.read_sql(sql, conn)
            if not df.empty:
                dfs.append(df)
        except Exception as e:
            print(f"Erro ao processar schema {schema}: {e}")

    # 3. Consolidação final
    if dfs:
        df_final = pd.concat(dfs, ignore_index=True)
        return df_final.drop_duplicates(subset=['CPF', 'COD_INSTITUCIONAL', 'CHAVE_FOLHA'])

    return pd.DataFrame()

