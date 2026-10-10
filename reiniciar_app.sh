#!/bin/bash
# Encerra qualquer Streamlit ativo
pkill -9 -f streamlit

# Ativa o ambiente virtual e sobe o app de produção na porta 8501
source /home/jose.gomes/miniconda3/bin/activate vobys_env
nohup streamlit run app.py --server.port 8501 --server.address 0.0.0.0 > app_8501.log 2>&1 &

# Sobe o sandbox de menu dinâmico na porta 8502
nohup streamlit run app_menu.py --server.port 8502 --server.address 0.0.0.0 > app_8502.log 2>&1 &

echo "Serviços reiniciados nas portas 8501 e 8502!"

