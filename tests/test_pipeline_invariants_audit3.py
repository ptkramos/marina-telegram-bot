"""Auditoria #3 — invariantes do pipeline de resposta.

`process_incoming_batch` tem ~880 linhas e dois blocos de finalização quase
idênticos (um no caminho de avatar, outro no caminho principal). Eles divergiram
em silêncio: o caminho de batch deixou de gravar a coluna `model`, deixou de
checar `u_id` antes de usá-lo, e media latência só no caminho ao vivo.

Nenhum teste de comportamento pegaria isso — a resposta chega ao Patrick
normalmente, só o dado de auditoria fica errado. Então estes testes são
estruturais: leem a AST do `bot.py` e falham se um caminho novo esquecer o
mesmo detalhe.
"""
import ast
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

BOT_SRC = (BASE_DIR / "bot.py").read_text(encoding="utf-8")
BOT_AST = ast.parse(BOT_SRC)


def _funcao(nome: str) -> ast.AsyncFunctionDef:
    for no in ast.walk(BOT_AST):
        if isinstance(no, (ast.AsyncFunctionDef, ast.FunctionDef)) and no.name == nome:
            return no
    raise AssertionError(f"função {nome} não encontrada em bot.py")


def _chamadas_de(escopo, nome_attr: str) -> list[ast.Call]:
    achadas = []
    for no in ast.walk(escopo):
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute):
            if no.func.attr == nome_attr:
                achadas.append(no)
    return achadas


class ModelColumnInvariantTests(unittest.TestCase):
    """Toda fala da Marina persistida deve registrar qual LLM a gerou.

    A coluna `model` foi criada no Patch 018 exatamente para auditar isso. O
    export de 21/09 mostrou "[model: -]" nas respostas entregues via batch,
    contra "mistral-nemo" nas ao vivo — o caminho de batch chamava
    `db.adicionar_mensagem` direto, sem passar `model=`.
    """

    def test_toda_insercao_de_assistant_passa_model(self):
        faltando = []
        for chamada in _chamadas_de(BOT_AST, "adicionar_mensagem"):
            kwargs = {kw.arg for kw in chamada.keywords if kw.arg}
            valores_role = [kw.value for kw in chamada.keywords if kw.arg == "role"]
            eh_assistant = any(
                isinstance(v, ast.Constant) and v.value == "assistant"
                for v in valores_role
            )
            if eh_assistant and "model" not in kwargs:
                faltando.append(chamada.lineno)
        self.assertEqual(
            faltando, [],
            f"adicionar_mensagem(role='assistant') sem model= nas linhas {faltando}; "
            "sem isso a resposta grava model=NULL e o export mostra '[model: -]'")

    def test_registrar_mensagem_assistente_tem_default_de_model(self):
        """O caminho ao vivo depende desse default — se cair, volta o NULL."""
        import inspect
        from memory import MemoryManager
        fonte = inspect.getsource(MemoryManager.registrar_mensagem_assistente)
        self.assertIn("LLM_MODEL", fonte,
                      "registrar_mensagem_assistente precisa cair em settings.LLM_MODEL")


class ConversationIdInvariantTests(unittest.TestCase):
    """`apply_plan_effects` recebe `conversation_id` — não pode vir None."""

    def test_apply_plan_effects_sempre_guardado_por_checagem_de_u_id(self):
        pipeline = _funcao("process_incoming_batch")
        chamadas = _chamadas_de(pipeline, "apply_plan_effects")
        self.assertGreater(len(chamadas), 0, "o pipeline deve aplicar efeitos do plano")

        # Cada chamada precisa estar sob um if que mencione u_id.
        linhas = BOT_SRC.splitlines()
        desprotegidas = []
        for chamada in chamadas:
            protegida = False
            for i in range(chamada.lineno - 2, max(pipeline.lineno, chamada.lineno - 6), -1):
                linha = linhas[i].strip()
                if linha.startswith("if ") and "u_id" in linha:
                    protegida = True
                    break
            if not protegida:
                desprotegidas.append(chamada.lineno)
        self.assertEqual(
            desprotegidas, [],
            f"apply_plan_effects sem checagem de u_id nas linhas {desprotegidas}")


class LatencyTelemetryInvariantTests(unittest.TestCase):
    """A latência real precisa ser medida nos dois caminhos de entrega.

    Entregas de batch são as mais relevantes para calibrar latência humana —
    são justamente as que a política de availability adiou de propósito. Medir
    só o caminho ao vivo enviesa a amostra para os turnos mais rápidos.
    """

    def test_record_actual_latency_nao_fica_exclusivo_do_caminho_ao_vivo(self):
        pipeline = _funcao("process_incoming_batch")
        chamadas = _chamadas_de(pipeline, "record_actual_latency")
        self.assertGreaterEqual(len(chamadas), 1)

        # Nenhuma chamada deve estar aninhada sob um `elif sent_mid:` — esse era
        # o bug: o ramo de batch nunca chegava lá.
        linhas = BOT_SRC.splitlines()
        for chamada in chamadas:
            trecho = [linhas[i].strip()
                      for i in range(max(0, chamada.lineno - 5), chamada.lineno)]
            self.assertFalse(
                any(t.startswith("elif sent_mid") for t in trecho),
                f"record_actual_latency na linha {chamada.lineno} está sob "
                "'elif sent_mid' — entregas de batch ficariam sem telemetria")


class PipelineExitInvariantTests(unittest.TestCase):
    """Saídas antecipadas não podem perder a fala do Patrick.

    Verificado nesta auditoria: quando a availability defere, o pipeline
    retorna antes de persistir — mas a mensagem já foi gravada em `conversas` e
    o item do batch guarda `conversation_message_id`. Este teste fixa esse
    contrato: o item precisa referenciar a conversa, senão um batch que morre
    (FAILED/SUPERSEDED) levaria a fala do Patrick com ele.
    """

    def test_item_de_batch_referencia_a_conversa(self):
        import inspect
        import pending_response
        fonte = inspect.getsource(pending_response)
        self.assertIn("conversation_message_id", fonte,
                      "o item do batch deve referenciar a mensagem persistida")


if __name__ == "__main__":
    unittest.main()
