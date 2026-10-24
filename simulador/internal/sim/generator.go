package sim

import (
	"fmt"
	"math/rand/v2"
	"time"
)

// DateLayout is the dataset's date format.
const DateLayout = "2006-01-02"

// Patient is a request the simulator created (or found in the queue on start)
// and keeps worsening. Profile is nil for one adopted from a previous run: its
// story is lost, so it only receives Worsening steps.
type Patient struct {
	RequestID string
	PatientID string
	Name      string
	Profile   *Profile
	EnteredAt time.Time
	Next      int // index of the next story step
	Position  int
	Class     string
}

// StoryLeft says whether the patient still has scripted steps.
func (p *Patient) StoryLeft() bool {
	return p.Profile != nil && p.Next < len(p.Profile.Story)
}

// Generator builds the request bodies. The clock is the backend's fixed
// reference date, not today: no date may be later than it.
type Generator struct {
	rng       *rand.Rand
	reference time.Time
}

func NewGenerator(rng *rand.Rand, reference time.Time) *Generator {
	return &Generator{rng: rng, reference: reference}
}

// RequestID and PatientID number the simulator's records apart from the
// dataset's (SOL-AAAA-NNNNN, PAC-NNNNN never start with 9 there).
func RequestID(seq int) string { return fmt.Sprintf("SOL-2026-9%04d", seq) }
func PatientID(seq int) string { return fmt.Sprintf("PAC-9%04d", seq) }

func pick[T any](rng *rand.Rand, items []T) T { return items[rng.IntN(len(items))] }

func between(rng *rand.Rand, low, high int) int { return low + rng.IntN(high-low+1) }

// NewEntry returns the patient and the /fila/entradas body (a fila_cirurgica.csv row).
func (g *Generator) NewEntry(seq int) (*Patient, map[string]any) {
	profile := &Profiles[g.rng.IntN(len(Profiles))]
	sex := profile.Sex
	if sex == "" {
		sex = pick(g.rng, []string{"F", "M"})
	}
	first := pick(g.rng, MaleNames)
	if sex == "F" {
		first = pick(g.rng, FemaleNames)
	}
	middle := pick(g.rng, Surnames)
	last := pick(g.rng, Surnames)
	for last == middle {
		last = pick(g.rng, Surnames)
	}
	name := fmt.Sprintf("%s %s %s", first, middle, last)
	city := pick(g.rng, Cities)
	entered := g.reference.AddDate(0, 0, -between(g.rng, 20, 420))

	patient := &Patient{
		RequestID: RequestID(seq),
		PatientID: PatientID(seq),
		Name:      name,
		Profile:   profile,
		EnteredAt: entered,
	}
	oncological := "nao"
	if profile.Oncological {
		oncological = "sim"
	}
	body := map[string]any{
		"solicitacao_id":        patient.RequestID,
		"paciente_id":           patient.PatientID,
		"nome_paciente":         name,
		"sexo":                  sex,
		"idade":                 between(g.rng, profile.AgeMin, profile.AgeMax),
		"municipio":             city.Name,
		"uf":                    "RS",
		"distancia_hospital_km": city.KM,
		"procedimento_id":       profile.ProcedureID,
		"cid_principal":         profile.CID,
		"cid_descricao":         profile.CIDDescription,
		"asa":                   between(g.rng, 1, 3),
		"comorbidades":          pick(g.rng, Comorbidities),
		"intensidade_dor_eva":   between(g.rng, profile.PainMin, profile.PainMax),
		"limitacao_funcional":   pick(g.rng, profile.Limitations),
		"justificativa_clinica": pick(g.rng, profile.Notes),
		"data_entrada_fila":     entered.Format(DateLayout),
		"prioridade_regulacao":  pick(g.rng, ManualPriorities),
		"flag_oncologico":       oncological,
	}
	return patient, body
}

// NextEvent returns the patient's next story step, or a Worsening one when the
// story is over, and the /fila/eventos body. It does not advance the story:
// the caller does that once the backend accepted the event.
func (g *Generator) NextEvent(p *Patient) (Step, bool, map[string]any) {
	scripted := p.StoryLeft()
	var step Step
	var date time.Time
	if scripted {
		step = p.Profile.Story[p.Next]
		// story steps go back in time from the reference, in order, a week or so apart
		date = g.reference.AddDate(0, 0, -(len(p.Profile.Story)-p.Next-1)*7-g.rng.IntN(3))
	} else {
		step = pick(g.rng, Worsening)
		date = g.reference.AddDate(0, 0, -g.rng.IntN(6))
	}
	if date.Before(p.EnteredAt) {
		date = p.EnteredAt
	}
	body := map[string]any{
		"solicitacao_id": p.RequestID,
		"paciente_id":    p.PatientID,
		"data_evento":    date.Format(DateLayout),
		"tipo_evento":    step.Kind,
		"resultado":      step.Result,
		"descricao":      step.Description,
		"origem":         step.Origin,
	}
	if step.Value != 0 {
		body["valor_numerico"] = step.Value
	}
	return step, scripted, body
}
