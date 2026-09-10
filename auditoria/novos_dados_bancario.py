# auditoria/novos_dados_bancario.py
import streamlit as st
import unicodedata
import pandas as pd
import re
import requests
import json

def atualizar_status_sefaz(conn, id_envio, novo_status):
    """
    Atualiza o status retornado pela SEFAZ na tabela de auditoria.
    """
    cursor = conn.cursor()
    try:
        sql_update = """
            UPDATE AUDITORIA_ENVIOS_SEFAZ 
            SET STATUS_SEFAZ = :status 
            WHERE ID_ENVIO = :id
        """
        cursor.execute(sql_update, {'status': novo_status, 'id': id_envio})
        conn.commit()
        print(f"Status atualizado para ID {id_envio}: {novo_status}")
    except Exception as e:
        print(f"Erro ao atualizar status: {e}")
        conn.rollback()
    finally:
        cursor.close()


def atualizar_status_auditoria(conn, df):
    """
    Atualiza de forma rápida apenas os campos [ENVIADO, DATA_ENVIO e SEFAZ]
    consultando diretamente a tabela AUDITORIA_ENVIOS_SEFAZ usando chave composta (CPF + Matrícula).
    """
    if df is None or df.empty or 'CPF' not in df.columns or 'COD_INSTITUCIONAL' not in df.columns:
        return df

    try:
        cpfs = [str(cpf) for cpf in df['CPF'].dropna().unique()]
        if not cpfs:
            return df

        placeholders = ','.join([f":cpf{i}" for i in range(len(cpfs))])
        params = {f"cpf{i}": cpf for i, cpf in enumerate(cpfs)}

        sql = f"""
            SELECT CPF, MATRICULA, RETORNO_API, DATA_ENVIO, STATUS_SEFAZ
            FROM AUDITORIA_ENVIOS_SEFAZ
            WHERE CPF IN ({placeholders})
        """

        df_audit = pd.read_sql(sql, conn, params=params)

        if not df_audit.empty:
            df_audit['DATA_ENVIO_STR'] = pd.to_datetime(df_audit['DATA_ENVIO']).dt.strftime('%d/%m/%Y %H:%M:%S')

            def calcula_enviado(retorno):
                if pd.isnull(retorno):
                    return 'NÃO'
                ret_str = str(retorno)
                if 'sucesso' in ret_str.lower():
                    return 'SIM'
                return 'ERRO'

            df_audit['ENVIADO'] = df_audit['RETORNO_API'].apply(calcula_enviado)

            df_audit['CHAVE_COMPOSITA'] = df_audit['CPF'].astype(str).str.strip() + '_' + df_audit['MATRICULA'].astype(str).str.strip()
            df['CHAVE_COMPOSITA'] = df['CPF'].astype(str).str.strip() + '_' + df['COD_INSTITUCIONAL'].astype(str).str.strip()

            map_enviado = df_audit.set_index('CHAVE_COMPOSITA')['ENVIADO'].to_dict()
            map_data = df_audit.set_index('CHAVE_COMPOSITA')['DATA_ENVIO_STR'].to_dict()
            map_sefaz = df_audit.set_index('CHAVE_COMPOSITA')['STATUS_SEFAZ'].to_dict()

            df['ENVIADO'] = df['CHAVE_COMPOSITA'].map(map_enviado).fillna(df['ENVIADO'] if 'ENVIADO' in df.columns else 'NÃO')
            df['DATA_ENVIO'] = df['CHAVE_COMPOSITA'].map(map_data)
            
            if 'SEFAZ' in df.columns:
                df['SEFAZ'] = df['CHAVE_COMPOSITA'].map(map_sefaz).fillna(df['SEFAZ'])
            else:
                df['SEFAZ'] = df['CHAVE_COMPOSITA'].map(map_sefaz)

            df = df.drop(columns=['CHAVE_COMPOSITA'])

    except Exception as e:
        print(f"DEBUG: Erro ao atualizar status leve: {e}")

    return df


