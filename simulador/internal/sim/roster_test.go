package sim

import "testing"

func patientWith(id string, next int) *Patient {
	return &Patient{RequestID: id, Profile: &Profiles[0], Next: next}
}

func TestAlvoEAUltimaEntrada(t *testing.T) {
	var r Roster
	r.Add(patientWith("A", 0))
	r.Add(patientWith("B", 1))
	r.Add(patientWith("C", 3)) // história acabada: ainda é o alvo, recebe piora
	got, ok := r.Latest()
	if !ok || got.RequestID != "C" {
		t.Fatalf("alvo %v", got)
	}
}

func TestRosterVazioNaoTemAlvo(t *testing.T) {
	var r Roster
	if _, ok := r.Latest(); ok {
		t.Fatal("roster vazio")
	}
}

func TestQuandoAUltimaSaiAAnteriorViraOAlvo(t *testing.T) {
	var r Roster
	r.Add(patientWith("A", 0))
	r.Add(patientWith("B", 0))
	r.Remove("B")
	r.Remove("NAO-EXISTE")
	got, _ := r.Latest()
	if r.Len() != 1 || got.RequestID != "A" || r.Get("B") != nil {
		t.Fatalf("roster %+v", r.patients)
	}
}
