# -*- coding: utf-8 -*-
import os
import sys
import oracledb

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

def get_connection_direto():
    """Obtém a conexão lendo diretamente do secrets.toml do Streamlit para uso via CLI."""
    try:
        # Tenta importar o secrets do streamlit se houver contexto
        import streamlit as st
        db = st.secrets["database"]
    except Exception:
        # Fallback: lê manualmente o arquivo .streamlit/secrets.toml se executado via terminal
        import toml
        secrets_path = os.path.join(BASE_DIR, ".streamlit", "secrets.toml")
        if os.path.exists(secrets_path):
            secrets = toml.load(secrets_path)
            db = secrets["database"]
        else:
            raise Exception("Arquivo .streamlit/secrets.toml não encontrado.")

    conn = oracledb.connect(
        user=db["db_user"],
        password=db["db_pass"],
        dsn=db["db_dsn"]
    )
    return conn

def exportar_todos_objetos():
    try:
        conn = get_connection_direto()
    except Exception as e:
        print(f"Erro ao estabelecer conexão com o banco de dados: {e}")
        return

    cursor = conn.cursor()

    sql_objetos = """
        SELECT object_name, object_type 
        FROM dba_objects 
        WHERE owner = 'JOSEGOMES' 
          AND object_type IN ('TABLE', 'SEQUENCE', 'INDEX', 'VIEW', 'PACKAGE', 'PACKAGE BODY', 'PROCEDURE', 'FUNCTION', 'TRIGGER')
          AND object_name NOT LIKE 'ISEQ$$_%'
        ORDER BY object_type, object_name
    """
    
    try:
        cursor.execute(sql_objetos)
        objetos = cursor.fetchall()
    except Exception as e:
        print(f"Erro ao listar objetos via dba_objects: {e}")
        cursor.close()
        conn.close()
        return

    print(f"Encontrados {len(objetos)} objetos no owner JOSEGOMES.")

    output_base = os.path.join(BASE_DIR, "db", "ddl")
    if not os.path.exists(output_base):
        os.makedirs(output_base)

    try:
        cursor.execute("BEGIN DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM,'STORAGE',false); END;")
        cursor.execute("BEGIN DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM,'SEGMENT_ATTRIBUTES',false); END;")
    except Exception:
        pass

    for obj_name, obj_type in objetos:
        tipo_dir_map = {
            'TABLE': 'tables',
            'SEQUENCE': 'sequences',
            'INDEX': 'indexes',
            'VIEW': 'views',
            'PACKAGE': 'packages',
            'PACKAGE BODY': 'packages',
            'PROCEDURE': 'procedures',
            'FUNCTION': 'functions',
            'TRIGGER': 'triggers'
        }
        
        sub_folder = tipo_dir_map.get(obj_type, 'outros')
        output_dir = os.path.join(output_base, sub_folder)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        try:
            cursor.execute(
                "SELECT DBMS_METADATA.GET_DDL(:obj_type, :obj_name, 'JOSEGOMES') FROM DUAL",
                {"obj_type": obj_type, "obj_name": obj_name}
            )
            res = cursor.fetchone()
            if res and res[0]:
                ddl_texto = res[0]
                if hasattr(ddl_texto, "read"):
                    ddl_texto = ddl_texto.read()

                arquivo_path = os.path.join(output_dir, obj_name.lower() + ".sql")
                with open(arquivo_path, "w") as f:
                    f.write(str(ddl_texto) + ";\n")
                
                print(f"[SUCESSO] [{obj_type}] Exportado: {obj_name}.sql -> {sub_folder}/")
            else:
                print(f"[AVISO] DDL vazio para {obj_type}: {obj_name}")
        except Exception as ex:
            print(f"[ERRO] Falha ao exportar {obj_type} {obj_name}: {ex}")

    cursor.close()
    conn.close()
    print(f"\nProcesso concluido! Salvo em: {output_base}")

if __name__ == "__main__":
    exportar_todos_objetos()

