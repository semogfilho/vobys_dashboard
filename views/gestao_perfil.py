# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import os

def render(conn, *args, **kwargs):
    st.title("⚙️ Gestão de Módulos, Perfis e Acessos")
    st.markdown("Gerencie os módulos do sistema, crie novos perfis e associe as permissões em tempo real.")

    tab1, tab2, tab3 = st.tabs(["📦 Cadastro e Edição de Módulos", "👤 Cadastro de Perfis", "🔗 Atribuição (Perfil x Módulos)"])

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    def carregar_todos_modulos():
        if not conn: return pd.DataFrame()
        query = "SELECT id, nome_menu, arquivo_view, ordem, ativo FROM josegomes.modulo ORDER BY ordem ASC"
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

    # Mapeia os arquivos .py válidos da pasta views (ignorando __init__)
    pasta_views = BASE_DIR
    arquivos_views = []
    if os.path.exists(pasta_views):
        for f in sorted(os.listdir(pasta_views)):
            if f.endswith(".py") and not f.startswith("__"):
                arquivos_views.append(f[:-3])

    with tab1:
        col_form, col_list = st.columns([1, 1.3])

        df_mod = carregar_todos_modulos()

        with col_form:
            # Alternador entre Novo Módulo e Editar Módulo
            modo_acao = st.radio("Ação:", ["➕ Novo Módulo", "✏️ Editar Módulo"], horizontal=True, key="modo_acao_modulo")

            if modo_acao == "➕ Novo Módulo":
                st.subheader("Novo Módulo")
                with st.form("form_novo_modulo"):
                    nome_menu = st.text_input("Nome no Menu (ex: ⚙️ Gestão de Perfis)")
                    
                    if arquivos_views:
                        arquivo_view = st.selectbox("Caminho View:", options=arquivos_views, key="new_view_sel")
                    else:
                        arquivo_view = st.text_input("Caminho View (ex: gestao_perfil)")

                    ordem = st.number_input("Ordem", min_value=1, value=10, key="new_ordem")
                    
                    if st.form_submit_button("Salvar Módulo", type="primary"):
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

            else:
                st.subheader("Editar Módulo Existente")
                if not df_mod.empty:
                    modulo_opcoes = {f"{row['ID']} - {row['NOME_MENU']} ({row['ARQUIVO_VIEW']})": row['ID'] for _, row in df_mod.iterrows()}
                    mod_selecionado_label = st.selectbox("Selecione o Módulo para Editar:", options=list(modulo_opcoes.keys()))
                    id_mod_edit = modulo_opcoes[mod_selecionado_label]

                    dados_atuais = df_mod[df_mod['ID'] == id_mod_edit].iloc[0]

                    with st.form("form_editar_modulo"):
                        edit_nome_menu = st.text_input("Nome no Menu", value=str(dados_atuais['NOME_MENU']))
                        
                        val_view = str(dados_atuais['ARQUIVO_VIEW']).replace("views.", "")
                        idx_view = arquivos_views.index(val_view) if val_view in arquivos_views else 0

                        if arquivos_views:
                            edit_arquivo_view = st.selectbox("Caminho View:", options=arquivos_views, index=idx_view)
                        else:
                            edit_arquivo_view = st.text_input("Caminho View", value=val_view)

                        edit_ordem = st.number_input("Ordem", min_value=1, value=int(dados_atuais['ORDEM']))
                        edit_ativo = st.checkbox("Módulo Ativo", value=bool(int(dados_atuais.get('ATIVO', 1)) == 1))

                        if st.form_submit_button("Atualizar Módulo", type="primary"):
                            if edit_nome_menu and edit_arquivo_view:
                                if conn:
                                    try:
                                        cursor = conn.cursor()
                                        cursor.execute("""
                                            UPDATE josegomes.modulo 
                                            SET nome_menu = :1, arquivo_view = :2, ordem = :3, ativo = :4
                                            WHERE id = :5
                                        """, (edit_nome_menu, edit_arquivo_view, edit_ordem, 1 if edit_ativo else 0, id_mod_edit))
                                        conn.commit()
                                        cursor.close()
                                        st.success(f"Módulo '{edit_nome_menu}' atualizado com sucesso!")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erro ao atualizar módulo: {e}")
                                else:
                                    st.error("Falha na conexão.")
                            else:
                                st.warning("Preencha todos os campos obrigatórios.")
                else:
                    st.info("Nenhum módulo cadastrado para editar.")

        with col_list:
            st.subheader("Módulos Cadastrados")
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

        if st.button("Salvar Permissões", type="primary"):
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
