"""
Agente de Câmbio - Versão Resiliente
"""

import requests
from typing import Dict, Any
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage


class AgenteCambio:
    def __init__(self, api_key: str, cliente_dados: Dict[str, Any]):
        self.api_key = api_key
        self.cliente = cliente_dados
        self.proximo_agente = None
        
        try:
            self.llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=self.api_key, temperature=0)
        except:
            self.llm = None

    def _obter_cotacao(self, moeda: str = "USD") -> str:
        try:
            url = f"https://economia.awesomeapi.com.br/json/last/{moeda.upper()}-BRL"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            key = f"{moeda.upper()}BRL"
            if key in data:
                return f"R$ {float(data[key]['bid']):.2f}"
            return "indisponível"
        except Exception as e:
            print(f"[ERRO] Falha ao obter cotação ({moeda}): {e}")
            return "indisponível"

    def processar_mensagem(self, mensagem: str, historico: list) -> tuple[str, list]:
        if not self.llm:
            return "Desculpe, o serviço de câmbio está em manutenção no momento.", []

        msg_l = mensagem.lower()
        
        try:
            # Lógica de moeda
            moeda = "USD"; nome = "Dólar"
            if "euro" in msg_l: moeda = "EUR"; nome = "Euro"
            elif "libra" in msg_l: moeda = "GBP"; nome = "Libra"
            
            valor = self._obter_cotacao(moeda)
            
            if valor == "indisponível":
                prompt = f"Informe ao {self.cliente.get('nome', 'Cliente')} que o serviço de cotação para {nome} está instável agora. Peça para tentar mais tarde e diga que ele voltará ao menu principal."
            else:
                prompt = f"Informe ao {self.cliente.get('nome', 'Cliente')} que o {nome} está custando {valor} agora. Seja breve e diga que ele será redirecionado para o menu principal."
            
            res = self.llm.invoke([SystemMessage(content=prompt)]).content
            self.proximo_agente = "AgenteTriagem"
            return res, []
        except Exception as e:
            print(f"[ERRO] Falha no processamento do Câmbio: {e}")
            self.proximo_agente = "AgenteTriagem"
            return "Ocorreu um erro ao consultar o câmbio. Redirecionando você ao menu inicial...", []
