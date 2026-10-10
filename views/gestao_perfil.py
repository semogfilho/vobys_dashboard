# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import os

def render(conn, *args, **kwargs):
    st.title("⚙️ Gestão de Módulos, Perfis e Acessos")
    st.markdown("Gerencie os módulos do sistema, crie novos perfis e associe as permissões em tempo real.")

    tab1, tab2, tab3 = st.tabs(["📦 Cadastro de Módulos", "👤 Cadastro de Perfis", "🔗 Atribuição (Perfil x Módulos)"])

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    raiz_sistema = os.path.abspath(os.path.join(BASE_DIR, ".."))

    def carregar_todos_modulos():
        if not conn: return pd.DataFrame()
        query = "SELECT id, nome_menu, arquivo_view, ordem FROM josegomes.modulo ORDER BY ordem ASC"
        return pd.read_sql(query, conn)

    def carregar_todos_perfis():
        if not conn: return pd.DataFrame()
        query = "SELECT id, descricao FROM josegomes.perfil ORDER BY id ASC"
        return pd.read_sql(query, conn)

    def carregar_modulos_por_perfil_id(perfil_id):
        if not conn: return []
        query = "SELECT id_modulo FROM josegomes.perfil_modulo WHERE id_perfil = :perfil_id"
        cursor = conn.cursor()
        cursor.execute(query, {"perfil_id": perfil_id})
        rows = cursor.fetchall()
        cursor.close()
        return [r[0] for r in rows]

    with tab1:
        col_cad, col_list = st.columns([1, 1.5])
        with col_cad:
            st.subheader("Novo Módulo")
            
            # Descobre automaticamente os arquivos .py na pasta views
            pasta_views = BASE_DIR
            arquivos_views = []
            if os.path.exists(pasta_views):
                for f in sorted(os.listdir(pasta_views)):
                    if f.endswith(".py") and f != "__init__":
                        arquivos_views.append(f[:-3]) # Remove a extensão .py

            with st.form("form_modulo"):
                nome_menu = st.text_input("Nome no Menu (ex: ⚙️ Gestão de Perfis)")
                
                if arquivos_views:
                    arquivo_view = st.selectbox("Caminho View:", options=arquivos_views)
                else:
                    arquivo_view = st.text_input("Caminho View (ex: gestao_perfil)")

                ordem = st.number_input("Ordem", min_value=1, value=10)
                
                if st.form_submit_button("Salvar Módulo"):
                    if nome_menu and arquivo_view:
                        if conn:
                            try:
                                cursor = conn.cursor()
                                cursor.execute(
                                    "INSERT INTO josegomes.modulo (nome_menu, arquivo_view, ordem, ativo) VALUES (:1, :2, :3, 1)",
                                    (nome_menu, arquivo_view, ordem)
                                )
                                conn.commit()
                                cursor.close()
                                st.success(f"Módulo '{nome_menu}' cadastrado com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao inserir módulo: {e}")
                        else:
                            st.error("Falha na conexão com o banco.")
                    else:
                        st.warning("Preencha todos os campos obrigatórios.")

        with col_list:
            st.subheader("Módulos Cadastrados")
            df_mod = carregar_todos_modulos()
            if not df_mod.empty:
                st.dataframe(df_mod, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum módulo cadastrado.")

    with tab2:
        col_cad_p, col_list_p = st.columns([1, 1.5])
        with col_cad_p:
            st.subheader("Novo Perfil")
            with st.form("form_perfil"):
                desc_perfil = st.text_input("Descrição (ex: Supervisor)")
                if st.form_submit_button("Salvar Perfil"):
                    if desc_perfil:
                        if conn:
                            try:
                                cursor = conn.cursor()
                                cursor.execute("INSERT INTO josegomes.perfil (descricao) VALUES (:1)", (desc_perfil,))
                                conn.commit()
                                cursor.close()
                                st.success(f"Perfil '{desc_perfil}' cadastrado com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao inserir perfil: {e}")
                        else:
                            st.error("Falha na conexão.")
                    else:
                        st.warning("Informe a descrição do perfil.")

        with col_list_p:
            st.subheader("Perfis Existentes")
            df_perf = carregar_todos_perfis()
            if not df_perf.empty:
                st.dataframe(df_perf, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum perfil cadastrado.")

    with tab3:
        st.subheader("Vincular Módulos aos Perfis")
        df_perf = carregar_todos_perfis()
        df_mod = carregar_todos_modulos()

        if df_perf.empty or df_mod.empty:
            st.warning("Cadastre ao menos um perfil e um módulo antes de fazer associações.")
            return

        perfil_map = {row['DESCRICAO']: row['ID'] for _, row in df_perf.iterrows()}
        perfil_escolhido = st.selectbox("Selecione o Perfil:", options=list(perfil_map.keys()))
        id_perfil_sel = perfil_map[perfil_escolhido]

        modulos_atuais = carregar_modulos_por_perfil_id(id_perfil_sel)
        modulo_map = {f"{row['ID']} - {row['NOME_MENU']} ({row['ARQUIVO_VIEW']})": row['ID'] for _, row in df_mod.iterrows()}
        default_mod_labels = [k for k, v in modulo_map.items() if v in modulos_atuais]

        modulos_selecionados_labels = st.multiselect(
            "Selecione os módulos permitidos para este perfil:",
            options=list(modulo_map.keys()),
            default=default_mod_labels
        )

        if st.button("Salvar Permissões"):
            if conn:
                try:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM josegomes.perfil_modulo WHERE id_perfil = :1", (id_perfil_sel,))
                    for label in modulos_selecionados_labels:
                        id_mod = modulo_map[label]
                        cursor.execute(
                            "INSERT INTO josegomes.perfil_modulo (id_perfil, id_modulo) VALUES (:1, :2)",
                            (id_perfil_sel, id_mod)
                        )
                    conn.commit()
                    cursor.close()
                    st.success("Permissões atualizadas com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar permissões: {e}")
