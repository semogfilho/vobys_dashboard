# -*- coding: utf-8 -*-
import oracledb
import streamlit as st

def get_connection():
    """Obtém a conexão com o banco Oracle utilizando as credenciais do st.secrets."""
    try:
        db = st.secrets["database"]
        conn = oracledb.connect(
            user=db["db_user"],
            password=db["db_pass"],
            dsn=db["db_dsn"]
        )
        return conn
    except Exception as e:
        st.error(f"Erro ao conectar ao banco de dados: {e}")
        return None

