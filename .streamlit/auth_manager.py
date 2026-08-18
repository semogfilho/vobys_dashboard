# -*- coding: utf-8 -*-
import os
import toml
import hashlib

# Caminho para o arquivo users.toml dentro da pasta .streamlit
TOML_PATH = os.path.join(".streamlit", "users.toml")

def carregar_usuarios():
    """Carrega o arquivo TOML. Se não existir, cria a estrutura básica."""
    if os.path.exists(TOML_PATH):
        try:
            return toml.load(TOML_PATH)
        except Exception:
            return {"usuarios": {}}
    return {"usuarios": {}}

def salvar_usuarios(dados):
    """Grava as alterações de volta no arquivo TOML."""
    with open(TOML_PATH, "w") as f:
        toml.dump(dados, f)

def hash_senha(senha):
    """Cria um hash seguro para não guardar a senha em texto limpo."""
    return hashlib.sha256(senha.encode('utf-8')).hexdigest()

def verificar_credenciais(usuario, senha_digitada):
    """Valida se o usuário existe e se a senha está correta."""
    dados = carregar_usuarios()
    
    # Se o arquivo estiver completamente vazio, criamos um usuário padrão para você conseguir entrar
    if not dados.get("usuarios"):
        dados["usuarios"] = {
            "josegomes": {
                "senha_hash": hash_senha("admin123")
            }
        }
        salvar_usuarios(dados)
    
    user_info = dados["usuarios"].get(usuario)
    if user_info:
        return user_info.get("senha_hash") == hash_senha(senha_digitada)
    
    return False

def cadastrar_novo_usuario(usuario, senha_nova):
    """Função utilitária caso queira registrar novos logins no TOML via código."""
    dados = carregar_usuarios()
    if "usuarios" not in dados:
        dados["usuarios"] = {}
        
    dados["usuarios"][usuario] = {
        "senha_hash": hash_senha(senha_nova)
    }
    salvar_usuarios(dados)

