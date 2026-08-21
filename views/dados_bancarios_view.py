# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import requests
import urllib3
import re
import time
from datetime import datetime
from auditoria.novos_dados_bancario import listar_novatos_bancario, atualizar_status_auditoria
from concurrent.futures import ThreadPoolExecutor, as_completed

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def formatar_cpf(val_cpf):
    """Formata uma string de CPF para o padrão 000.000.000-00 de forma segura"""
    if not val_cpf or pd.isna(val_cpf):
        return ""
    # Remove tudo que não for dígito e garante 11 caracteres com zeros à esquerda
    digitos = re.sub(r'\D', '', str(val_cpf)).zfill(11)
    if len(digitos) == 11:
        return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
    return str(val_cpf)

def consultar_credor_sefaz_individual(ano, cpf_ou_credor, matricula_para_conferir):
    """Consulta o credor na SEFAZ e valida se a matrícula específica existe nos dados bancários (tratando strings com ';')"""
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

        # Autenticação
        payload_auth = {"usuario": usuario, "senha": senha}
        r_auth = session.post(f"{BASE_URL}/auth", json=payload_auth, timeout=15)
        r_auth.raise_for_status()

        token = r_auth.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})

        # Consulta no endpoint oficial com timeout ampliado para 30 segundos
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

                # Valida se a matrícula limpa consta nos dados bancários, dividindo por ';' se necessário
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

                # --- TRAVA FLEXÍVEL (Apenas CPFs da Exceção e Órgão SEDUC) ---
                if 'CPF' in df_temp.columns and 'ORGAO' in df_temp.columns:
                    cpfs_excecao = [
                        '05602146342', '04227244323', '00306962322',
                        '00352388366', '00352234300', '00522894356', '01461363306'
                    ]

                    # Limpa o CPF para comparação garantida
                    df_temp['CPF_LIMPO'] = df_temp['CPF'].astype(str).str.replace(r'\D', '', regex=True).str.zfill(11)

                    mask_cpfs = df_temp['CPF_LIMPO'].isin(cpfs_excecao)
                    mask_seduc = df_temp['ORGAO'].astype(str).str.upper() == 'SEDUC'

                    df_temp = df_temp.drop(columns=['CPF_LIMPO'], errors='ignore')
                # -----------------------------------------------------------

                if 'SEFAZ' not in df_temp.columns:
                    df_temp['SEFAZ'] = '⏳ PENDENTE'
                st.session_state.df_bancario = df_temp
                st.session_state.last_params = (ano, mes)

        if not st.session_state.df_bancario.empty:
            if "ENVIAR" not in st.session_state.df_bancario.columns:
                st.session_state.df_bancario["ENVIAR"] = False
            if "SEFAZ" not in st.session_state.df_bancario.columns:
                st.session_state.df_bancario["SEFAZ"] = '⏳ PENDENTE'

            st.session_state.df_bancario = st.session_state.df_bancario.sort_values(by=["ORGAO", "CPF"])

            # -------------------------------------------------------------
            # TELA 1: PROCESSAMENTO EM LOTE
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
                
                # Formata o CPF corretamente para exibição amigável
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
                            "SEFAZ": st.column_config.TextColumn("Status SEFAZ", disabled=True)
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
                    if "ENVIAR" in df_editado.columns:
                        st.session_state.df_bancario["ENVIAR"] = df_editado["ENVIAR"]

                    df_atual = st.session_state.df_bancario
                    indices_marcados = df_atual[df_atual["ENVIAR"] == True].index.tolist()

                    if indices_marcados:
                        indices_pendentes = indices_marcados
                    else:
                        nao_enviado_ou_erro = df_atual['ENVIADO'].isin(['NÃO', '⏳ NÃO', 'ERRO']) | df_atual['ENVIADO'].isna()
                        nao_ativo = df_atual['SEFAZ'] != '✅ MATRÍCULA ATIVA'
                        nao_sim = df_atual['ENVIADO'] != 'SIM'
                        indices_pendentes = df_atual[nao_enviado_ou_erro & nao_ativo & nao_sim].index.tolist()

                    total_pendentes = len(indices_pendentes)

                    if total_pendentes == 0:
                        st.info("Não há registros pendentes de checagem na SEFAZ!")
                    else:
                        progress_bar = st.progress(0)
                        status_text = st.empty()

                        user_sistema = st.session_state.get("login_atual", "SISTEMA")

                        def processar_item_sefaz(idx, cpf_cru, matricula_atual, nome_atual):
                            print(f"\n--- INICIANDO ANÁLISE DO CPF ---")
                            print(f"CPF bruto recebido: {cpf_cru} | Nome: {nome_atual}")
                            input("[DEBUG] Pressione ENTER para limpar o CPF...")

                            digitos_puros = re.sub(r'\D', '', str(cpf_cru)).zfill(11)
                            print(f"-> Digitos puros obtidos: {digitos_puros}")
                            input("[DEBUG] Pressione ENTER para validar tamanho e repetição...")

                            if len(digitos_puros) != 11 or len(set(digitos_puros)) == 1:
                                print("-> FALHA: Tamanho inválido ou dígitos repetidos.")
                                return idx, "CPF INVÁLIDO"
                            
                            print("-> Tamanho OK (11 dígitos).")
                            input("[DEBUG] Pressione ENTER para converter em lista de inteiros...")

                            nums = [int(dig) for dig in digitos_puros]
                            print(f"-> Lista de números: {nums}")
                            input("[DEBUG] Pressione ENTER para calcular o 1º Dígito Verificador...")

                            # 1º Dígito Verificador
                            soma1 = sum(nums[i] * (i + 1) for i in range(9))
                            resto1 = soma1 % 11
                            if resto1 == 10: 
                                resto1 = 0
                                
                            print(f"-> 1º DV: Soma = {soma1} | Resto % 11 = {resto1} | Dígito no CPF = {nums[9]}")
                            input("[DEBUG] Pressione ENTER para comparar o 1º Dígito...")

                            if resto1 != nums[9]: 
                                print("-> FALHA: 1º Dígito Verificador não bateu!")
                                return idx, "CPF INVÁLIDO"
                                
                            print("-> 1º Dígito APROVADO!")
                            input("[DEBUG] Pressione ENTER para calcular o 2º Dígito Verificador...")

                            # 2º Dígito Verificador
                            soma2 = sum(nums[i] * i for i in range(10))
                            resto2 = soma2 % 11
                            if resto2 == 10: 
                                resto2 = 0
                                
                            print(f"-> 2º DV: Soma = {soma2} | Resto % 11 = {resto2} | Dígito no CPF = {nums[10]}")
                            input("[DEBUG] Pressione ENTER para comparar o 2º Dígito e finalizar...")

                            if resto2 != nums[10]:
                                print("-> FALHA: 2º Dígito Verificador não bateu!")
                                return idx, "CPF INVÁLIDO"
                            
                            print("-> SUCESSO ABSOLUTO: CPF Válido!")
                            
                            p_cpf_fmt = f"{digitos_puros[:3]}.{digitos_puros[3:6]}.{digitos_puros[6:9]}-{digitos_puros[9:]}"
                            p_cpf_limpo = digitos_puros
                            p_mat = str(matricula_atual)
                            p_nome = str(nome_atual)
                            p_usr = str(user_sistema)

                            res_visual = consultar_credor_sefaz_individual(ano, p_cpf_limpo, p_mat)
                            p_status = str(res_visual)

                            try:
                                cursor = conn.cursor()
                                sql_block = """
                                BEGIN
                                    DELETE FROM AUDITORIA_ENVIOS_SEFAZ
                                    WHERE REGEXP_REPLACE(CPF, '[^0-9]', '') = :cpf
                                      AND MATRICULA = :mat;

                                    INSERT INTO AUDITORIA_ENVIOS_SEFAZ (ID_ENVIO, CPF, MATRICULA, NOME, STATUS_SEFAZ, USUARIO_ENVIO)
                                    VALUES (SEQ_AUD_ENVIOS_SEFAZ.NEXTVAL, :cpf_fmt, :mat, :nome, :status, :usr);
                                END;
                                """
                                cursor.execute(sql_block, {
                                    'cpf': p_cpf_limpo,
                                    'cpf_fmt': p_cpf_fmt,
                                    'mat': p_mat,
                                    'nome': p_nome,
                                    'status': p_status,
                                    'usr': p_usr
                                })
                                conn.commit()
                                cursor.close()
                            except Exception as e_db:
                                conn.rollback()
                                raise e_db

                            return idx, res_visual

                        max_workers = min(5, total_pendentes)
                        concluidos = 0

                        with ThreadPoolExecutor(max_workers=max_workers) as executor:
                            future_to_idx = {}
                            for idx in indices_pendentes:
                                row = st.session_state.df_bancario.loc[idx]
                                cpf_cru = row.get('CPF', '')
                                matricula_atual = row.get('COD_INSTITUCIONAL', '')
                                nome_atual = row.get('NOME_ATUAL', 'Sem Nome')

                                future = executor.submit(processar_item_sefaz, idx, cpf_cru, matricula_atual, nome_atual)
                                future_to_idx[future] = idx

                            for future in as_completed(future_to_idx):
                                concluidos += 1
                                percentual = int((concluidos / total_pendentes) * 100)
                                progress_bar.progress(percentual)
                                status_text.text(f"Consultando SEFAZ ({concluidos}/{total_pendentes}) em paralelo...")

                                try:
                                    idx, res_visual = future.result()
                                    st.session_state.df_bancario.loc[idx, 'SEFAZ'] = res_visual
                                except Exception as e_db:
                                    st.error(f"❌ Erro em um dos registros durante o processamento paralelo.")
                                    st.exception(e_db)
                                    st.stop()

                        progress_bar.empty()
                        status_text.empty()

                        # ---> ATUALIZAÇÃO AUTOMÁTICA ADICIONADA AQUI <---
                        if 'df_bancario' in st.session_state and not st.session_state.df_bancario.empty:
                            st.session_state.df_bancario = atualizar_status_auditoria(conn, st.session_state.df_bancario)
                            carregar_dados_bancarios.clear()

                        st.success("Checagem em lote na SEFAZ concluída e tela atualizada!")
                        st.rerun()

                if submit_button:
                    if "ENVIAR" in df_editado.columns:
                        st.session_state.df_bancario["ENVIAR"] = df_editado["ENVIAR"]

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

                if finalizar_button:
                    if "ENVIAR" in df_editado.columns:
                        st.session_state.df_bancario["ENVIAR"] = df_editado["ENVIAR"]

                    if 'df_bancario' in st.session_state and not st.session_state.df_bancario.empty:
                        st.session_state.df_bancario = atualizar_status_auditoria(conn, st.session_state.df_bancario)

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
                        df_cpf_str = st.session_state.df_bancario['CPF'].astype(str)
                        mask_cpf = df_cpf_str.str.replace(r'\D', '', regex=True).str.zfill(11) == cpf_limpo

                        barra_avulsa = st.progress(0)
                        status_avulsa = st.empty()

                        status_avulsa.text("🔍 Conectando e localizando CPF na competência...")
                        barra_avulsa.progress(40)
                        time.sleep(0.2)

                        status_avulsa.text("🔄 Validando status e consultando SEFAZ...")
                        barra_avulsa.progress(80)

                        if st.session_state.df_bancario[mask_cpf].any().any():
                            barra_avulsa.progress(100)
                            status_avulsa.text("✅ CPF localizado com sucesso na lista!")
                            time.sleep(0.3)
                            barra_avulsa.empty()
                            status_avulsa.empty()

                            st.info(f"O CPF {cpf_limpo} foi localizado na lista.")
                            st.session_state.df_bancario.loc[mask_cpf, 'ENVIAR'] = True

                            df_loc_exib = st.session_state.df_bancario[mask_cpf].copy()
                            df_loc_exib['CPF'] = df_loc_exib['CPF'].apply(formatar_cpf)
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
                            barra_avulsa.progress(100)
                            status_avulsa.text("✅ Busca avulsa concluída!")
                            time.sleep(0.3)
                            barra_avulsa.empty()
                            status_avulsa.empty()

                            if df_encontrado is not None and not df_encontrado.empty:
                                df_encontrado['ENVIAR'] = True
                                if 'SEFAZ' not in df_encontrado.columns:
                                    df_encontrado['SEFAZ'] = '⏳ PENDENTE'
                                st.session_state.df_bancario = pd.concat([st.session_state.df_bancario, df_encontrado]).drop_duplicates(subset=['CPF', 'COD_INSTITUCIONAL'])
                                st.success(f"{len(df_encontrado)} registro(s) localizado(s) e adicionado(s)!")

                                df_busc_exib = df_encontrado.copy()
                                df_busc_exib['CPF'] = df_busc_exib['CPF'].apply(formatar_cpf)
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

