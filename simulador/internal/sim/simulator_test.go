package sim

import (
	"bytes"
	"context"
	"errors"
	"log"
	"strings"
	"testing"
	"time"
)

// fakeAPI answers like the backend would, from scripted responses.
type fakeAPI struct {
	healthErrs []error
	snapshot   Snapshot
	entryErrs  []error // consumed one per AddEntry; nil = accept
	eventErrs  []error
	entries    []map[string]any
	events     []map[string]any
	calls      []string // "entrada:<id>" / "evento:<id>", in order
	position   int
}

func (f *fakeAPI) Health(context.Context) error {
	if len(f.healthErrs) == 0 {
		return nil
	}
	err := f.healthErrs[0]
	f.healthErrs = f.healthErrs[1:]
	return err
}

func (f *fakeAPI) Queue(context.Context) (Snapshot, error) { return f.snapshot, nil }

func next(errs *[]error) error {
	if len(*errs) == 0 {
		return nil
	}
	err := (*errs)[0]
	*errs = (*errs)[1:]
	return err
}

func (f *fakeAPI) AddEntry(_ context.Context, body map[string]any) (Entry, error) {
	if err := next(&f.entryErrs); err != nil {
		return Entry{}, err
	}
	f.entries = append(f.entries, body)
	f.calls = append(f.calls, "entrada:"+body["solicitacao_id"].(string))
	return Entry{ID: body["solicitacao_id"].(string), Position: 800, UrgencyClass: "D"}, nil
}

func (f *fakeAPI) AddEvent(_ context.Context, body map[string]any) (Entry, error) {
	if err := next(&f.eventErrs); err != nil {
		return Entry{}, err
	}
	f.events = append(f.events, body)
	f.calls = append(f.calls, "evento:"+body["solicitacao_id"].(string))
	previous := 800 - f.position
	f.position += 250
	return Entry{ID: body["solicitacao_id"].(string), Position: 800 - f.position, PreviousPosition: &previous, UrgencyClass: "C"}, nil
}

func newSimulator(api API) (*Simulator, *bytes.Buffer) {
	var out bytes.Buffer
	return New(api, NewGenerator(newRNG(), reference), log.New(&out, "", 0)), &out
}

func TestBootstrapAdotaOsPacientesDoSimuladorEContinuaANumeracao(t *testing.T) {
	api := &fakeAPI{snapshot: Snapshot{Total: 3, Entries: []Entry{
		{ID: "SOL-2025-00048", Position: 1},
		{ID: "SOL-2026-90007", PatientID: "PAC-90007", EnteredAt: "2026-10-01", Position: 40, UrgencyClass: "B"},
		{ID: "SOL-2026-90003", PatientID: "PAC-90003", Position: 90},
	}}}
	s, _ := newSimulator(api)
	if err := s.Bootstrap(context.Background()); err != nil {
		t.Fatal(err)
	}
	if s.Roster().Len() != 2 || s.Roster().Get("SOL-2025-00048") != nil {
		t.Fatalf("adotou %d", s.Roster().Len())
	}
	adopted := s.Roster().Get("SOL-2026-90007")
	if adopted.Profile != nil || adopted.Class != "B" || adopted.EnteredAt.Format(DateLayout) != "2026-10-01" {
		t.Fatalf("adotado %+v", adopted)
	}
	// a fila vem por posição; o alvo é o último criado, não o último listado
	if latest, _ := s.Roster().Latest(); latest.RequestID != "SOL-2026-90007" {
		t.Fatalf("última entrada %s", latest.RequestID)
	}
	if err := s.SendEntry(context.Background()); err != nil {
		t.Fatal(err)
	}
	if got := api.entries[0]["solicitacao_id"]; got != "SOL-2026-90008" {
		t.Fatalf("próximo id %v", got)
	}
}

func TestEntradaPulaIdQueOBackendJaTem(t *testing.T) {
	api := &fakeAPI{entryErrs: []error{&APIError{Status: 409, Detail: "já existe"}, &APIError{Status: 409}}}
	s, out := newSimulator(api)
	if err := s.SendEntry(context.Background()); err != nil {
		t.Fatal(err)
	}
	if api.entries[0]["solicitacao_id"] != "SOL-2026-90003" || s.Roster().Len() != 1 {
		t.Fatalf("entrou %v", api.entries)
	}
	if !strings.Contains(out.String(), "posição 800") {
		t.Fatalf("log %q", out.String())
	}
}

