# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import requests
import urllib3
import re
import time
from datetime import datetime
from auditoria.novos_dados_bancario import listar_novatos_bancario, atualizar_status_auditoria

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def formatar_cpf(val_cpf):
    """Formata uma string de CPF para o padrão 000.000.000-00 para exibição"""
    if not val_cpf or pd.isna(val_cpf):
        return ""
    digitos = re.sub(r'\D', '', str(val_cpf)).zfill(11)
    if len(digitos) == 11:
        return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
    return str(val_cpf)

def formatar_cpf_completo(val_cpf):
    """Formata para 000.000.000-00 para salvar no banco com máscara"""
    if not val_cpf or pd.isna(val_cpf):
        return ""
    s = re.sub(r'\D', '', str(val_cpf)).zfill(11)
    return f"{s[:3]}.{s[3:6]}.{s[6:9]}-{s[9:]}"

def consultar_credor_sefaz_individual(ano, cpf_ou_credor, matricula_para_conferir):
    try:
        usuario = st.secrets["sefaz"]["SIAFE_CPF"]
        senha = st.secrets["sefaz"]["SIAFE_SENHA"]
        BASE_URL = st.secrets["sefaz"]["BASE_URL"]

        cpf_limpo = re.sub(r'\D', '', str(cpf_ou_credor)).zfill(11)
        matricula_limpa = re.sub(r'\D', '', str(matricula_para_conferir).split('.')[0])

        if not cpf_limpo:
            return "CPF Inválido"

        session = requests.Session()
        session.verify = False
        session.headers.update({"Content-Type": "application/json"})

        payload_auth = {"usuario": usuario, "senha": senha}
        r_auth = session.post(f"{BASE_URL}/auth", json=payload_auth, timeout=15)
        r_auth.raise_for_status()

        token = r_auth.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})

        url = f"{BASE_URL}/apoio-geral/credor/{ano}/{cpf_limpo}"

        try:
            r = session.get(url, timeout=30)
        except requests.exceptions.Timeout:
            return "ERRO TIMEOUT"
        except requests.exceptions.ConnectionError:
            return "ERRO CONEXÃO"

        if r.status_code == 200:
            data = r.json()
            if isinstance(data, dict):
                dados_bancarios = data.get("dadosBancarios", data.get("domiciliosBancario", []))

                existe_matricula = False
                for v in dados_bancarios:
                    raw_val = str(v.get("idFuncional", v.get("matricula", "")))
                    partes = raw_val.split(";")
                    for p in partes:
                        if re.sub(r'\D', '', p) == matricula_limpa:
                            existe_matricula = True
                            break
                    if existe_matricula:
                        break

                if existe_matricula:
                    return "✅ MATRÍCULA ATIVA"
                else:
                    return "⚠️ MATRÍCULA NÃO ENCONTRADA"
            else:
                return "NÃO CADASTRADO"

        elif r.status_code == 404:
            return "NÃO CADASTRADO"
        else:
            return f"ERRO API ({r.status_code})"

    except Exception as e:
        print(f"DEBUG EXCEPTION: {str(e)}")
        return "ERRO CONEXÃO"

