package sim

import (
	"regexp"
	"slices"
	"strings"
	"testing"
)

// alarm is the official verifier's KW_ALARME (backend/dataset/verificar_fila_priorizada.py).
// A calm profile whose note matched it would not enter as "sem urgência
// clínica" and would not start at the bottom of the queue.
var alarm = regexp.MustCompile(`encarcer|estrangul|colangite|icter|pancreatite|enterorragia|melena|hematemese|` +
	`suboclus|perda ponderal|disfagia|sepse|hidronefrose|perda de funcao|transfund|hemoptise|rouquidao|` +
	`linfonodo.*(?:fixo|palpavel)|sangramento espontaneo|acamad|ulcera de pressao|quedas de repeticao|` +
	`glaucoma facomorfico|retencao de co2|dano neurologico|psa em elevacao|dessaturacao|angina em repouso|` +
	`sincope|crescimento rapido|retencao urinaria aguda|massa anexial|ca-125`)

// urgentCID is the verifier's CID_URGENTE: never calm, whatever the pain.
var urgentCID = []string{"I200", "K403", "K400", "K420", "K430", "K800", "N132", "I832"}

func TestPassosDasHistoriasUsamODominioDoBackend(t *testing.T) {
	steps := slices.Clone(Worsening)
	for _, p := range Profiles {
		steps = append(steps, p.Story...)
	}
	for _, s := range steps {
		results, ok := EventResults[s.Kind]
		if !ok {
			t.Errorf("tipo_evento %q fora do domínio", s.Kind)
			continue
		}
		if !slices.Contains(results, s.Result) {
			t.Errorf("resultado %q não vale para %s", s.Result, s.Kind)
		}
		valued := s.Kind == "hba1c" || s.Kind == "internacao"
		if !valued && s.Value != 0 {
			t.Errorf("%s/%s tem valor_numerico, que só vale para hba1c e internacao", s.Kind, s.Result)
		}
		if s.Kind == "hba1c" && s.Value == 0 {
			t.Errorf("hba1c sem valor_numerico")
		}
		if s.Description == "" || s.Origin == "" {
			t.Errorf("%s/%s sem descrição ou origem", s.Kind, s.Result)
		}
	}
}

func TestHistoriasCobremOsEventosQueCadaEntradaRecebe(t *testing.T) {
	// no ritmo padrão chegam 2 eventos por entrada; o pulo precisa estar neles
	// (quem confere o tamanho do pulo é o teste de contrato do backend)
	for _, p := range Profiles {
		if len(p.Story) < DefaultConfig.EventsPerEntry() {
			t.Errorf("%s tem %d passos", p.Label, len(p.Story))
		}
	}
}

func TestHistoriasNaoRepetemEvento(t *testing.T) {
	// o backend marca evento de conteúdo igual como duplicata e não o conta
	for _, p := range Profiles {
		seen := map[string]bool{}
		for _, s := range p.Story {
			if seen[s.Description] {
				t.Errorf("%s repete %q", p.Label, s.Description)
			}
			seen[s.Description] = true
		}
	}
}

func TestPerfisCalmosEntramSemUrgenciaClinica(t *testing.T) {
	calm := 0
	for _, p := range Profiles {
		mild := !slices.ContainsFunc(p.Limitations, func(l string) bool { return l != "nenhuma" && l != "leve" })
		if p.Oncological || p.PainMax > 3 || !mild {
			continue
		}
		calm++
		cid := strings.ReplaceAll(p.CID, ".", "")
		if slices.Contains(urgentCID, cid) {
			t.Errorf("%s: CID %s é urgente para o verificador", p.Label, p.CID)
		}
		for _, note := range p.Notes {
			if alarm.MatchString(strings.ToLower(note)) {
				t.Errorf("%s: justificativa com palavra de alarme: %q", p.Label, note)
			}
		}
	}
	if calm < 3 {
		t.Errorf("só %d perfis calmos: os pulos do fim da fila são o que mais aparece", calm)
	}
}

func TestPerfisSaoCoerentes(t *testing.T) {
	limitations := []string{"nenhuma", "leve", "moderada", "grave"}
	for _, p := range Profiles {
		if _, ok := Procedures[p.ProcedureID]; !ok {
			t.Errorf("%s: procedimento %s fora do catálogo", p.Label, p.ProcedureID)
		}
		if p.Oncological != strings.HasPrefix(p.CID, "C") {
			t.Errorf("%s: oncológico deve vir do CID (%s)", p.Label, p.CID)
		}
		if p.PainMin < 0 || p.PainMax > 10 || p.PainMin > p.PainMax {
			t.Errorf("%s: dor %d–%d", p.Label, p.PainMin, p.PainMax)
		}
		if p.AgeMin < 18 || p.AgeMax > 92 || p.AgeMin > p.AgeMax {
			t.Errorf("%s: idade %d–%d", p.Label, p.AgeMin, p.AgeMax)
		}
		if p.Sex != "" && p.Sex != "F" && p.Sex != "M" {
			t.Errorf("%s: sexo %q", p.Label, p.Sex)
		}
		for _, l := range p.Limitations {
			if !slices.Contains(limitations, l) {
				t.Errorf("%s: limitação %q", p.Label, l)
			}
		}
		if len(p.Notes) == 0 {
			t.Errorf("%s sem justificativa", p.Label)
		}
	}
}