def buscar_por_cpf(conn, cpf_limpo, ano, mes):
    mes_int = int(mes)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT owner FROM all_tables
        WHERE table_name = 'FOLHA_FUNC' AND owner LIKE 'SW_%'
    """)
    schemas = [row[0] for row in cursor.fetchall()]
    cursor.close()

    lista_resultados = []
    total_schemas = len(schemas)

    barra_progresso = st.progress(0, text="Iniciando varredura nos órgãos...")

    for i, schema in enumerate(schemas):
        nome_orgao = schema.replace('SW_', '')
        
        if total_schemas > 0:
            percentual = (i + 1) / total_schemas
            barra_progresso.progress(
                percentual, 
                text=f"Consultando órgão: {nome_orgao} ({i + 1}/{total_schemas})..."
            )

        sql = f"""
            SELECT * FROM (
                SELECT '{nome_orgao}' AS ORGAO,
                        ff.cod_institucional, phn.nome AS NOME_ATUAL, doc.cpf_pessoa AS CPF, 'NÃO' AS ENVIADO, f.chave_folha,
                        ff.data_cadastro AS DIGITACAO_FOLHA,
                        CASE 
                            WHEN pbb.cod_banco IS NULL OR pb.conta_corrente IS NULL THEN 'SEM CONTA CADASTRADA'
                            ELSE pbb.cod_banco || ' / Ag: ' || NVL(pba.cod_agencia, '-') || ' / CC: ' || pb.conta_corrente
                        END AS CONTA_CORRENTE
                FROM {schema}.folha_func ff
                INNER JOIN {schema}.folha f ON f.id_folha = ff.id_folha
                INNER JOIN sw_publico.pessoa p ON p.id_pessoa = ff.id_pessoa_funcionario
                INNER JOIN sw_publico.pessoa_historico_nomes phn ON phn.id_pessoa = p.id_pessoa AND phn.data_fim IS NULL
                INNER JOIN sw_publico.pessoa_doc_cpf doc ON doc.id_pessoa = p.id_pessoa
                LEFT JOIN SW_PUBLICO.Pessoa_Banco pb ON pb.id_pessoa = p.id_pessoa AND pb.data_fim IS NULL
                LEFT JOIN SW_PUBLICO.RHB_BANCO_AGENCIA pba ON pba.id_agencia = pb.id_agencia
                LEFT JOIN SW_PUBLICO.RHB_BANCO pbb ON pbb.id_banco = pba.id_banco
                WHERE REGEXP_REPLACE(doc.cpf_pessoa, '[^0-9]', '') = :cpf
                AND f.ano = :ano AND f.mes = :mes

                UNION ALL

                SELECT '{nome_orgao}' AS ORGAO,
                        pv.cod_institucional, phn.nome AS NOME_ATUAL, doc.cpf_pessoa AS CPF, 'NÃO' AS ENVIADO, ef.mascara chave_folha,
                        ef.data_cadastro AS DIGITACAO_FOLHA,
                        CASE 
                            WHEN pbb.cod_banco IS NULL OR pb.conta_corrente IS NULL THEN 'SEM CONTA CADASTRADA'
                            ELSE pbb.cod_banco || ' / Ag: ' || NVL(pba.cod_agencia, '-') || ' / CC: ' || pb.conta_corrente
                        END AS CONTA_CORRENTE
                FROM {schema}.Estagiario_Pagamento ep
                INNER JOIN {schema}.Estag_Folha ef ON ef.id_folha = ep.id_folha
                INNER JOIN {schema}.estagiario e ON e.id_estagiario = ep.id_estagiario
                INNER JOIN {schema}.PESSOA_VINCULO pv ON pv.id_pessoa_vinculo = e.id_pessoa_vinculo
                INNER JOIN sw_publico.pessoa p ON p.id_pessoa = pv.ID_PESSOA
                INNER JOIN sw_publico.pessoa_historico_nomes phn ON phn.id_pessoa = p.id_pessoa AND phn.data_fim IS NULL
                INNER JOIN sw_publico.pessoa_doc_cpf doc ON doc.id_pessoa = p.id_pessoa
                LEFT JOIN SW_PUBLICO.Pessoa_Banco pb ON pb.id_pessoa = p.id_pessoa AND pb.data_fim IS NULL
                LEFT JOIN SW_PUBLICO.RHB_BANCO_AGENCIA pba ON pba.id_agencia = pb.id_agencia
                LEFT JOIN SW_PUBLICO.RHB_BANCO pbb ON pbb.id_banco = pba.id_banco
                WHERE REGEXP_REPLACE(doc.cpf_pessoa, '[^0-9]', '') = :cpf
                AND ef.ano = :ano AND ef.mes = :mes
            )
        """
        try:
            df = pd.read_sql(sql, conn, params={'cpf': cpf_limpo, 'ano': int(ano), 'mes': mes_int})
            if not df.empty:
                lista_resultados.append(df)
        except Exception as e:
            print(f"DEBUG: Erro no schema {schema}: {e}")
            continue

    barra_progresso.progress(1.0, text="Varredura de CPFs concluída!")

    if lista_resultados:
        return pd.concat(lista_resultados, ignore_index=True)
    
    return pd.DataFrame()


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
            tl.descricao ||' '||
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
        LEFT JOIN SW_PUBLICO.ESB_TIPOS_DE_LOGRADOURO tl on tl.id_esb_tipos_de_logradouro=pe.id_esb_tipos_de_logradouro 
        LEFT JOIN (
            SELECT * FROM (
                SELECT 
                    pis_sub.*, 
                    ROW_NUMBER() OVER (PARTITION BY pis_sub.id_pessoa ORDER BY pis_sub.data_cadastro DESC) as rn
                FROM sw_publico.PESSOA_DOC_PISPASEP pis_sub
                WHERE pis_sub.data_baixa IS NULL
            ) WHERE rn = 1
        ) pis ON pis.id_pessoa = p.id_pessoa
        LEFT JOIN SW_PUBLICO.RHB_CEP_UNIDADE_FEDERACAO upe ON upe.id_unidade_federacao = pe.id_unidade_federacao
        LEFT JOIN SW_PUBLICO.RHB_CEP_MUNICIPIO_IBGE mpe ON mpe.id_municipio = pe.id_municipio
        LEFT JOIN SW_PUBLICO.Pessoa_Banco pb ON pb.id_pessoa = p.id_pessoa AND pb.data_fim IS NULL
        LEFT JOIN SW_PUBLICO.RHB_BANCO_AGENCIA pba ON pba.id_agencia = pb.id_agencia
        LEFT JOIN SW_PUBLICO.RHB_BANCO pbb ON pbb.id_banco = pba.id_banco
        WHERE ff.cod_institucional = :cod
        UNION ALL
        SELECT 
            doc.cpf_pessoa AS CPF,
            phn.nome AS NOME,
            p.data_nascimento AS DATANASCIMENTO,
            pis.PISPASEP AS NUMEROPISPASEPNIT,
            upe.cod_unidade_federacao AS UF,
            mpe.cod_municipio_ibge AS CODIGOMUNICIPIO,
            pe.cep AS CEP,
            tl.descricao ||' '||
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
            pv.cod_institucional AS IDFUNCIONAL
         FROM {schema}.Estagiario_Pagamento ff
        INNER JOIN {schema}.Estag_Folha f_tab ON f_tab.id_folha = ff.id_folha
        INNER JOIN {schema}.estagiario e ON e.id_estagiario = ff.id_estagiario
        INNER JOIN {schema}.PESSOA_VINCULO pv ON pv.id_pessoa_vinculo = e.id_pessoa_vinculo
        INNER JOIN sw_publico.pessoa p ON p.id_pessoa = pv.ID_PESSOA
        INNER JOIN sw_publico.pessoa_historico_nomes phn ON phn.id_pessoa = p.id_pessoa and phn.data_fim is null
        LEFT JOIN sw_publico.pessoa_doc_cpf doc ON doc.id_pessoa = p.id_pessoa
        LEFT JOIN SW_PUBLICO.pessoa_endereco pe ON pe.id_pessoa = p.id_pessoa AND pe.data_fim IS NULL
        LEFT JOIN SW_PUBLICO.ESB_TIPOS_DE_LOGRADOURO tl on tl.id_esb_tipos_de_logradouro=pe.id_esb_tipos_de_logradouro 
        LEFT JOIN (
            SELECT * FROM (
                SELECT 
                    pis_sub.*, 
                    ROW_NUMBER() OVER (PARTITION BY pis_sub.id_pessoa ORDER BY pis_sub.data_cadastro DESC) as rn
                FROM sw_publico.PESSOA_DOC_PISPASEP pis_sub
                WHERE pis_sub.data_baixa IS NULL
            ) WHERE rn = 1
        ) pis ON pis.id_pessoa = p.id_pessoa
        LEFT JOIN SW_PUBLICO.RHB_CEP_UNIDADE_FEDERACAO upe ON upe.id_unidade_federacao = pe.id_unidade_federacao
        LEFT JOIN SW_PUBLICO.RHB_CEP_MUNICIPIO_IBGE mpe ON mpe.id_municipio = pe.id_municipio
        LEFT JOIN SW_PUBLICO.Pessoa_Banco pb ON pb.id_pessoa = p.id_pessoa AND pb.data_fim IS NULL
        LEFT JOIN SW_PUBLICO.RHB_BANCO_AGENCIA pba ON pba.id_agencia = pb.id_agencia
        LEFT JOIN SW_PUBLICO.RHB_BANCO pbb ON pbb.id_banco = pba.id_banco
        WHERE pv.cod_institucional = :cod
    """
    try:
        df = pd.read_sql(sql, conn, params={'cod': cod_institucional})
        if not df.empty:
            return df.iloc[0].to_dict()
        return None
    except Exception as e:
        print(f"Erro crítico no SQL: {e}")
        return None


