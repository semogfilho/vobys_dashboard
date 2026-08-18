# -*- coding: utf-8 -*-
import oracledb
import streamlit as st

def get_connection():
    """Gerencia a conexão com o banco Oracle de forma centralizada."""
    try:
        # Usando os dados do secrets.toml
        return oracledb.connect(
            user=st.secrets["database"]["db_user"],
            password=st.secrets["database"]["db_pass"],
            dsn=st.secrets["database"]["db_dsn"]
        )
    except Exception as e:
        st.error(f"Erro de conexão ao Oracle: {e}")
        return None

