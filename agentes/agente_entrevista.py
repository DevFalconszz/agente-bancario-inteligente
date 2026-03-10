"""
Agente de Entrevista - Versão Resiliente
"""

import os
import pandas as pd
import re
from typing import Optional, Dict, Any, List
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage


class AgenteEntrevista:
    CLIENTES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "clientes.csv")
    
    def __init__(self, api_key: str, cliente_dados: Dict[str, Any]):
        self.api_key = api_key
        self.cliente = cliente_dados
        self.respostas = {}
        self.etapa_atual = "pergunta_renda"
        self.proximo_agente = None
        
        try:
            self.llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=self.api_key, temperature=0)
        except:
            self.llm = None
        
        self.system_prompt = f"Analista Financeiro. Entrevistado: {self.cliente.get('nome', 'Cliente')}. REGRAS: 1 pergunta por vez, direto, humano."

    def _extrair_valor(self, texto: str) -> float:
        nums = re.sub(r'[^\d,.]', '', texto).replace(',', '.')
        try: return float(nums)
        except: return 0.0

    def _calcular_novo_score(self) -> int:
        try:
            renda = self.respostas.get('renda', 0.0)
            despesas = self.respostas.get('despesas', 0.0)
            emprego = self.respostas.get('emprego', 'desempregado')
            dependentes = self.respostas.get('dependentes', 0)
            dividas = self.respostas.get('dividas', 'não')

            p_renda = 30
            p_emprego = {"formal": 300, "autônomo": 200, "desempregado": 0}
            p_dep = {0: 100, 1: 80, 2: 60, "3+": 30}
            p_div = {"sim": -100, "não": 100}

            f_renda = (renda / (despesas + 1)) * p_renda
            score = f_renda + p_emprego.get(emprego, 0) + p_div.get(dividas, 100)
            dep_key = dependentes if dependentes in [0, 1, 2] else "3+"
            score += p_dep.get(dep_key, 30)

            return int(min(max(score, 0), 1000))
        except Exception as e:
            print(f"[ERRO] Falha no cálculo do score: {e}")
            return int(self.cliente.get('score', 500))

    def _atualizar_score_base(self, novo_score: int):
        try:
            if not os.path.exists(self.CLIENTES_PATH): return
            df = pd.read_csv(self.CLIENTES_PATH, dtype=str)
            cpf = re.sub(r'\D', '', str(self.cliente.get("cpf", ""))).zfill(11)
            df["cpf_l"] = df["cpf"].str.replace(r'\D', '', regex=True).str.zfill(11)
            if cpf in df["cpf_l"].values:
                df.loc[df["cpf_l"] == cpf, "score"] = str(novo_score)
                df.drop(columns=["cpf_l"]).to_csv(self.CLIENTES_PATH, index=False)
                self.cliente["score"] = novo_score
        except Exception as e:
            print(f"[ERRO] Falha ao salvar novo score: {e}")

    def processar_mensagem(self, mensagem: str, historico: list) -> tuple[str, list]:
        if not self.llm:
            return "Desculpe, o sistema de análise de perfil está indisponível agora.", historico

        msg_l = mensagem.lower()
        try:
            if self.etapa_atual == "pergunta_renda" and len(self.respostas) == 0:
                if not any(c.isdigit() for char in mensagem for c in char):
                    res = "Iniciando a entrevista para atualizar seu score. Primeiro, qual sua renda mensal líquida?"
                    historico.append(AIMessage(content=res)); return res, historico

            historico.append(HumanMessage(content=mensagem))

            if self.etapa_atual == "pergunta_renda":
                self.respostas['renda'] = self._extrair_valor(mensagem)
                self.etapa_atual = "pergunta_emprego"
                comando = "Pergunte o Tipo de Emprego (Formal, Autônomo ou Desempregado)."
            elif self.etapa_atual == "pergunta_emprego":
                if "formal" in msg_l: self.respostas['emprego'] = "formal"
                elif "autônomo" in msg_l or "autonomo" in msg_l: self.respostas['emprego'] = "autônomo"
                else: self.respostas['emprego'] = "desempregado"
                self.etapa_atual = "pergunta_despesas"
                comando = "Pergunte as despesas fixas mensais."
            elif self.etapa_atual == "pergunta_despesas":
                self.respostas['despesas'] = self._extrair_valor(mensagem)
                self.etapa_atual = "pergunta_dependentes"
                comando = "Pergunte o número de dependentes."
            elif self.etapa_atual == "pergunta_dependentes":
                nums = re.findall(r'\d+', mensagem)
                self.respostas['dependentes'] = int(nums[0]) if nums else 0
                self.etapa_atual = "pergunta_dividas"
                comando = "Pergunte se possui dívidas ativas."
            elif self.etapa_atual == "pergunta_dividas":
                self.respostas['dividas'] = "sim" if "sim" in msg_l else "não"
                novo_score = self._calcular_novo_score()
                self._atualizar_score_base(novo_score)
                self.proximo_agente = "AgenteCredito"
                return "", historico

            res = self.llm.invoke([SystemMessage(content=f"{self.system_prompt}\nORIENTAÇÃO: {comando}")] + historico[-4:]).content
            historico.append(AIMessage(content=res))
            return res, historico
        except Exception as e:
            print(f"[ERRO] Falha no processamento da Entrevista: {e}")
            return "Tive um problema ao processar sua resposta. Pode repetir?", historico
