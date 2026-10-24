"""WebSocket contracts for source dataset ingestion."""


class FakeIngestion:
    def __init__(self):
        self.calls = []

    def create_request(self, payload):
        self.calls.append(("request", payload))
        return {"accepted": True, "entity": "queue_request", "id": payload["solicitacao_id"]}

    def create_event(self, payload):
        self.calls.append(("event", payload))
        return {"accepted": True, "entity": "clinical_event", "id": payload["evento_id"]}

    def upsert_procedure(self, payload):
        self.calls.append(("procedure", payload))
        return {"accepted": True, "entity": "procedure", "id": payload["procedimento_id"]}


def test_comandos_websocket_encaminham_entidades_para_ingestao(app, pedir, monkeypatch):
    fake = FakeIngestion()
    monkeypatch.setitem(app.extensions, "dataset_ingestion", fake)

    request = pedir(
        "queue.request.create",
        request={"solicitacao_id": "SOL-NOVA", "paciente_id": "PAC-NOVO"},
    )
    event = pedir(
        "clinical_event.create",
        event={"evento_id": "EVT-NOVO", "solicitacao_id": "SOL-NOVA"},
    )
    procedure = pedir(
        "procedure.upsert",
        procedure={"procedimento_id": "PROC-NOVO", "risco_cirurgico": 3},
    )

    assert request["id"] == "SOL-NOVA"
    assert event["id"] == "EVT-NOVO"
    assert procedure["id"] == "PROC-NOVO"
    assert [kind for kind, _ in fake.calls] == ["request", "event", "procedure"]


def test_welcome_anuncia_acoes_de_ingestao(conversa):
    ws = conversa()
    assert {
        "queue.request.create",
        "clinical_event.create",
        "procedure.upsert",
    } <= set(ws.welcome["actions"])
