from flask import jsonify

from . import api
from ..data import current_repository

SORT_FIELDS = [
    "dias_em_fila",
    "idade",
    "data_entrada_fila",
    "intensidade_dor_eva",
    "solicitacao_id",
]


@api.get("/procedures")
def procedures():
    repository = current_repository()
    return jsonify({"data": repository.procedures, "total": len(repository.procedures)})


@api.get("/references/swalis")
def swalis():
    repository = current_repository()
    return jsonify({"data": repository.swalis, "total": len(repository.swalis)})


@api.get("/references/filters")
def filters():
    repository = current_repository()
    return jsonify(
        {
            "specialties": repository.specialties(),
            "priorities": repository.priorities(),
            "sort_fields": SORT_FIELDS,
        }
    )