func TestEntradaRecusadaPorOutroMotivoNaoEntraNoRoster(t *testing.T) {
	api := &fakeAPI{entryErrs: []error{&APIError{Status: 400, Detail: "'idade' deve ser"}}}
	s, _ := newSimulator(api)
	err := s.SendEntry(context.Background())
	if err == nil || !strings.Contains(err.Error(), "'idade' deve ser") || s.Roster().Len() != 0 {
		t.Fatalf("erro %v, roster %d", err, s.Roster().Len())
	}
}

func TestEventoAndaAHistoriaEMostraOPulo(t *testing.T) {
	api := &fakeAPI{}
	s, out := newSimulator(api)
	s.SendEntry(context.Background())
	patient := s.Roster().Get("SOL-2026-90001")
	first := patient.Profile.Story[0]

	if err := s.SendEvent(context.Background()); err != nil {
		t.Fatal(err)
	}
	if patient.Next != 1 || patient.Position != 550 || patient.Class != "C" {
		t.Fatalf("paciente %+v", patient)
	}
	if api.events[0]["tipo_evento"] != first.Kind || api.events[0]["resultado"] != first.Result {
		t.Fatalf("evento %v", api.events[0])
	}
	if !strings.Contains(out.String(), "subiu 800 → 550 (+250)") || !strings.Contains(out.String(), "D→C") {
		t.Fatalf("log %q", out.String())
	}
}

func TestEventoVaiParaAUltimaEntrada(t *testing.T) {
	api := &fakeAPI{}
	s, _ := newSimulator(api)
	ctx := context.Background()
	s.SendEntry(ctx)
	s.SendEvent(ctx)
	s.SendEntry(ctx)
	s.SendEvent(ctx)
	s.SendEvent(ctx)
	want := []string{
		"entrada:SOL-2026-90001", "evento:SOL-2026-90001",
		"entrada:SOL-2026-90002", "evento:SOL-2026-90002", "evento:SOL-2026-90002",
	}
	if strings.Join(api.calls, " ") != strings.Join(want, " ") {
		t.Fatalf("chamadas %v", api.calls)
	}
	if s.Roster().Get("SOL-2026-90002").Next != 2 {
		t.Fatal("a última entrada anda a própria história")
	}
}

func TestQuandoAUltimaSaiDaFilaOEventoVaiParaAAnterior(t *testing.T) {
	api := &fakeAPI{eventErrs: []error{&APIError{Status: 404}}}
	s, _ := newSimulator(api)
	s.SendEntry(context.Background())
	s.SendEntry(context.Background())
	if err := s.SendEvent(context.Background()); err != nil {
		t.Fatal(err)
	}
	if s.Roster().Get("SOL-2026-90002") != nil {
		t.Fatal("a última saiu da fila e devia sair do roster")
	}
	if api.events[0]["solicitacao_id"] != "SOL-2026-90001" {
		t.Fatalf("evento foi para %v", api.events[0]["solicitacao_id"])
	}
}

func TestHistoriaAcabadaContinuaRecebendoPiora(t *testing.T) {
	api := &fakeAPI{}
	s, _ := newSimulator(api)
	s.SendEntry(context.Background())
	for range 5 { // 3 da história + 2 de piora, enquanto não chega outra entrada
		if err := s.SendEvent(context.Background()); err != nil {
			t.Fatal(err)
		}
	}
	if len(api.events) != 5 || s.Roster().Get("SOL-2026-90001").Next != 3 {
		t.Fatalf("%d eventos", len(api.events))
	}
}

func TestEventoRecusadoNaoAndaAHistoria(t *testing.T) {
	api := &fakeAPI{eventErrs: []error{errors.New("connection refused")}}
	s, _ := newSimulator(api)
	s.SendEntry(context.Background())
	if err := s.SendEvent(context.Background()); err == nil {
		t.Fatal("esperava o erro")
	}
	if s.Roster().Get("SOL-2026-90001").Next != 0 {
		t.Fatal("o passo deve ser reenviado no próximo tique")
	}
}

func TestEventoSemPacientesEsperaSemChamarOBackend(t *testing.T) {
	api := &fakeAPI{}
	s, out := newSimulator(api)
	if err := s.SendEvent(context.Background()); err != nil || len(api.events) != 0 {
		t.Fatalf("erro %v, eventos %d", err, len(api.events))
	}
	if !strings.Contains(out.String(), "evento adiado") {
		t.Fatalf("log %q", out.String())
	}
}

func TestPosicaoAnteriorDoBackendNaoEnganaOLog(t *testing.T) {
	// o paciente ficou em 30, mas o previousPosition ainda é o do evento anterior
	p := &Patient{RequestID: "SOL-2026-90001", Position: 30, Class: "A1"}
	old := 198
	line := describeMove(p, Step{Kind: "pronto_socorro", Result: "observacao"}, Entry{Position: 30, PreviousPosition: &old, UrgencyClass: "A1"})
	if !strings.Contains(line, "ficou em 30") {
		t.Fatalf("linha %q", line)
	}
}

