import os
import requests
import logging
import pandas as pd
from typing import Optional, Dict, Any
from src.services.deduplication import generate_transaction_hash

logger = logging.getLogger("PluggyService")

class PluggyService:
    """
    Conector com a API Open Finance da Pluggy para busca automatizada de transações e extratos bancários.
    """
    BASE_URL = "https://api.pluggy.ai"

    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None):
        self.client_id = client_id or os.getenv("PLUGGY_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("PLUGGY_CLIENT_SECRET", "")
        self.api_key: Optional[str] = None

    def get_auth_token(self) -> str:
        """
        Autentica na API da Pluggy e obtém o apiKey (JWT) para as chamadas subsequentes.
        """
        if self.api_key:
            return self.api_key

        if not self.client_id or not self.client_secret:
            raise ValueError("Credenciais da Pluggy (CLIENT_ID / CLIENT_SECRET) não configuradas.")

        url = f"{self.BASE_URL}/auth"
        payload = {
            "clientId": self.client_id,
            "clientSecret": self.client_secret
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            self.api_key = data.get("apiKey")
            return self.api_key
        except Exception as e:
            logger.error(f"Erro ao autenticar na Pluggy: {e}")
            raise RuntimeError(f"Falha na autenticação da Pluggy: {e}")

    def fetch_accounts(self, item_id: Optional[str] = None) -> list:
        """
        Lista todas as contas bancárias conectadas ou vinculadas a um item_id.
        """
        token = self.get_auth_token()
        url = f"{self.BASE_URL}/accounts"
        params = {}
        if item_id:
            params["itemId"] = item_id

        headers = {
            "X-API-KEY": token,
            "Accept": "application/json"
        }

        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            return response.json().get("results", [])
        except Exception as e:
            logger.error(f"Erro ao buscar contas na Pluggy: {e}")
            return []

    def fetch_transactions(self, from_date: str, to_date: Optional[str] = None, account_id: Optional[str] = None) -> pd.DataFrame:
        """
        Busca transações de contas conectadas na Pluggy no intervalo de datas especificado (YYYY-MM-DD).
        Retorna DataFrame padronizado: ['Data', 'Descricao', 'Valor', 'Categoria', 'Tipo', 'Forma_Pagamento', 'Hash']
        """
        token = self.get_auth_token()
        url = f"{self.BASE_URL}/transactions"
        
        headers = {
            "X-API-KEY": token,
            "Accept": "application/json"
        }

        accounts_to_query = [account_id] if account_id else [acc["id"] for acc in self.fetch_accounts()]
        if not accounts_to_query:
            # Tenta buscar transações globais se não houver ID específico de conta
            accounts_to_query = [None]

        all_records = []

        for acc in accounts_to_query:
            params: Dict[str, Any] = {
                "from": from_date,
                "pageSize": 500
            }
            if to_date:
                params["to"] = to_date
            if acc:
                params["accountId"] = acc

            try:
                response = requests.get(url, headers=headers, params=params, timeout=20)
                if response.status_code == 200:
                    results = response.json().get("results", [])
                    for trx in results:
                        amount = float(trx.get("amount", 0.0))
                        date_str = str(trx.get("date", ""))[:10]
                        desc = trx.get("description") or trx.get("descriptionRaw") or "Transação Pluggy"
                        category_info = trx.get("category", "") or "Outros"
                        payment_type = trx.get("paymentData", {}).get("paymentMethod") if trx.get("paymentData") else "Open Finance"
                        
                        tipo = "Receita" if amount > 0 else "Despesa"
                        valor = abs(amount)

                        all_records.append({
                            "Data": date_str,
                            "Descricao": desc.strip(),
                            "Valor": valor,
                            "Categoria": category_info,
                            "Tipo": tipo,
                            "Forma_Pagamento": payment_type or "Open Finance"
                        })
            except Exception as e:
                logger.error(f"Erro ao buscar transações da conta {acc}: {e}")

        df = pd.DataFrame(all_records)
        if not df.empty:
            df["Hash"] = df.apply(lambda r: generate_transaction_hash(r["Data"], r["Valor"], r["Descricao"]), axis=1)
        else:
            df = pd.DataFrame(columns=['Data', 'Descricao', 'Valor', 'Categoria', 'Tipo', 'Forma_Pagamento', 'Hash'])

        return df
