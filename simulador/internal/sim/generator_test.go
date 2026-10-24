package sim

import (
	"math/rand/v2"
	"regexp"
	"slices"
	"strings"
	"testing"
	"time"
)

var reference = time.Date(2026, 10, 23, 0, 0, 0, 0, time.UTC)

func newRNG() *rand.Rand { return rand.New(rand.NewPCG(1, 2)) }

func newGenerator() *Generator { return NewGenerator(newRNG(), reference) }

func date(t *testing.T, value any) time.Time {
	t.Helper()
	parsed, err := time.Parse(DateLayout, value.(string))
	if err != nil {
		t.Fatalf("data %v: %v", value, err)
	}
	return parsed
}

func TestIdsDoSimuladorNaoColidemComODataset(t *testing.T) {
	if RequestID(7) != "SOL-2026-90007" || PatientID(7) != "PAC-90007" {
		t.Fatalf("got %s %s", RequestID(7), PatientID(7))
	}
}

func TestEntradaTemOsCamposObrigatoriosEmDominio(t *testing.T) {
	gen := newGenerator()
	required := []string{
		"solicitacao_id", "paciente_id", "nome_paciente", "sexo", "idade", "municipio", "uf",
		"procedimento_id", "cid_principal", "justificativa_clinica", "data_entrada_fila",
	}
	for seq := 1; seq <= 300; seq++ {
		patient, body := gen.NewEntry(seq)
		for _, key := range required {
			if value, ok := body[key]; !ok || value == "" {
				t.Fatalf("entrada %d sem %s", seq, key)
			}
		}
		if body["solicitacao_id"] != patient.RequestID || body["paciente_id"] != patient.PatientID {
			t.Fatalf("ids do corpo e do paciente divergem")
		}
		p := patient.Profile
		if age := body["idade"].(int); age < p.AgeMin || age > p.AgeMax {
			t.Fatalf("idade %d fora de %d–%d", age, p.AgeMin, p.AgeMax)
		}
		if pain := body["intensidade_dor_eva"].(int); pain < p.PainMin || pain > p.PainMax {
			t.Fatalf("dor %d fora de %d–%d", pain, p.PainMin, p.PainMax)
		}
		if !slices.Contains(p.Limitations, body["limitacao_funcional"].(string)) {
			t.Fatalf("limitação %v fora do perfil", body["limitacao_funcional"])
		}
		if sex := body["sexo"]; sex != "F" && sex != "M" || (p.Sex != "" && sex != p.Sex) {
			t.Fatalf("sexo %v para %s", sex, p.Label)
		}
		if !slices.Contains(ManualPriorities, body["prioridade_regulacao"].(string)) {
			t.Fatalf("prioridade %v", body["prioridade_regulacao"])
		}
		if flag := body["flag_oncologico"]; (flag == "sim") != strings.HasPrefix(p.CID, "C") {
			t.Fatalf("flag %v contradiz o CID %s", flag, p.CID)
		}
		entered := date(t, body["data_entrada_fila"])
		if entered.After(reference) || entered.Before(reference.AddDate(0, 0, -420)) {
			t.Fatalf("entrada em %s", entered.Format(DateLayout))
		}
		if !entered.Equal(patient.EnteredAt) {
			t.Fatalf("data do corpo e do paciente divergem")
		}
	}
}

func TestEntradasCobremTodosOsPerfis(t *testing.T) {
	gen := newGenerator()
	seen := map[string]bool{}
	for seq := 1; seq <= 300; seq++ {
		patient, _ := gen.NewEntry(seq)
		seen[patient.Profile.Label] = true
	}
	if len(seen) != len(Profiles) {
		t.Fatalf("só %d de %d perfis em 300 entradas", len(seen), len(Profiles))
	}
}

func TestNomeTemTresPartesSemAcentoNemSobrenomeRepetido(t *testing.T) {
	gen := newGenerator()
	plain := regexp.MustCompile(`^[A-Za-z]+ [A-Za-z]+ [A-Za-z]+$`)
	for seq := 1; seq <= 50; seq++ {
		_, body := gen.NewEntry(seq)
		name := body["nome_paciente"].(string)
		if !plain.MatchString(name) {
			t.Fatalf("nome %q", name)
		}
		if parts := strings.Fields(name); parts[1] == parts[2] {
			t.Fatalf("sobrenome repetido: %q", name)
		}
	}
}

