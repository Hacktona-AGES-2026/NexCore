from flask import jsonify

from . import api
from ..data import current_repository


@api.get("/procedimentos")
def procedures():
    repository = current_repository()
    return jsonify({"dados": repository.procedures, "total": len(repository.procedures)})


@api.get("/referencias/swalis")
def swalis():
    repository = current_repository()
    return jsonify({"dados": repository.swalis, "total": len(repository.swalis)})


@api.get("/referencias/filtros")
def filters():
    repository = current_repository()
    return jsonify(
        {
            "especialidades": repository.specialties(),
            "prioridades": repository.priorities(),
            "ordenacoes": ["dias_em_fila", "idade", "data_entrada_fila",
                           "intensidade_dor_eva", "solicitacao_id"],
        }
    )
