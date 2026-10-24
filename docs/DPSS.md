# DPSS experimental module

The DPSS engine is an opt-in extension of the current DPS engine. It is exposed
through the WebSocket action `queue.prioritize.dpss`; it does not replace
`queue.prioritize` or the regulation queue while its reference coverage is not
validated.

## Formula and stages

```text
DPS          = (T / M) * (1 + c)
DPSS         = (T / M) * (1 + c + w*S)
final_score  = DPSS * disability_weight
```

- `T`, `M`, `c`, SWALIS, events and active status come from the audited DPS
  implementation.
- `S` must be in `[0, 1]`, where `1` is the greatest combined social and
  geographic vulnerability.
- `w` defaults to `0.25` and is accepted in `[0, 1]`. This is an experimental
  value, not a clinically or ethically validated weight.
- `disability_weight` must be in `[0, 1]` and must describe a validated health
  state mapping. A DALY is not a 0..1 weight: DALY is `YLL + YLD`, measured in
  lost healthy years. The legacy input column `daly_weight_norm` is accepted but
  explicitly reported as a terminology warning.

The A1/A2 safety band remains above the general queue. The hybrid indicator is:

```text
social = mean(valid EVFAM-BR items), when at least one item is available
       = inverted municipal INSE, otherwise
       = 0.5, when neither source is available

geographic = clip(distancia_hospital_km / 150, 0, 1)
           = 0.5, when distance is missing or invalid

S = clip(0.8*social + 0.2*geographic, 0, 1)
```

The recognized EVFAM-BR items are financial difficulty, continuous medication
use, absence of family support and housing vulnerability. Their canonical
columns are `evfam_dificuldade_financeira`,
`evfam_uso_medicamentos_continuos`, `evfam_sem_apoio_familiar` and
`evfam_vulnerabilidade_habitacional`; legacy aliases remain accepted. Each item
must already be encoded in `[0,1]` or as yes/no. Invalid values are ignored in
the row mean; if every item is absent or invalid, the INSE fallback is used.

`s_social_source`, `s_vulnerabilidade_imputada` and
`s_distancia_imputada` make the precedence and both neutral fallbacks auditable.
The DPSS runtime recalculates these components from the current request fields
and the municipal reference on every execution. It does not trust a previously
materialized final `s_vulnerabilidade`; therefore new rows and changes to
EVFAM-BR or distance take effect as soon as the repository reloads the changed
dataset. The materialized columns remain an audit snapshot and are checked
against the runtime calculation.
The ranking uses the latest complete stage (`final_score`, then DPSS, then DPS),
and every row reports `ranking_basis`, `reference_coverage`, `data_quality` and
a textual justification.

## Reference contracts

`backend/dataset/normalizado/socioeconomic_normalized.csv`:

```text
id_municipio,inse_medio,observacoes_inse,s_vulnerabilidade,source,source_year,source_version,weight_method
```

`normalizar_dataset.py` loads `backend/dataset/IBGE.csv`, converts `inse` to a
number, groups every network/location/year row by the seven-digit
`id_municipio` using the arithmetic mean, and computes the municipal fallback:

```text
S = (max(INSE_municipal) - INSE_municipal) /
    (max(INSE_municipal) - min(INSE_municipal))
```

The local `referencias/municipios_ibge.csv` adds `id_municipio` to the source
queue through a validated `municipio_norm + uf` many-to-one merge. A second
validated merge attaches `inse_medio` and `s_ibge`; the final queue field
`s_vulnerabilidade` is then produced by
`calcular_indicador_s_substituto`. For homologation, missing EVFAM-BR columns
are generated deterministically from a fixed seed, with binary probabilities
positively correlated with inverted municipal INSE. Existing EVFAM data is
never overwritten. All 941 current rows therefore use synthetic EVFAM as the
social layer and are explicitly marked by `evfam_dados_sinteticos=sim` and
`evfam_sintese_versao=correlated-inse-v1`; 20 rows have no valid distance and
use the geographic fallback `0.5`. These values are test fixtures, not observed
household facts and not evidence that EVFAM-BR was administered.