def renderizar_dados_bancarios(conn, ano, mes, auth_ui, novos_dados_bancario):
    try:
        mes_exibicao = "13º" if int(mes) == 13 else f"{int(mes):02d}"
        st.subheader(f"🏦 Dados Bancários (Novatos) ({mes_exibicao}/{ano})")

        @st.cache_data(ttl=600, show_spinner=False)
        def carregar_dados_bancarios(ano, mes):
            return novos_dados_bancario.listar_novatos_bancario_com_status(conn, ano, mes)

        if 'df_bancario' not in st.session_state or st.session_state.get('last_params') != (ano, mes):
            with st.spinner("Buscando dados no banco..."):
                df_temp = carregar_dados_bancarios(ano, mes)
                df_temp = df_temp.reset_index(drop=True)

                if 'CPF' in df_temp.columns and 'ORGAO' in df_temp.columns:
                    cpfs_excecao = [
                        '05602146342', '04227244323', '00306962322',
                        '00352388366', '00352234300', '00522894356', '01461363306'
                    ]
                    df_temp['CPF_LIMPO'] = df_temp['CPF'].astype(str).str.replace(r'\D', '', regex=True).str.zfill(11)
                    mask_cpfs = df_temp['CPF_LIMPO'].isin(cpfs_excecao)
                    mask_seduc = df_temp['ORGAO'].astype(str).str.upper() == 'SEDUC'
                    df_temp = df_temp.drop(columns=['CPF_LIMPO'], errors='ignore')

                if 'SEFAZ' not in df_temp.columns:
                    df_temp['SEFAZ'] = '⏳ PENDENTE'

                if not df_temp.empty:
                    df_temp = atualizar_status_auditoria(conn, df_temp)

                st.session_state.df_bancario = df_temp.reset_index(drop=True)
                st.session_state.last_params = (ano, mes)

        if not st.session_state.df_bancario.empty:
            if "ENVIAR" not in st.session_state.df_bancario.columns:
                st.session_state.df_bancario["ENVIAR"] = False
            if "SEFAZ" not in st.session_state.df_bancario.columns:
                st.session_state.df_bancario["SEFAZ"] = '⏳ PENDENTE'

            st.session_state.df_bancario = st.session_state.df_bancario.sort_values(by=["ORGAO", "CPF"]).reset_index(drop=True)

            # -------------------------------------------------------------
            # MODO PASSO A PASSO (SEFAZ ITERATIVO)
            # -------------------------------------------------------------
            if st.session_state.get('modo_passo_a_passo_ativo', False):
                indices_pendentes = st.session_state.get('indices_passo_a_passo', [])
                passo_atual = st.session_state.get('indice_passo_atual', 0)

                st.subheader(f"⚙️ Processamento Passo a Passo ({passo_atual + 1} de {len(indices_pendentes)})")
                st.progress((passo_atual + 1) / len(indices_pendentes))

                if passo_atual < len(indices_pendentes):
                    idx = indices_pendentes[passo_atual]

                    row = st.session_state.df_bancario.loc[idx]
                    if isinstance(row, pd.DataFrame):
                        row = row.iloc[0]

                    cpf_cru = str(row.get('CPF', ''))
                    matricula_atual = str(row.get('COD_INSTITUCIONAL', ''))
                    nome_atual = str(row.get('NOME_ATUAL', 'Sem Nome'))
                    org_atual = str(row.get('ORGAO', ''))

                    st.info(f"**Órgão:** {org_atual} | **Matrícula:** {matricula_atual} | **Nome:** {nome_atual} | **CPF:** {cpf_cru}")

                    col_passo1, col_passo2 = st.columns([1, 1])
                    with col_passo1:
                        btn_proximo = st.button("▶️ Processar Próximo Registro", type="primary")
                    with col_passo2:
                        btn_parar = st.button("⏹️ Sair do Modo Passo a Passo")

                    if btn_parar:
                        st.session_state.modo_passo_a_passo_ativo = False
                        st.rerun()

                    if btn_proximo:
                        user_sistema = st.session_state.get("login_atual", "SISTEMA")

                        digitos_puros = re.sub(r'\D', '', cpf_cru)
                        if len(digitos_puros) > 11:
                            digitos_puros = digitos_puros[-11:]
                        digitos_puros = digitos_puros.zfill(11)

                        if len(digitos_puros) != 11 or len(set(digitos_puros)) == 1:
                            res_visual = "CPF INVÁLIDO"
                        else:
                            nums = [int(dig) for dig in digitos_puros]
                            soma1 = sum(nums[i] * (i + 1) for i in range(9))
                            resto1 = soma1 % 11
                            if resto1 == 10: resto1 = 0

                            soma2 = sum(nums[i] * i for i in range(10))
                            resto2 = soma2 % 11
                            if resto2 == 10: resto2 = 0

                            if resto1 != nums[9] or resto2 != nums[10]:
                                res_visual = "CPF INVÁLIDO"
                            else:
                                res_visual = consultar_credor_sefaz_individual(ano, digitos_puros, matricula_atual)

                        p_cpf_fmt = formatar_cpf_completo(cpf_cru)
                        p_mat = matricula_atual
                        p_nome = nome_atual[:150]
                        p_usr = str(user_sistema)

                        try:
                            cursor = conn.cursor()
                            sql_block = """
                            BEGIN
                                DELETE FROM AUDITORIA_ENVIOS_SEFAZ
                                WHERE REGEXP_REPLACE(CPF, '[^0-9]', '') = :cpf_numerico
                                  AND MATRICULA = :mat;

                                INSERT INTO AUDITORIA_ENVIOS_SEFAZ (ID_ENVIO, CPF, MATRICULA, NOME, STATUS_SEFAZ, USUARIO_ENVIO)
                                VALUES (SEQ_AUD_ENVIOS_SEFAZ.NEXTVAL, :cpf_fmt, :mat, :nome, :status, :usr);
                            END;
                            """
                            cursor.execute(sql_block, {
                                'cpf_numerico': re.sub(r'\D', '', cpf_cru),
                                'cpf_fmt': p_cpf_fmt,
                                'mat': p_mat,
                                'nome': p_nome,
                                'status': str(res_visual),
                                'usr': p_usr
                            })
                            conn.commit()
                            cursor.close()
                        except Exception as e_db:
                            conn.rollback()
                            st.error(f"Erro ao salvar no banco: {e_db}")

                        st.session_state.df_bancario.loc[idx, 'SEFAZ'] = res_visual

                        if passo_atual + 1 < len(indices_pendentes):
                            st.session_state.indice_passo_atual += 1
                            st.rerun()
                        else:
                            st.session_state.modo_passo_a_passo_ativo = False
                            st.session_state.df_bancario = atualizar_status_auditoria(conn, st.session_state.df_bancario)
                            carregar_dados_bancarios.clear()
                            st.success("🎉 Todos os registros selecionados foram processados com sucesso!")
                            time.sleep(1.5)
                            st.rerun()

                st.divider()
                return

            # -------------------------------------------------------------
            # TELA 1: PROCESSAMENTO EM LOTE (AUTOMÁTICO)
            # -------------------------------------------------------------
            if 'processamento_pendente' in st.session_state and st.session_state.processamento_pendente:
                registros = st.session_state.processamento_pendente

                existe_envio_real = any(not r.get("SOMENTE_VISUALIZAR", True) for r in registros)
                if existe_envio_real and not auth_ui.verificar_credenciais_sefaz():
                    st.warning("⚠️ Credenciais da SEFAZ não validas. Por favor, autentique-se antes de continuar.")
                    st.stop()

                for idx, registro in enumerate(registros):
                    cpf_reg = re.sub(r'\D', '', str(registro['CPF'])).zfill(11)
                    schema_dinamico = f"SW_{registro.get('ORGAO')}"

                    dados_busca = novos_dados_bancario.buscar_dados_completos(conn, schema_dinamico, registro['COD_INSTITUCIONAL'])

                    if dados_busca is None or (isinstance(dados_busca, pd.DataFrame) and dados_busca.empty):
                        st.warning(f"⚠️ Dados cadastrais não encontrados no schema {schema_dinamico} para o código {registro['COD_INSTITUCIONAL']}.")
                        continue

                    payload = novos_dados_bancario.montar_json_sefaz(dados_busca)

                    st.subheader(f"JSON: {registro.get('NOME_ATUAL')}")
                    st.json(payload)

                    df_cpf_str = st.session_state.df_bancario['CPF'].astype(str)
                    mask = (df_cpf_str.str.replace(r'\D', '', regex=True).str.zfill(11) == cpf_reg) & \
                           (st.session_state.df_bancario['COD_INSTITUCIONAL'] == registro['COD_INSTITUCIONAL'])

                    if registro.get("SOMENTE_VISUALIZAR", True):
                        st.info(f"Modo Visualização: {registro.get('NOME_ATUAL')} (Não enviado à SEFAZ)")
                    else:
                        try:
                            sucesso, json_str, retorno = novos_dados_bancario.enviar_para_sefaz(payload)
                            try:
                                novos_dados_bancario.registrar_envio(conn, [registro], json_str, retorno)
                            except Exception as e_log:
                                st.warning(f"Envio efetuado, mas falhou ao gravar histórico: {e_log}")

                            if sucesso:
                                st.session_state.df_bancario.loc[mask, 'ENVIADO'] = 'SIM'
                                st.success(f"Gravado com sucesso: {registro.get('NOME_ATUAL')}")
                            else:
                                st.session_state.df_bancario.loc[mask, 'ENVIADO'] = 'ERRO'
                                st.error(f"Erro ao processar SEFAZ para {registro.get('NOME_ATUAL')}: {retorno}")
                        except Exception as e_envio:
                            st.session_state.df_bancario.loc[mask, 'ENVIADO'] = 'ERRO'
                            st.error(f"Falha na comunicação: {e_envio}")

                    st.session_state.df_bancario.loc[mask, 'ENVIAR'] = False
                    st.divider()

                del st.session_state.processamento_pendente

                if st.button("Voltar ao Painel Principal"):
                    st.session_state.pagina_atual = "painel_principal"
                    st.rerun()

            # -------------------------------------------------------------
            # TELA 2: PAINEL PRINCIPAL
            # -------------------------------------------------------------
            else:
                df_exibicao = st.session_state.df_bancario.copy()
                df_exibicao = df_exibicao.reset_index(drop=True)
                df_exibicao['_INDEX_REAL'] = df_exibicao.index

                df_exibicao['CPF'] = df_exibicao['CPF'].apply(formatar_cpf)

                if 'DATA_ENVIO' in df_exibicao.columns:
                    df_exibicao['DATA_ENVIO'] = pd.to_datetime(
                        df_exibicao['DATA_ENVIO'], errors='coerce'
                    ).dt.strftime('%d/%m/%Y %H:%M:%S').fillna('')

                df_exibicao['ENVIADO'] = df_exibicao['ENVIADO'].map({
                    'SIM': '✅ SIM', 'ERRO': '❌ ERRO', 'NÃO': '⏳ NÃO'
                }).fillna('⏳ NÃO')

                if "SOMENTE_VISUALIZAR" in df_exibicao.columns:
                    df_exibicao = df_exibicao.drop(columns=["SOMENTE_VISUALIZAR"])

                with st.form("form_lote_bancario"):
                    df_editado = st.data_editor(
                        df_exibicao,
                        key="editor_dados_bancarios",
                        column_config={
                            "ENVIAR": st.column_config.CheckboxColumn("Selecionar", default=False),
                            "DATA_ENVIO": st.column_config.TextColumn("Data de Envio", disabled=True),
                            "SEFAZ": st.column_config.TextColumn("Status SEFAZ", disabled=True),
                            "_INDEX_REAL": None
                        },
                        disabled=["ENVIADO", "SEFAZ", "ORGAO", "COD_INSTITUCIONAL", "NOME_ATUAL", "CPF", "CHAVE_FOLHA", "DATA_ENVIO"],
                        use_container_width=True,
                        hide_index=True,
                    )

                    col_btn1, col_chk, col_btn2, col_btn3 = st.columns([1.2, 1, 1.2, 1.2])
                    with col_btn1:
                        submit_button = st.form_submit_button("Confirmar Envio Selecionados")
                    with col_chk:
                        chk_visualizar = st.checkbox("Somente Visualizar?", value=True, key="chk_somente_visualizar_geral")
                    with col_btn2:
                        checar_sefaz_button = st.form_submit_button("CHECAR SEFAZ")
                    with col_btn3:
                        finalizar_button = st.form_submit_button("Finalizar e Atualizar Tela")

                if checar_sefaz_button:
                    if "ENVIAR" in df_editado.columns and "_INDEX_REAL" in df_editado.columns:
                        for _, row_tela in df_editado.iterrows():
                            idx_real = row_tela.get('_INDEX_REAL')
                            if idx_real is not None and idx_real in st.session_state.df_bancario.index:
                                st.session_state.df_bancario.loc[idx_real, 'ENVIAR'] = row_tela.get('ENVIAR', False)

                    # Garante que valores vazios/NaN não quebrem a comparação booleana
                    df_editado["ENVIAR"] = df_editado["ENVIAR"].fillna(False)
                    selecionados_checar = df_editado[df_editado["ENVIAR"] == True]

                    if not selecionados_checar.empty:
                        indices_pendentes = selecionados_checar['_INDEX_REAL'].dropna().astype(int).tolist()
                        st.success(f"Processando {len(indices_pendentes)} registros marcados para a SEFAZ.")
                    else:
                        indices_pendentes = st.session_state.df_bancario[
                            (st.session_state.df_bancario['SEFAZ'] != '✅ MATRÍCULA ATIVAA') |
                            (st.session_state.df_bancario['SEFAZ'].isna())
                        ].index.tolist()
                        #st.info("Nenhum selecionado manualmente. Processando todos os pendentes gerais.")
                        st.success(f"Nenhum selecionado manualmente. Processando todos pendentes ({len(indices_pendentes)} registros).")
                        time.sleep(2.5)

                    if indices_pendentes:
                        st.session_state.modo_passo_a_passo_ativo = False
                        st.session_state.indices_passo_a_passo = indices_pendentes
                        st.session_state.indice_passo_atual = 0
                        st.rerun()
                    else:
                        st.warning("Não há registros pendentes para processar.")

                if finalizar_button:
                    if "ENVIAR" in df_editado.columns and "_INDEX_REAL" in df_editado.columns:
                        for _, row_tela in df_editado.iterrows():
                            idx_real = row_tela.get('_INDEX_REAL')
                            if idx_real is not None and idx_real in st.session_state.df_bancario.index:
                                st.session_state.df_bancario.loc[idx_real, 'ENVIAR'] = row_tela.get('ENVIAR', False)

                    try:
                        cursor = conn.cursor()
                        user_sistema = st.session_state.get("login_atual", "SISTEMA")

                        for idx, row in st.session_state.df_bancario.iterrows():
                            status_atual = row.get('SEFAZ')
                            if status_atual and str(status_atual).strip() not in ['', 'None', 'nan', '⏳ PENDENTE']:
                                cpf_fmt = formatar_cpf_completo(row.get('CPF', ''))
                                mat = str(row.get('COD_INSTITUCIONAL', ''))
                                nome = str(row.get('NOME_ATUAL', ''))[:150]

                                sql_sync = """
                                BEGIN
                                    MERGE INTO AUDITORIA_ENVIOS_SEFAZ t
                                    USING (SELECT :cpf_fmt AS cpf, :mat AS mat FROM dual) s
                                    ON (REGEXP_REPLACE(t.CPF, '[^0-9]', '') = REGEXP_REPLACE(s.cpf, '[^0-9]', '') AND t.MATRICULA = s.mat)
                                    WHEN MATCHED THEN
                                        UPDATE SET STATUS_SEFAZ = :status, USUARIO_ENVIO = :usr
                                    WHEN NOT MATCHED THEN
                                        INSERT (ID_ENVIO, CPF, MATRICULA, NOME, STATUS_SEFAZ, USUARIO_ENVIO)
                                        VALUES (SEQ_AUD_ENVIOS_SEFAZ.NEXTVAL, :cpf_fmt, :mat, :nome, :status, :usr);
                                END;
                                """
                                cursor.execute(sql_sync, {
                                    'cpf_fmt': cpf_fmt,
                                    'mat': mat,
                                    'nome': nome,
                                    'status': str(status_atual),
                                    'usr': user_sistema
                                })
                        conn.commit()
                        cursor.close()
                    except Exception as e_sync:
                        if 'conn' in locals():
                            conn.rollback()
                        st.warning(f"Aviso na sincronização final: {e_sync}")

                    if 'df_bancario' in st.session_state and not st.session_state.df_bancario.empty:
                        st.session_state.df_bancario = atualizar_status_auditoria(conn, st.session_state.df_bancario)

                    st.rerun()

                if submit_button:
                    if "ENVIAR" in df_editado.columns and "_INDEX_REAL" in df_editado.columns:
                        for _, row_tela in df_editado.iterrows():
                            idx_real = row_tela.get('_INDEX_REAL')
                            if idx_real is not None and idx_real in st.session_state.df_bancario.index:
                                st.session_state.df_bancario.loc[idx_real, 'ENVIAR'] = row_tela.get('ENVIAR', False)

                    selecionados = st.session_state.df_bancario[st.session_state.df_bancario["ENVIAR"] == True].copy()
                    if selecionados.empty:
                        st.warning("Nenhum registro selecionado!")
                    else:
                        selecionados["SOMENTE_VISUALIZAR"] = chk_visualizar

                        if not chk_visualizar:
                            if not auth_ui.verificar_credenciais_sefaz():
                                st.stop()

                        st.session_state.processamento_pendente = selecionados.to_dict('records')
                        st.rerun()

                st.divider()

                col1, col2 = st.columns([1, 1])
                with col1:
                    cpf_busca = st.text_input("Consultar CPF avulso:", placeholder="Digite o CPF...", key="input_cpf_avulso")
                with col2:
                    btn_buscar = st.button("Buscar CPF na Competência", key="btn_buscar_cpf")

                if btn_buscar and cpf_busca:
                    st.session_state['cpf_buscado_ativo'] = ''.join(filter(str.isdigit, cpf_busca)).zfill(11)

                if st.session_state.get('cpf_buscado_ativo'):
                    cpf_limpo = st.session_state['cpf_buscado_ativo']

                    if not cpf_limpo:
                        st.warning("Por favor, informe um CPF válido contendo números.")
                        del st.session_state['cpf_buscado_ativo']
                    else:
                        mask_cpf = st.session_state.df_bancario['CPF'].astype(str).str.replace(r'\D', '', regex=True) == cpf_limpo

                        with st.spinner('Consultando CPF...'):
                            if st.session_state.df_bancario[mask_cpf].any().any():
                                st.info(f"O CPF {cpf_limpo} foi localizado na lista.")
                                st.session_state.df_bancario.loc[mask_cpf, 'ENVIAR'] = True

                                df_loc_exib = st.session_state.df_bancario[mask_cpf].copy()
                                if "SOMENTE_VISUALIZAR" in df_loc_exib.columns:
                                    df_loc_exib = df_loc_exib.drop(columns=["SOMENTE_VISUALIZAR"])

                                st.data_editor(
                                    df_loc_exib,
                                    column_config={
                                        "ENVIAR": st.column_config.CheckboxColumn("Selecionar", default=False)
                                    },
                                    hide_index=True,
                                    use_container_width=True,
                                    key=f"editor_cpf_localizado_{cpf_limpo}"
                                )
                            else:
                                df_encontrado = novos_dados_bancario.buscar_por_cpf(conn, cpf_limpo, ano, mes)
                                if df_encontrado is not None and not df_encontrado.empty:
                                    df_encontrado['ENVIAR'] = True
                                    if 'SEFAZ' not in df_encontrado.columns:
                                        df_encontrado['SEFAZ'] = '⏳ PENDENTE'
                                    
                                    # CORREÇÃO CRÍTICA DE ÍNDICES: Concatena e imediatamente reseta o índice mantendo a integridade
                                    st.session_state.df_bancario = pd.concat([st.session_state.df_bancario, df_encontrado]).drop_duplicates(subset=['CPF', 'COD_INSTITUCIONAL']).reset_index(drop=True)
                                    
                                    st.success(f"{len(df_encontrado)} registro(s) localizado(s) e adicionado(s)!")

                                    df_busc_exib = df_encontrado.copy()
                                    if "SOMENTE_VISUALIZAR" in df_busc_exib.columns:
                                        df_busc_exib = df_busc_exib.drop(columns=["SOMENTE_VISUALIZAR"])

                                    st.data_editor(
                                        df_busc_exib,
                                        column_config={
                                            "ENVIAR": st.column_config.CheckboxColumn("Selecionar", default=False)
                                        },
                                        use_container_width=True,
                                        hide_index=True,
                                        num_rows="fixed",
                                        key=f"editor_cpf_buscado_{cpf_limpo}"
                                    )
                                else:
                                    st.error("CPF não encontrado na folha desta competência.")

                        if st.button("⬅️ Voltar para lista completa", key=f"btn_voltar_lista_{cpf_limpo}"):
                            del st.session_state['cpf_buscado_ativo']
                            st.rerun()

                st.divider()
                st.subheader("🔍 Auditoria de Erros")
                df_erros = st.session_state.df_bancario[st.session_state.df_bancario['ENVIADO'] == 'ERRO']
                if not df_erros.empty:
                    cpf_err = st.selectbox("Selecione o CPF do erro:", df_erros['CPF'].unique(), key="sb_cpf_erro")
                    if st.button("Carregar Log do Servidor", key=f"btn_log_erro_{cpf_err}"):
                        st.error(f"Log: {novos_dados_bancario.buscar_detalhe_erro_no_banco(conn, cpf_err)}")
                else:
                    st.info("Nenhum erro para exibir.")
    except Exception as e:
        st.error("❌ Ocorreu um erro crítico ao renderizar a tela de Dados Bancários:")
        st.exception(e)

