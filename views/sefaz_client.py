import requests


class SefazClient:

  def __init__(self, base_url: str, client_id: str = None, secret: str = None):
    # Garante que a url_base não termine com barra para evitar duplicação
    self.base_url = base_url.rstrip("/")
    self.session = requests.Session()
    self.token = None

  def autenticar(self, auth_endpoint: str, credentials: dict):
    """Realiza a autenticação e injeta o token Bearer no header da sessão."""
    url = f"{self.base_url}/{auth_endpoint.lstrip('/')}"
    response = self.session.post(url, json=credentials)
    response.raise_for_status()

    # Ajuste conforme a chave real retornada pela API da SEFAZ
    self.token = response.json().get("token")
    self.session.headers.update({
        "Authorization": f"Bearer {self.token}",
        "Content-Type": "application/json",
    })

  def transmitir(self, endpoint: str, payload: dict) -> requests.Response:
    """Método genérico e seguro para envio de dados para qualquer endpoint."""
    if not self.token:
      raise PermissionError(
          "Cliente não autenticado. Chame o método autenticar primeiro."
      )

    url = f"{self.base_url}/{endpoint.lstrip('/')}"
    response = self.session.post(url, json=payload)
    return response