func TestPacienteAdotadoSemPosicaoUsaADoBackend(t *testing.T) {
	p := &Patient{RequestID: "SOL-2026-90001"}
	old := 500
	line := describeMove(p, Step{Kind: "pronto_socorro", Result: "observacao"}, Entry{Position: 300, PreviousPosition: &old, UrgencyClass: "C"})
	if !strings.Contains(line, "subiu 500 → 300 (+200)") {
		t.Fatalf("linha %q", line)
	}
}

func TestDescreveQuemNaoMudou(t *testing.T) {
	p := &Patient{RequestID: "SOL-2026-90001", Position: 12, Class: "A1"}
	line := describeMove(p, Step{Kind: "contato_telefonico", Result: "relata_piora"}, Entry{Position: 12, UrgencyClass: "A1"})
	if !strings.Contains(line, "ficou em 12") || strings.Contains(line, "→") {
		t.Fatalf("linha %q", line)
	}
}

func TestEsperaOBackendSubir(t *testing.T) {
	api := &fakeAPI{healthErrs: []error{errors.New("recusada"), errors.New("recusada")}}
	s, out := newSimulator(api)
	if err := s.WaitForBackend(context.Background(), time.Millisecond); err != nil {
		t.Fatal(err)
	}
	if strings.Count(out.String(), "aguardando o backend") != 2 {
		t.Fatalf("log %q", out.String())
	}
}

func TestEsperaParaQuandoOContextoAcaba(t *testing.T) {
	api := &fakeAPI{healthErrs: []error{errors.New("recusada")}}
	s, _ := newSimulator(api)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if err := s.WaitForBackend(ctx, time.Hour); !errors.Is(err, context.Canceled) {
		t.Fatalf("erro %v", err)
	}
}

func TestRitmoPadraoEUmaEntradaA10sEUmEventoA5s(t *testing.T) {
	if DefaultConfig.EntryInterval != 10*time.Second || DefaultConfig.EventInterval != 5*time.Second {
		t.Fatalf("%+v", DefaultConfig)
	}
	if DefaultConfig.EventsPerEntry() != 2 {
		t.Fatalf("%d eventos por entrada", DefaultConfig.EventsPerEntry())
	}
}

func TestRunRecusaIntervaloZero(t *testing.T) {
	s, _ := newSimulator(&fakeAPI{})
	if err := s.Run(context.Background(), Config{EntryInterval: time.Second}); err == nil {
		t.Fatal("intervalo de evento zero")
	}
}

func TestRunMandaAPrimeiraEntradaNaHoraEOEventoSoDepoisDoIntervalo(t *testing.T) {
	api := &fakeAPI{}
	s, _ := newSimulator(api)
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	if err := s.Run(ctx, Config{EntryInterval: time.Hour, EventInterval: 100 * time.Millisecond}); err != nil {
		t.Fatal(err)
	}
	if len(api.entries) != 1 || len(api.events) != 0 {
		t.Fatalf("%d entradas, %d eventos em 50 ms", len(api.entries), len(api.events))
	}
}

func TestRunIntercalaDoisEventosNaUltimaEntradaEntreAsEntradas(t *testing.T) {
	// o ritmo da demonstração (10 s / 5 s) em escala de milissegundos
	api := &fakeAPI{}
	s, _ := newSimulator(api)
	ctx, cancel := context.WithTimeout(context.Background(), 400*time.Millisecond)
	defer cancel()
	s.Run(ctx, Config{EntryInterval: 120 * time.Millisecond, EventInterval: 60 * time.Millisecond})
	want := []string{
		"entrada:SOL-2026-90001", "evento:SOL-2026-90001", "evento:SOL-2026-90001",
		"entrada:SOL-2026-90002", "evento:SOL-2026-90002", "evento:SOL-2026-90002",
		"entrada:SOL-2026-90003",
	}
	if len(api.calls) < len(want) || strings.Join(api.calls[:len(want)], " ") != strings.Join(want, " ") {
		t.Fatalf("chamadas %v", api.calls)
	}
}

func TestChamadaLentaPulaOsTiquesEmVezDeDispararEmRajada(t *testing.T) {
	start := time.Now()
	due := start.Add(10 * time.Millisecond)
	got := advance(due, 10*time.Millisecond, start.Add(35*time.Millisecond))
	if !got.Equal(start.Add(40 * time.Millisecond)) {
		t.Fatalf("próximo tique em %s", got.Sub(start))
	}
}