def remover_acentos(texto):
    if pd.isnull(texto):
        return None
    texto_str = str(texto).strip()
    texto_normalizado = unicodedata.normalize('NFKD', texto_str)
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
        "cpf": limpar_numeros(row['CPF']),
        "nome": remover_acentos(row['NOME']).upper() if pd.notnull(row['NOME']) else None,
        "dataNascimento": row['DATANASCIMENTO'].strftime('%Y-%m-%d') if pd.notnull(row['DATANASCIMENTO']) else None,
        "numeroPisPasepNit": row['NUMEROPISPASEPNIT'],
        "uf": row['UF'],
        "codigoMunicipio": row['CODIGOMUNICIPIO'],
        "cep": limpar_numeros(row['CEP']) or "64018900",
        "endereco": str(row['ENDERECO']).upper().strip() if pd.notnull(row['ENDERECO']) else None,
        "bairro": str(row['BAIRRO']).upper().strip() if pd.notnull(row['BAIRRO']) else None,
        "telefone": limpar_numeros(row['TELEFONE']),
        "telefone2": limpar_numeros(row['TELEFONE2']),
        "celular": limpar_numeros(row['CELULAR']),
        "fax": limpar_numeros(row['FAX']),
        "email": remover_acentos(row['EMAIL']).lower() if pd.notnull(row['EMAIL']) else None,
        "dadosBancarios": [{
            "codigoBanco": row['CODIGOBANCO'],
            "codigoAgencia": str(row['CODIGOAGENCIA']).split('-')[0].zfill(4),
            "numeroConta": str(row['NUMEROCONTA']).replace(' ', '').replace('.', '').replace('-', '').zfill(13),
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
 
    try:
        session = requests.Session()
        session.verify = False

        payload_auth = {"usuario": usuario, "senha": senha}
        r_auth = session.post(f"{BASE_URL}/auth", json=payload_auth, timeout=10)
        r_auth.raise_for_status()

        token = r_auth.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})

        print("DEBUG: Headers enviados:", session.headers)
        print("DEBUG: Payload enviado:", payload)

        response = session.post(URL_FINAL, json=payload, timeout=10)
        sucesso = response.status_code in [200, 201]
        
        return sucesso, json.dumps(payload), response.text

    except Exception as e:
        return False, None, str(e)