`backend/dataset/normalizado/disease_burden_normalized.csv`:

```text
cid_prefix_norm,health_state,disability_weight_norm,source,source_version,mapping_method
```

CID matching uses the single longest prefix. Ambiguous matches and invalid
values are rejected for that row. A defensible mapping needs clinical review
because GBD disability weights are attached to health states/sequelae, not
automatically to every CID diagnosis or surgical indication.

## Command

```json
{
  "id": "dpss-1",
  "action": "queue.prioritize.dpss",
  "params": {
    "as_of": "2026-10-23",
    "include_inactive": false,
    "socioeconomic_weight": 0.25
  }
}
```

The response preserves every source queue field and adds the calculation,
coverage, provenance and explanation fields. `model.clinical_use_authorized`
and `model.replaces_default_dps` remain `false` until validation is complete.

## Reactive execution

`/v1/dpss/ws?hospital=hsl` is a push-only WebSocket. A subscriber first
receives the current complete `queue.dpss.snapshot`. A background observer then
watches the source queue, clinical events, procedures, IBGE and reference CSVs.
When a signature changes it runs the normalizer with atomic file replacement,
reloads the repository, recalculates DPSS for the whole active queue and
broadcasts a new snapshot with an incremented `revision` and reason
`source_normalized`. A direct change to a normalized CSV produces reason
`normalized_dataset_changed`.

This differs from the original DPS behavior, which notices changes only on the
next request to `queue.prioritize`. The reactive service is enabled by default
outside tests and polls once per second; use `DPSS_REACTIVE_ENABLED` and
`DPSS_WATCH_INTERVAL_SECONDS` to configure it.

The command WebSocket `/ws` also accepts `queue.request.create`,
`clinical_event.create` and `procedure.upsert`. These actions validate and
atomically persist a source record, synchronously invoke the same reactive
cycle and return its published revision. The full queue is not duplicated in
the command response; subscribers receive it from `/v1/dpss/ws`. A patient has
no independent table in this dataset, so patient demographics are created as
part of `queue.request.create`.

## SWALIS inference coverage

The 924 active requests currently receive a SWALIS class and maximum wait. Six
requests that previously had no inferable `M` are covered by explicit local
rules requiring both CID and supporting clinical text: symptomatic recurrent
cholelithiasis (`C`), uncomplicated umbilical hernia (`D`), CEAP C3 chronic
venous disease (`C`), obstructive hydronephrosis (`B`) and compressive
multinodular goitre (`B`). Two requests share the cholelithiasis rule. These are
versioned prototype inferences and remain distinct from PAPRIKA weights.

The article's PAPRIKA weights were elicited from clinicians through pairwise
trade-off questions and numerically codified by 1000minds for each
procedure-specific PPT. The equal one-third component weights currently used
by this implementation were not elicited in that study and must not be
described as its medical weights. Reproducing the paper requires importing the
published procedure-specific criteria, levels and weights, mapping local data
to them, and then applying the paper's cross-procedure calibration.

## Activation gate

Activation requires all of the following:

1. document and approve the uploaded IBGE/INSE extract and the decision to mix
   2019 and 2021 rows in one arithmetic municipality mean;
2. clinically and ethically validate the EVFAM item coding, equal item weights,
   the 80/20 social/geographic split, the 150 km ceiling and neutral fallbacks;
3. validate the construction of `S`, including sensitivity and fairness
   analysis across municipality, sex, age, oncology and specialty;
4. a clinically reviewed CID-to-health-state mapping and a decision whether a
   disability-weight multiplier belongs in surgical prioritization at all;
5. elicitation/validation of `w` and the clinical factor weights;
6. retrospective comparison, verifier pass, prospective silent validation and
   governance approval;
7. explicit integration into `QueueState` if the frontend regulation queue is
   intended to use DPSS rather than the current Neco rule.
