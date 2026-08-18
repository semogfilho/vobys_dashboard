import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL_TESTE = "https://localhost:8443/siafe-api"

print(f"--- Iniciando teste de conectividade em: {URL_TESTE} ---")

try:
    # Aumentamos o timeout para ver se ele tenta conectar
    response = requests.get(URL_TESTE, timeout=10, verify=False)
    print(f"Sucesso! Status Code: {response.status_code}")
except requests.exceptions.ConnectionError as e:
    print("ERRO DE CONEXÃO: O túnel está na porta 8443, mas a conexão foi recusada.")
    print(f"Detalhes: {e}")
except requests.exceptions.Timeout:
    print("ERRO: Timeout. O túnel está aberto, mas o servidor não respondeu.")
except Exception as e:
    print(f"Erro inesperado: {e}")

input("\nPressione Enter para sair...")