def obter_schemas_dinamicos(conn):
    if conn is None:
        print("DEBUG: Conexão (conn) é None!")
        return []

    cursor = None
    try:
        cursor = conn.cursor()
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
        print(f"DEBUG: Schemas encontrados com sucesso: {len(schemas)}")
        return schemas

    except Exception as e:
        st.error("Erro ao processar busca de schemas. Verifique o log abaixo:")
        st.exception(e)
        print(f"DEBUG: Ocorreu um erro crítico na query: {str(e)}")
        return []

    finally:
        if cursor:
            cursor.close()


def listar_novatos_bancario_com_status(conn, ano, mes):
    df_novatos = listar_novatos_bancario(conn, ano, mes)

    if df_novatos is None or df_novatos.empty:
        return pd.DataFrame(columns=['ORGAO', 'COD_INSTITUCIONAL', 'NOME_ATUAL', 'CPF', 'CHAVE_FOLHA', 'ENVIADO', 'DATA_ENVIO', 'DIGITACAO_FOLHA', 'SEFAZ', 'CONTA_CORRENTE'])

    return df_novatos


def registrar_envio(conn, lista, json_payload, retorno_status):
    user_sefaz = st.session_state.get("sefaz_cpf", "DESCONHECIDO")
    user_sistema = st.session_state.get("login_atual", "SISTEMA")
    usuario_final = f"{user_sistema}_{user_sefaz}"

    cursor = conn.cursor()
    try:
        print(f"DEBUG: Tentando recriar {len(lista)} registros no Oracle...")

        sql_block = """
        BEGIN
            DELETE FROM AUDITORIA_ENVIOS_SEFAZ 
            WHERE CPF = :cpf AND MATRICULA = :matricula;

            INSERT INTO AUDITORIA_ENVIOS_SEFAZ (ID_ENVIO, CPF, MATRICULA, NOME, DATA_ENVIO, JSON_ENVIO, RETORNO_API, USUARIO_ENVIO, STATUS_SEFAZ)
            VALUES (SEQ_AUD_ENVIOS_SEFAZ.NEXTVAL, :cpf, :matricula, :nome, SYSDATE, :json, :ret, :usuario_envio, :status_sefaz);
        END;
        """
        
        dados = [
            {
                'cpf': item['CPF'], 
                'matricula': str(item['COD_INSTITUCIONAL']), 
                'nome': item['NOME_ATUAL'], 
                'json': json_payload, 
                'ret': retorno_status,
                'usuario_envio': usuario_final,
                'status_sefaz': '✅ MATRÍCULA ATIVA'
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
    mes_int = int(mes) if str(mes).isdigit() else 1
    ano_int = int(ano)

    cursor = conn.cursor()
    cursor.execute("""
        SELECT owner 
        FROM all_tables 
        WHERE table_name = 'FOLHA_FUNC' 
        AND owner LIKE 'SW_%'
        AND owner NOT IN ('SW_FUNPREV', 'SW_REENVIO')
    """)
    todos_schemas = [row[0] for row in cursor.fetchall()]
    
    schemas_ativos = []
    for schema in todos_schemas:
        try:
            check_sql = f"SELECT 1 FROM {schema}.folha f WHERE f.mes = {mes_int} AND f.ano = {int(ano)} AND ROWNUM = 1"
            cursor.execute(check_sql)
            if cursor.fetchone():
                schemas_ativos.append(schema)
        except:
            continue
    cursor.close()

    dfs = []
    for schema in schemas_ativos:
        sql = f"""
        SELECT '{schema.replace('SW_', '')}' AS ORGAO, ff.cod_institucional, phn.nome AS NOME_ATUAL, doc.cpf_pessoa AS CPF, f_tab.chave_folha as CHAVE_FOLHA,
        CASE 
           WHEN hist.retorno_api IS NULL THEN 'NÃO'
           WHEN (CASE WHEN INSTR((hist.retorno_api), 'sucesso') > 0 THEN 1 ELSE 0 END) = 1 THEN 'SIM'
           ELSE 'ERRO'
        END AS ENVIADO
        ,TO_CHAR(hist.DATA_ENVIO, 'DD/MM/YYYY HH24:MI:SS') AS DATA_ENVIO
        ,hist.STATUS_SEFAZ AS SEFAZ
        ,ff.data_cadastro AS DIGITACAO_FOLHA
        ,CASE 
            WHEN pbb.cod_banco IS NULL OR pb.conta_corrente IS NULL THEN 'SEM CONTA CADASTRADA'
            ELSE pbb.cod_banco || ' / Ag: ' || NVL(pba.cod_agencia, '-') || ' / CC: ' || pb.conta_corrente
         END AS CONTA_CORRENTE
        ,doc.id_pessoa
        FROM {schema}.folha_func ff
        INNER JOIN {schema}.folha f_tab ON f_tab.id_folha = ff.id_folha
        INNER JOIN sw_publico.pessoa p ON p.id_pessoa = FF.ID_PESSOA_FUNCIONARIO
        INNER JOIN sw_publico.pessoa_historico_nomes phn ON phn.id_pessoa = p.id_pessoa and phn.data_fim is null
        LEFT JOIN sw_publico.pessoa_doc_cpf doc ON doc.id_pessoa = p.id_pessoa
        LEFT JOIN SW_PUBLICO.Pessoa_Banco pb ON pb.id_pessoa = p.id_pessoa AND pb.data_fim IS NULL
        LEFT JOIN SW_PUBLICO.RHB_BANCO_AGENCIA pba ON pba.id_agencia = pb.id_agencia
        LEFT JOIN SW_PUBLICO.RHB_BANCO pbb ON pbb.id_banco = pba.id_banco
        LEFT JOIN AUDITORIA_ENVIOS_SEFAZ hist 
            ON hist.cpf = doc.cpf_pessoa AND hist.matricula = ff.cod_institucional
        WHERE f_tab.mes = {mes_int} AND f_tab.ano = {ano_int}
          AND NOT EXISTS (
              SELECT 1 FROM {schema}.folha_func ff_ant
              WHERE ff_ant.id_pessoa_funcionario = ff.id_pessoa_funcionario 
                    and ff_ant.cod_institucional     = ff.cod_institucional
                    and ff_ant.id_folha              < ff.id_folha
          )
          AND NOT EXISTS (
              SELECT 1 FROM sw_funprev.folha_func ff_ant
              WHERE ff_ant.id_pessoa_funcionario = ff.id_pessoa_funcionario 
                    and ff_ant.cod_institucional     = ff.cod_institucional
                    and ff_ant.id_folha              < ff.id_folha
          )
        UNION ALL

        SELECT '{schema.replace('SW_', '')}' AS ORGAO, pv.cod_institucional, phn.nome AS NOME_ATUAL, 
               doc.cpf_pessoa AS CPF, f_tab.mascara AS CHAVE_FOLHA,
               CASE
                   WHEN hist.retorno_api IS NULL THEN 'NÃO'
                   WHEN INSTR(hist.retorno_api, 'sucesso') > 0 THEN 'SIM'
                   ELSE 'ERRO'
               END AS ENVIADO
        ,TO_CHAR(hist.DATA_ENVIO, 'DD/MM/YYYY HH24:MI:SS') AS DATA_ENVIO
        ,hist.STATUS_SEFAZ AS SEFAZ
        ,f_tab.data_cadastro AS DIGITACAO_FOLHA
        ,CASE 
            WHEN pbb.cod_banco IS NULL OR pb.conta_corrente IS NULL THEN 'SEM CONTA CADASTRADA'
            ELSE pbb.cod_banco || ' / Ag: ' || NVL(pba.cod_agencia, '-') || ' / CC: ' || pb.conta_corrente
         END AS CONTA_CORRENTE
        ,doc.id_pessoa
        FROM {schema}.Estagiario_Pagamento ff
        INNER JOIN {schema}.Estag_Folha f_tab ON f_tab.id_folha = ff.id_folha
        INNER JOIN {schema}.estagiario e ON e.id_estagiario = ff.id_estagiario
        INNER JOIN {schema}.PESSOA_VINCULO pv ON pv.id_pessoa_vinculo = e.id_pessoa_vinculo
        INNER JOIN sw_publico.pessoa p ON p.id_pessoa = pv.ID_PESSOA
        INNER JOIN sw_publico.pessoa_historico_nomes phn ON phn.id_pessoa = p.id_pessoa and phn.data_fim is null
        LEFT JOIN sw_publico.pessoa_doc_cpf doc ON doc.id_pessoa = p.id_pessoa
        LEFT JOIN SW_PUBLICO.Pessoa_Banco pb ON pb.id_pessoa = p.id_pessoa AND pb.data_fim IS NULL
        LEFT JOIN SW_PUBLICO.RHB_BANCO_AGENCIA pba ON pba.id_agencia = pb.id_agencia
        LEFT JOIN SW_PUBLICO.RHB_BANCO pbb ON pbb.id_banco = pba.id_banco
        LEFT JOIN AUDITORIA_ENVIOS_SEFAZ hist ON hist.cpf = doc.cpf_pessoa AND hist.matricula = pv.cod_institucional
        WHERE f_tab.mes = {mes_int} AND f_tab.ano = {ano_int}
            AND NOT EXISTS (
              SELECT 1 FROM {schema}.Estagiario_Pagamento ff_ant
              INNER JOIN {schema}.estagiario e_ant  on e_ant.id_estagiario= ff_ant.id_estagiario
              WHERE e_ant.id_estagiario = e.id_estagiario
                    and ff_ant.id_folha              < ff.id_folha
          )
        """
        try:
            df = pd.read_sql(sql, conn)
            if not df.empty:
                dfs.append(df)
        except Exception as e:
            print(f"Erro ao processar schema {schema}: {e}")

    if dfs:
        df_novatos = pd.concat(dfs, ignore_index=True)
    
        if not df_novatos.empty and 'ID_PESSOA' in df_novatos.columns:
            df_novatos['LINK_SIAPE'] = (
                "https://siape.sead.pi.gov.br/adm/sead/pessoas-sead/pessoa-sead/"
                + df_novatos['ID_PESSOA'].astype(str)
                + "/dados-cadastrais/vinculos/vinculos#"
                + df_novatos['CPF'].fillna('').astype(str)
            )
        return df_novatos
    else:
        return pd.DataFrame()

