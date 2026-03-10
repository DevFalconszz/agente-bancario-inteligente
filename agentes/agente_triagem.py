"""
Agente de Triagem - Versão Resiliente
"""

import os
import pandas as pd
import re
from typing import Optional, Dict, Any, List
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage


class AgenteTriagem:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.cliente: Optional[Dict[str, Any]] = None
        self.tentativas_falhas = 0
        self.cpf_coletado = None
        self.data_coletada = None
        self.proximo_agente = None
        self.etapa_atual = "coleta_cpf"
        
        try:
            self.llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=self.api_key, temperature=0)
        except Exception as e:
            print(f"[ERRO CRÍTICO] Falha ao inicializar LLM na Triagem: {e}")
            self.llm = None

    def _carregar_clientes(self) -> pd.DataFrame:
        try:
            path = os.path.join(os.path.dirname(__file__), "..", "data", "clientes.csv")
            if not os.path.exists(path):
                return pd.DataFrame()
            return pd.read_csv(path, dtype=str)
        except Exception as e:
            print(f"[ERRO] Falha ao ler clientes.csv: {e}")
            return pd.DataFrame()

    def _extrair_dados(self, texto: str):
        nums = re.sub(r'\D', '', texto)
        cpf = re.search(r'\d{11}', nums)
        if cpf: self.cpf_coletado = cpf.group(0)
        
        data = re.search(r'(\d{2})[/-](\d{2})[/-](\d{4})', texto)
        if data: 
            self.data_coletada = f"{data.group(1)}/{data.group(2)}/{data.group(3)}"
        elif len(nums) == 8:
            if not self.cpf_coletado or nums != self.cpf_coletado:
                self.data_coletada = f"{nums[:2]}/{nums[2:4]}/{nums[4:]}"

    def _autenticar(self) -> Optional[Dict[str, Any]]:
        df = self._carregar_clientes()
        if df.empty: return {"error": "DATABASE_OFFLINE"}
        if not self.cpf_coletado or not self.data_coletada: return None
        
        cpf_alvo = self.cpf_coletado.zfill(11)
        for _, r in df.iterrows():
            cpf_base = re.sub(r'\D', '', str(r['cpf'])).zfill(11)
            data_base = str(r['data_nascimento']).strip()
            if cpf_base == cpf_alvo and data_base == self.data_coletada:
                return r.to_dict()
        return None

    def processar_mensagem(self, mensagem: str, historico: list) -> tuple[str, list]:
        if not self.llm:
            return "Desculpe, estou com dificuldades técnicas de conexão com meu cérebro (IA). Por favor, tente novamente em instantes.", historico

        msg_l = mensagem.lower()
        self.proximo_agente = None

        system_rules = """Você é o Agente de Triagem do Banco Digital.
        Sua ÚNICA função é autenticar o cliente e encaminhá-lo para um dos três serviços disponíveis:
        1. Crédito (Aumento de limite, Score)
        2. Entrevista (Atualização cadastral, Perfil)
        3. Câmbio (Moeda estrangeira)
        
        REGRAS:
        - NUNCA ofereça outros serviços.
        - Seja direto e profissional.
        """

        try:
            # 1. Fluxo Logado
            if self.cliente:
                classificar_prompt = f"Analise: '{mensagem}'. Responda: [MUDAR:CREDITO], [MUDAR:ENTREVISTA], [MUDAR:CAMBIO] ou [MANTER]."
                decisao = self.llm.invoke([SystemMessage(content=classificar_prompt)]).content.strip()
                
                if "[MUDAR:CREDITO]" in decisao: self.proximo_agente = "AgenteCredito"; return "", historico
                if "[MUDAR:ENTREVISTA]" in decisao: self.proximo_agente = "AgenteEntrevista"; return "", historico
                if "[MUDAR:CAMBIO]" in decisao: self.proximo_agente = "AgenteCambio"; return "", historico
                
                historico.append(HumanMessage(content=mensagem))
                res = self.llm.invoke([SystemMessage(content=system_rules + f"\nO cliente {self.cliente['nome']} está logado. Apresente Crédito, Entrevista ou Câmbio.")] + historico[-3:]).content
                historico.append(AIMessage(content=res))
                return res, historico

            # 2. Fluxo Autenticação
            historico.append(HumanMessage(content=mensagem))
            self._extrair_dados(mensagem)

            if self.cpf_coletado and self.data_coletada:
                c = self._autenticar()
                if c and isinstance(c, dict) and "error" in c:
                    return "Desculpe, nossa base de dados está temporariamente indisponível. Não consigo realizar sua autenticação agora.", historico
                
                if c:
                    self.cliente = c
                    comando = f"Sucesso! Cliente {c['nome']} autenticado. Apresente as opções: Crédito, Entrevista ou Câmbio."
                else:
                    self.tentativas_falhas += 1
                    restantes = 3 - self.tentativas_falhas
                    self.cpf_coletado = self.data_coletada = None
                    if restantes <= 0:
                        self.etapa_atual = "encerrado"
                        comando = "Limite de 3 tentativas atingido. Encerre o atendimento educadamente."
                    else:
                        comando = f"Dados não conferem. Tentativa {self.tentativas_falhas}/3. Peça CPF e Data novamente."
            elif self.cpf_coletado:
                comando = "CPF recebido. Peça a Data de Nascimento (DD/MM/AAAA)."
            else:
                comando = "Peça o CPF para iniciar."

            res = self.llm.invoke([SystemMessage(content=system_rules + f"\nORIENTAÇÃO: {comando}")] + historico[-3:]).content
            historico.append(AIMessage(content=res))
            return res, historico

        except Exception as e:
            print(f"[ERRO] Falha no processamento da Triagem: {e}")
            return "Ocorreu um erro inesperado no processamento. Por favor, reenvie sua última mensagem.", historico

    def reset(self):
        self.cliente = None; self.tentativas_falhas = 0; self.cpf_coletado = None; self.data_coletada = None; self.proximo_agente = None; self.etapa_atual = "coleta_cpf"
