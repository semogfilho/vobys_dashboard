#!/bin/bash

# Exibe o status atual do git
git status

# Adiciona todas as alterações
git add .

# Pede uma mensagem de commit ao usuário (se não digitar nada, usa uma padrão)
echo "Digite a mensagem do commit (ou aperte Enter para usar a padrão):"
read mensagem

if [ -z "$mensagem" ]; then
    mensagem="Atualização automática: $(date '+%Y-%m-%d %H:%M:%S')"
fi

# Realiza o commit
git commit -m "$mensagem"

# Envia para o GitHub na branch principal
git push origin main

echo "----------------------------------------"
echo "✅ Repositório atualizado com sucesso no GitHub!"
echo "----------------------------------------"

