# -*- coding: utf-8 -*-
import streamlit as st
import os, toml, hashlib, pandas as pd, smtplib, random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configurações de Caminho
CAMINHO_ATUAL = os.path.dirname(__file__)
CAMINHO_USERS_TOML = os.path.abspath(os.path.join(CAMINHO_ATUAL, "..", ".streamlit", "users.toml"))

def exibir_feedback():
    if "mensagem_sucesso" in st.session_state:
        st.success(st.session_state.mensagem_sucesso)
        del st.session_state.mensagem_sucesso
        
    if "senha_debug" in st.session_state:
        if st.session_state.perfil_usuario in ['a']:
            st.info(f"🔍 [DEBUG] Senha temporária ativa: **{st.session_state.senha_debug}**")
        del st.session_state.senha_debug
        
    if "mensagem_erro" in st.session_state:
        st.error(st.session_state.mensagem_erro)
        del st.session_state.mensagem_erro

exibir_feedback()

def enviar_email_senha(email_destino, senha_temp, nome, login):
    remetente = st.secrets["email"]["remetente"]
    senha_app = st.secrets["email"]["senha_app"]
    smtp_server = st.secrets["email"]["smtp_server"]
    smtp_port = int(st.secrets["email"]["smtp_port"])
 
    link = st.secrets["sistema"]["url_acesso"]
    
    corpo = f"""
Olá, {nome}!

Seus dados de usuário para acesso ao sistema NTGD:

Login: {login}
Senha: {senha_temp}

Acesse o sistema pelo link abaixo:
{link}

Esta senha é válida apenas para o seu próximo acesso.
"""
    msg = MIMEMultipart()
    msg['From'] = remetente
    msg['To'] = email_destino
    msg['Subject'] = "NTGD - Senha Temporaria de Acesso"
    msg.attach(MIMEText(corpo, 'plain'))

    try:
        server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        server.login(remetente, senha_app)
        server.sendmail(remetente, email_destino, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        st.error(f"Erro de envio (SSL): {type(e).__name__} - {str(e)}")
        return False

def pode_ver_usuario(login_alvo):
    if st.session_state.perfil_usuario in ['a', 'g']:
        return True
    return login_alvo == st.session_state.login_atual

def registrar_log_acesso(conn, login, ip_usuario="0.0.0.0"):
    cursor = conn.cursor()
    try:
        query = "INSERT INTO APP_LOG_ACESSO (USUARIO, IP_USUARIO, DATA_ACESSO) VALUES (:1, :2, SYSDATE)"
        cursor.execute(query, [login, ip_usuario])
        conn.commit()
    except Exception as e:
        print(f"Erro ao inserir log no banco: {e}")
    finally:
        cursor.close()

def carregar_usuarios():
    return toml.load(CAMINHO_USERS_TOML) if os.path.exists(CAMINHO_USERS_TOML) else {"usuario": {}}

def salvar_usuarios(dados):
    with open(CAMINHO_USERS_TOML, "w", encoding="utf-8") as f:
        toml.dump(dados, f)

def buscar_logs_usuario(conn, login):
    query = f"SELECT * FROM (SELECT TO_CHAR(DATA_ACESSO, 'DD/MM/YYYY HH24:MI:SS') AS DATA_HORA, IP_USUARIO FROM APP_LOG_ACESSO WHERE USUARIO = '{login}' ORDER BY DATA_ACESSO DESC) WHERE ROWNUM <= 10"
    return pd.read_sql(query, conn)

def render(conn, perfil_logado=None, *args, **kwargs):
    if perfil_logado is None:
        perfil_logado = st.session_state.get("perfil_usuario", "a")

    st.markdown("""<style>[data-testid="stVerticalBlock"] { gap: 0px !important; } .stButton button { height: 30px !important; }</style>""", unsafe_allow_html=True)

    st.markdown("<h2>⚙️ Gerenciamento de Usuários</h2>", unsafe_allow_html=True)
    
    aba_listar, aba_cadastrar, aba_editar = st.tabs(["📋 Lista", "➕ Cadastro", "✏️ Editar Usuário"])

    dados_toml = carregar_usuarios()
    usuarios_dict = dados_toml.get("usuario", {})

    with aba_listar:
        hierarquia = {'a': 3, 'g': 2, 'c': 1}

        for login, info in usuarios_dict.items():
            tipo_user = info.get("tipo", "c")
            nome_user = info.get("nome", "Sem Nome")
            email_user = info.get("email", "")
            esta_resetado = str(info.get("requer_reset", "nao")).lower() in ["sim", "true", "1"]
            tipo_logado = st.session_state.perfil_usuario

            if not pode_ver_usuario(login):
                continue

            pode_interagir = (hierarquia.get(tipo_logado, 1) >= hierarquia.get(tipo_user, 1)) or (tipo_logado == 'a')

            with st.container(border=True):
                c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 1.5, 1.5])
                with c1: st.markdown(f"**{nome_user}** ({login})")
                with c2: st.markdown(f"Perfil: {'Adm' if tipo_user=='a' else 'Gerente' if tipo_user=='g' else 'Comum'}")
                with c3: st.markdown(":red[🔴 Resetado]" if esta_resetado else ":green[✅ Ativo]")
                
                with c4:
                    if pode_interagir:
                        if st.button("📊 Logs", key=f"log_{login}", use_container_width=True):
                            st.session_state[f"show_log_{login}"] = True
                    else:
                        st.markdown("🚫")
                
                with c5:
                    if pode_interagir:
                        if esta_resetado and tipo_logado not in ['a','g']:
                            st.button("Solicitado", key=f"rst_{login}", disabled=True, use_container_width=True)
                        else:
                            with st.popover("🔑 Reset", use_container_width=True):
                                if st.button("Confirmar Reset", key=f"conf_{login}", type="primary"):
                                    senha_temp = str(random.randint(100000, 999999))
                                    nome_usuario = dados_toml["usuario"][login].get("nome", "Usuario")
                                    if enviar_email_senha(email_user, senha_temp, nome_usuario, login):
                                        dados_toml["usuario"][login].update({"requer_reset": "sim", "senha_hash": hashlib.sha256(senha_temp.encode()).hexdigest()})
                                        salvar_usuarios(dados_toml)
                                        st.session_state.mensagem_sucesso = f"Senha resetada! E-mail enviado para {email_user}"
                                        st.session_state.senha_debug = senha_temp
                                        st.rerun()
                    else:
                        st.markdown("🔒")

            if st.session_state.get(f"show_log_{login}"):
                st.dataframe(buscar_logs_usuario(conn, login), use_container_width=True)
                if st.button("Fechar", key=f"close_{login}"):
                    st.session_state[f"show_log_{login}"] = False
                    st.rerun()

    with aba_cadastrar:
        st.markdown("### Adicionar Novo Usuário")
        
        if st.session_state.perfil_usuario in ['a', 'g']:
            with st.form("form_cadastro"):
                novo_login = st.text_input("Login do Usuário")
                novo_nome = st.text_input("Nome Completo")
                novo_email = st.text_input("E-mail")

                if st.session_state.perfil_usuario == 'a':
                    opcoes = ["c", "g", "a"]
                else:
                    opcoes = ["c", "g"]
                
                novo_tipo = st.selectbox(
                    "Perfil", 
                    opcoes, 
                    format_func=lambda x: "Comum" if x=="c" else "Gerente" if x=="g" else "Administrador"
                )

                if st.form_submit_button("Cadastrar"):
                    if novo_login in dados_toml.get("usuario", {}):
                        st.error("Usuário já existe!")
                    elif not novo_login or not novo_nome or not novo_email:
                        st.error("Preencha todos os campos!")
                    else:
                        senha_temp = str(random.randint(100000, 999999))
                        if enviar_email_senha(novo_email, senha_temp, novo_nome, novo_login):
                            dados_toml["usuario"][novo_login] = {
                                "nome": novo_nome,
                                "email": novo_email,
                                "tipo": novo_tipo,
                                "senha_hash": hashlib.sha256(senha_temp.encode()).hexdigest(), 
                                "requer_reset": "sim"
                            }
                            salvar_usuarios(dados_toml)
                            st.session_state.mensagem_sucesso = f"Usuário {novo_login} cadastrado com sucesso!"
                            st.session_state.senha_debug = senha_temp
                            st.rerun()
                        else:
                            st.error("Erro ao enviar e-mail. Usuário não cadastrado.")
        else:
            st.warning("⚠️ Você não tem permissão para cadastrar novos usuários.")

    with aba_editar:
        st.markdown("### Editar Usuário Existente")
        
        # Exibe feedback específico da edição se houver
        if "msg_sucesso_edicao" in st.session_state:
            st.success(st.session_state.msg_sucesso_edicao)
            del st.session_state.msg_sucesso_edicao

        if st.session_state.perfil_usuario == 'a':
            if usuarios_dict:
                lista_logins = list(usuarios_dict.keys())
                usuario_selecionado = st.selectbox("Selecione o Usuário para Editar:", lista_logins, key="select_user_edit")
                
                dados_user_atual = usuarios_dict[usuario_selecionado]
                
                with st.form("form_editar_usuario"):
                    edit_nome = st.text_input("Nome Completo", value=dados_user_atual.get("nome", ""))
                    edit_email = st.text_input("E-mail", value=dados_user_atual.get("email", ""))
                    
                    tipo_atual = dados_user_atual.get("tipo", "c")
                    opcoes_edit = ["c", "g", "a"]
                    idx_tipo = opcoes_edit.index(tipo_atual) if tipo_atual in opcoes_edit else 0
                    
                    edit_tipo = st.selectbox(
                        "Perfil", 
                        opcoes_edit, 
                        index=idx_tipo,
                        format_func=lambda x: "Comum" if x=="c" else "Gerente" if x=="g" else "Administrador"
                    )

                    if st.form_submit_button("Salvar Alterações"):
                        if not edit_nome or not edit_email:
                            st.error("Preencha todos os campos obrigatórios!")
                        else:
                            dados_toml["usuario"][usuario_selecionado]["nome"] = edit_nome
                            dados_toml["usuario"][usuario_selecionado]["email"] = edit_email
                            dados_toml["usuario"][usuario_selecionado]["tipo"] = edit_tipo
                            
                            salvar_usuarios(dados_toml)
                            st.session_state.msg_sucesso_edicao = f"Usuário '{usuario_selecionado}' atualizado com sucesso!"
                            st.rerun()
            else:
                st.info("Nenhum usuário cadastrado para editar.")
        else:
            st.warning("⚠️ Apenas administradores têm permissão para editar usuários.")

