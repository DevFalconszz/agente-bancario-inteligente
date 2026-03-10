"""
Agente de Crédito - Versão Resiliente
"""

import os
import pandas as pd
import re
from datetime import datetime
from typing import Optional, Dict, Any, List
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage


class AgenteCredito:
    def __init__(self, api_key: str, cliente_dados: Dict[str, Any], veio_da_entrevista: bool = False):
        self.api_key = api_key
        self.cliente = cliente_dados
        self.veio_da_entrevista = veio_da_entrevista
        self.etapa_atual = "menu_inicial"
        self.proximo_agente = None
        
        # Arquivos
        self.DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
        self.SCORE_LIMITE_PATH = os.path.join(self.DATA_DIR, "score_limite.csv")
        self.SOLICITACOES_PATH = os.path.join(self.DATA_DIR, "solicitacoes_aumento_limite.csv")
        self.CLIENTES_PATH = os.path.join(self.DATA_DIR, "clientes.csv")

        try:
            df = pd.read_csv(self.CLIENTES_PATH, dtype=str)
            cpf = re.sub(r'\D', '', str(self.cliente.get('cpf', ''))).zfill(11)
            df["cpf_l"] = df["cpf"].str.replace(r'\D', '', regex=True).str.zfill(11)
            r = df[df["cpf_l"] == cpf].iloc[0]
            self.limite_atual = float(str(r['limite_atual']).replace(',', '.'))
            self.score = int(float(str(r['score'])))
            self.cpf = cpf
        except Exception as e:
            print(f"[ERRO] Falha ao inicializar dados no Crédito: {e}")
            self.limite_atual = 0.0; self.score = 0; self.cpf = "0"
            
        try:
            self.llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=self.api_key, temperature=0)
        except:
            self.llm = None

    def _obter_max(self) -> float:
        try:
            if not os.path.exists(self.SCORE_LIMITE_PATH): return 0.0
            df = pd.read_csv(self.SCORE_LIMITE_PATH)
            for _, r in df.iterrows():
                if int(r['score_minimo']) <= self.score <= int(r['score_maximo']): return float(r['limite_maximo'])
            return 0.0
        except Exception as e:
            print(f"[ERRO] Falha ao obter limite máximo: {e}")
            return 0.0

    def _registrar(self, val: float, st: str):
        try:
            d = pd.DataFrame([{"cpf_cliente": self.cpf, "data_hora_solicitacao": datetime.now().isoformat(), "limite_atual": self.limite_atual, "novo_limite_solicitado": val, "status_pedido": st}])
            d.to_csv(self.SOLICITACOES_PATH, mode='a', header=not os.path.exists(self.SOLICITACOES_PATH), index=False)
        except Exception as e:
            print(f"[ERRO] Falha ao registrar solicitação: {e}")

    def _atualizar_base(self, novo: float):
        try:
            if not os.path.exists(self.CLIENTES_PATH): return False
            df = pd.read_csv(self.CLIENTES_PATH, dtype=str)
            df["c_l"] = df["cpf"].str.replace(r'\D', '', regex=True).str.zfill(11)
            if self.cpf in df["c_l"].values:
                df.loc[df["c_l"] == self.cpf, "limite_atual"] = f"{novo:.2f}"
                df.drop(columns=["c_l"]).to_csv(self.CLIENTES_PATH, index=False)
                self.limite_atual = novo
                return True
        except Exception as e:
            print(f"[ERRO] Falha ao atualizar clientes.csv: {e}")
        return False

    def processar_mensagem(self, mensagem: str, historico: list) -> tuple[str, list]:
        if not self.llm:
            return "Desculpe, o sistema de análise de crédito está temporariamente fora do ar. Tente novamente mais tarde.", historico

        msg_l = mensagem.lower()
        self.proximo_agente = None

        try:
            # 1. Roteamento Inteligente
            solicitar_aumento = any(p in msg_l for p in ["aumento", "subir", "quero", "mudar", "alterar", "para", "solicitar"]) and "limite" in msg_l
            
            if mensagem.strip() and not solicitar_aumento:
                if "score" in msg_l and ("aumentar" in msg_l or "melhorar" in msg_l or "subir" in msg_l):
                    self.proximo_agente = "AgenteEntrevista"; return "", historico

                classificar_prompt = f"Analise: '{mensagem}'. [MUDAR:CAMBIO], [MUDAR:ENTREVISTA] ou [MANTER]?"
                decisao = self.llm.invoke([SystemMessage(content=classificar_prompt)]).content.strip()
                if "[MUDAR:CAMBIO]" in decisao: self.proximo_agente = "AgenteCambio"; return "", historico
                elif "[MUDAR:ENTREVISTA]" in decisao: self.proximo_agente = "AgenteEntrevista"; return "", historico

            # 2. Fluxo Principal
            if (self.veio_da_entrevista or not mensagem.strip()) and len(historico) == 0:
                self.veio_da_entrevista = False
                res = f"Olá, {self.cliente.get('nome', 'Cliente')}! Sou o Gerente de Crédito. Limite atual: R$ {self.limite_atual:.2f}, Score: {self.score}. Como posso ajudar?"
                historico.append(AIMessage(content=res)); return res, historico

            historico.append(HumanMessage(content=mensagem))
            max_p = self._obter_max()
            comando = ""

            nums = re.findall(r'(\d+(?:\.\d{3})*(?:,\d{2})?)', mensagem)
            valor_solicitado = None
            if nums:
                try:
                    raw_num = nums[-1].replace(".", "").replace(",", ".")
                    valor_solicitado = float(raw_num)
                except: pass

            if (solicitar_aumento or self.etapa_atual == "aguardando_valor") and valor_solicitado:
                if valor_solicitado <= max_p:
                    if self._atualizar_base(valor_solicitado):
                        self._registrar(valor_solicitado, "aprovado")
                        comando = f"APROVADO: Novo limite de R$ {valor_solicitado:.2f} ATIVADO. Parabenize o cliente."
                        self.etapa_atual = "menu_inicial"
                    else:
                        return "Tivemos um problema técnico ao gravar seu novo limite. Por favor, tente novamente em alguns segundos.", historico
                else:
                    self._registrar(valor_solicitado, "rejeitado")
                    comando = f"NEGADO: Valor R$ {valor_solicitado:.2f} excede o máximo de R$ {max_p:.2f} (Score {self.score}). Ofereça a entrevista."
                    self.etapa_atual = "sugerir_entrevista"
            elif solicitar_aumento:
                self.etapa_atual = "aguardando_valor"
                comando = "Pergunte o valor desejado para o novo limite total."
            else:
                comando = "Responda à dúvida de crédito ou peça para o cliente descrever o que precisa."

            res = self.llm.invoke([SystemMessage(content=f"Você é o Gerente de Crédito. Limite R$ {self.limite_atual:.2f}, Score {self.score}. REGRAS: Direto, humano, sem burocracia. ORIENTAÇÃO: {comando}")] + historico[-3:]).content
            historico.append(AIMessage(content=res))
            return res, historico

        except Exception as e:
            print(f"[ERRO] Falha no processamento do Crédito: {e}")
            return "Ocorreu um erro ao processar sua solicitação de crédito. Vamos tentar de novo?", historico
