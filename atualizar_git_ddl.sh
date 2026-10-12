#!/bin/bash

# Vai para a raiz do repositório Git automaticamente
cd "$(git rev-parse --show-toplevel)" || exit 1

echo "=== 1. Iniciando extração dos DDLs do Oracle ==="
/home/jose.gomes/miniconda3/envs/vobys_env/bin/python exportar_ddl_completo.py

if [ $? -ne 0 ]; then
    echo "[ERRO] A extração do DDL falhou. O processo do Git foi abortado."
    exit 1
fi

echo -e "\n=== 2. Verificando alterações no Git para DDLs ==="
# Adiciona explicitamente apenas a pasta de DDLs
git add db/ddl/

# Verifica se há alterações em staged apenas para a pasta db/ddl
git diff --cached --quiet db/ddl/

if [ $? -eq 0 ]; then
    echo "[INFO] Nenhuma alteração estrutural nos DDLs foi detectada desde o último commit."
else
    echo "[INFO] Alterações detectadas nos DDLs. Gerando commit automático..."
    DATA_HORA=$(date '+%Y-%m-%d %H:%M:%S')
    git commit -m "chore(ddl): atualização automática dos DDLs - $DATA_HORA"
    
    echo "[INFO] Enviando alterações para o repositório remoto (git push)..."
    # Descobre o branch atual de forma compatível com versões antigas do Git
    CURRENT_BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || git rev-parse --abbrev-ref HEAD)
    
    git push origin "$CURRENT_BRANCH"
    
    if [ $? -eq 0 ]; then
        echo "[SUCESSO] Commit e Push realizados com sucesso!"
    else
        echo "[AVISO] O commit local foi feito, mas houve um erro ao tentar o push remoto."
        exit 1
    fi
fi

echo "=== Processo concluído com sucesso! ==="