func TestEventosDaHistoriaSeguemEmOrdemAteAReferencia(t *testing.T) {
	gen := newGenerator()
	for seq := 1; seq <= 100; seq++ {
		patient, _ := gen.NewEntry(seq)
		var last time.Time
		for i := range patient.Profile.Story {
			step, scripted, body := gen.NextEvent(patient)
			if !scripted || step != patient.Profile.Story[i] {
				t.Fatalf("passo %d de %s fora de ordem", i, patient.Profile.Label)
			}
			when := date(t, body["data_evento"])
			if when.After(reference) || when.Before(patient.EnteredAt) {
				t.Fatalf("evento em %s, entrada em %s", when.Format(DateLayout), patient.EnteredAt.Format(DateLayout))
			}
			if when.Before(last) {
				t.Fatalf("evento %d antes do anterior", i)
			}
			last = when
			patient.Next++
		}
	}
}

func TestEventosRecentesContamComoIdaRecenteAoPS(t *testing.T) {
	// o backend só conta PS/internação dos últimos 180 dias
	gen := newGenerator()
	patient, _ := gen.NewEntry(1)
	_, _, body := gen.NextEvent(patient)
	if when := date(t, body["data_evento"]); when.Before(reference.AddDate(0, 0, -180)) {
		t.Fatalf("evento em %s fica fora da janela", when.Format(DateLayout))
	}
}

func TestNextEventNaoAvancaAHistoria(t *testing.T) {
	gen := newGenerator()
	patient, _ := gen.NewEntry(1)
	gen.NextEvent(patient)
	if patient.Next != 0 {
		t.Fatalf("Next = %d", patient.Next)
	}
}

func TestHistoriaAcabadaRecebePiora(t *testing.T) {
	gen := newGenerator()
	patient, _ := gen.NewEntry(1)
	patient.Next = len(patient.Profile.Story)
	step, scripted, body := gen.NextEvent(patient)
	if scripted || !slices.Contains(Worsening, step) {
		t.Fatalf("esperava um passo de piora, veio %+v", step)
	}
	if _, ok := body["valor_numerico"]; ok {
		t.Fatalf("piora sem valor não manda valor_numerico")
	}
}

func TestPacienteAdotadoSoRecebePiora(t *testing.T) {
	gen := newGenerator()
	adopted := &Patient{RequestID: "SOL-2026-90001", PatientID: "PAC-90001", EnteredAt: reference.AddDate(0, 0, -2)}
	_, scripted, body := gen.NextEvent(adopted)
	if scripted {
		t.Fatal("paciente sem perfil não tem história")
	}
	if when := date(t, body["data_evento"]); when.Before(adopted.EnteredAt) {
		t.Fatalf("evento em %s antes da entrada", when.Format(DateLayout))
	}
}

func TestInternacaoLevaOsDiasEmValorNumerico(t *testing.T) {
	gen := newGenerator()
	patient := &Patient{RequestID: "SOL-2026-90001", PatientID: "PAC-90001", Profile: &Profiles[0], EnteredAt: reference.AddDate(0, 0, -300)}
	patient.Next = 1 // colelitíase: o segundo passo é a internação
	step, _, body := gen.NextEvent(patient)
	if step.Kind != "internacao" || body["valor_numerico"] != 4.0 {
		t.Fatalf("passo %+v, corpo %v", step, body)
	}
}

func TestDumpTrazOsEventosQueCadaEntradaRecebe(t *testing.T) {
	batch := Dump(newGenerator(), 5, 2)
	if len(batch.Entries) != 5 || len(batch.Events) != 10 {
		t.Fatalf("%d entradas e %d eventos", len(batch.Entries), len(batch.Events))
	}
	for i, event := range batch.Events {
		if event["solicitacao_id"] != batch.Entries[i/2]["solicitacao_id"] {
			t.Fatalf("evento %d é de %v", i, event["solicitacao_id"])
		}
	}
}

func TestDumpAlemDaHistoriaMandaPiora(t *testing.T) {
	batch := Dump(newGenerator(), 1, 5)
	if len(batch.Events) != 5 {
		t.Fatalf("%d eventos", len(batch.Events))
	}
}
