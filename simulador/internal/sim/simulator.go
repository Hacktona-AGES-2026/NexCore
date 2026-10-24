package sim

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"
	"regexp"
	"sort"
	"strconv"
	"time"
)

// Config is the pace: a new entry every EntryInterval and, starting one
// EventInterval after the first entry, an event for the latest entry every
// EventInterval.
type Config struct {
	EntryInterval time.Duration
	EventInterval time.Duration
}

// DefaultConfig is the demo's pace: an entry every 10 s, an event every 5 s,
// so each entry gets two events (at +5 s and +10 s) before the next arrives.
var DefaultConfig = Config{EntryInterval: 10 * time.Second, EventInterval: 5 * time.Second}

// EventsPerEntry is how many events an entry gets before the next one arrives.
func (c Config) EventsPerEntry() int {
	if c.EventInterval <= 0 {
		return 0
	}
	return int(c.EntryInterval / c.EventInterval)
}

// maxIDRetries bounds how many ids SendEntry skips when the backend says one exists.
const maxIDRetries = 20

var simulatedID = regexp.MustCompile(`^SOL-2026-9(\d{4})$`)

// Simulator sends mock entries and events to the backend on one schedule, all
// from one goroutine: no locks, and the roster always sees the backend's answer
// to the previous call before the next one.
type Simulator struct {
	api    API
	gen    *Generator
	log    *log.Logger
	roster Roster
	seq    int // last simulated sequence number used
}

func New(api API, gen *Generator, logger *log.Logger) *Simulator {
	return &Simulator{api: api, gen: gen, log: logger}
}

// Roster exposes the patients, for tests and the final summary.
func (s *Simulator) Roster() *Roster { return &s.roster }

// WaitForBackend polls /api/health until it answers or ctx ends.
func (s *Simulator) WaitForBackend(ctx context.Context, every time.Duration) error {
	for {
		err := s.api.Health(ctx)
		if err == nil {
			return nil
		}
		s.log.Printf("aguardando o backend: %v", err)
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(every):
		}
	}
}

// Bootstrap reads the queue so a restart neither reuses ids (409) nor forgets
// the patients it created before. Those come back in the order they were
// numbered, so the latest is the last one created, and without their story:
// they only get Worsening steps.
func (s *Simulator) Bootstrap(ctx context.Context) error {
	snapshot, err := s.api.Queue(ctx)
	if err != nil {
		return fmt.Errorf("lendo a fila: %w", err)
	}
	type adopted struct {
		seq     int
		patient *Patient
	}
	var found []adopted
	for _, e := range snapshot.Entries {
		match := simulatedID.FindStringSubmatch(e.ID)
		if match == nil {
			continue
		}
		seq, _ := strconv.Atoi(match[1])
		entered, err := time.Parse(DateLayout, e.EnteredAt)
		if err != nil {
			entered = s.gen.reference
		}
		found = append(found, adopted{seq, &Patient{
			RequestID: e.ID, PatientID: e.PatientID, Name: e.Name,
			EnteredAt: entered, Position: e.Position, Class: e.UrgencyClass,
		}})
	}
	sort.Slice(found, func(i, j int) bool { return found[i].seq < found[j].seq })
	for _, a := range found {
		s.roster.Add(a.patient)
		s.seq = a.seq
	}
	s.log.Printf("fila com %d solicitações; %d do simulador já estavam lá", snapshot.Total, s.roster.Len())
	return nil
}

// SendEntry creates one patient. An id the backend already has is skipped.
func (s *Simulator) SendEntry(ctx context.Context) error {
	for range maxIDRetries {
		s.seq++
		patient, body := s.gen.NewEntry(s.seq)
		entry, err := s.api.AddEntry(ctx, body)
		var refused *APIError
		if errors.As(err, &refused) && refused.Status == http.StatusConflict {
			continue
		}
		if err != nil {
			return fmt.Errorf("entrada %s: %w", patient.RequestID, err)
		}
		patient.Position, patient.Class = entry.Position, entry.UrgencyClass
		s.roster.Add(patient)
		s.log.Printf("+ entrada  %s %-26s %-24s classe %-2s → posição %d",
			patient.RequestID, patient.Name, patient.Profile.Label, entry.UrgencyClass, entry.Position)
		return nil
	}
	return fmt.Errorf("nenhum id livre depois de %d tentativas", maxIDRetries)
}

// SendEvent worsens the latest entry. If the regulation took it out of the
// queue (404) it is dropped and the one before it becomes the latest.
func (s *Simulator) SendEvent(ctx context.Context) error {
	for {
		patient, ok := s.roster.Latest()
		if !ok {
			s.log.Printf("  evento adiado: nenhum paciente do simulador na fila ainda")
			return nil
		}
		step, scripted, body := s.gen.NextEvent(patient)
		entry, err := s.api.AddEvent(ctx, body)
		var refused *APIError
		if errors.As(err, &refused) && refused.Status == http.StatusNotFound {
			s.log.Printf("  %s saiu da fila; não recebe mais eventos", patient.RequestID)
			s.roster.Remove(patient.RequestID)
			continue
		}
		if err != nil {
			return fmt.Errorf("evento de %s: %w", patient.RequestID, err)
		}
		if scripted {
			patient.Next++
		}
		s.log.Print(describeMove(patient, step, entry))
		patient.Position, patient.Class = entry.Position, entry.UrgencyClass
		return nil
	}
}

// describeMove is the log line of an event: who, what, and how far it jumped
// since the simulator last saw the patient. The backend's previousPosition is
// the place before the patient's last move, which may be an older event, so it
// only stands in when the simulator has no position of its own yet.
func describeMove(p *Patient, step Step, entry Entry) string {
	from := p.Position
	if from == 0 && entry.PreviousPosition != nil {
		from = *entry.PreviousPosition
	}
	move := fmt.Sprintf("ficou em %d", entry.Position)
	switch {
	case entry.Position < from:
		move = fmt.Sprintf("subiu %d → %d (+%d)", from, entry.Position, from-entry.Position)
	case entry.Position > from:
		move = fmt.Sprintf("desceu %d → %d", from, entry.Position)
	}
	class := entry.UrgencyClass
	if p.Class != "" && p.Class != entry.UrgencyClass {
		class = fmt.Sprintf("%s→%s", p.Class, entry.UrgencyClass)
	}
	return fmt.Sprintf("  evento   %s %-36s classe %-5s %s",
		p.RequestID, step.Kind+"/"+step.Result, class, move)
}

// Run sends the first entry right away and then keeps the schedule until ctx
// ends: an event every EventInterval (the first one EventInterval after the
// first entry) and an entry every EntryInterval. When both fall due together
// the event goes first, so it still reaches the entry it was meant for and the
// new entry starts clean: at the default pace every entry gets its events at
// +5 s and +10 s, then the next one arrives. A failed call is logged and the
// schedule goes on (the backend may be restarting); a call slower than an
// interval skips the ticks it overran instead of firing them in a burst.
func (s *Simulator) Run(ctx context.Context, cfg Config) error {
	if cfg.EntryInterval <= 0 || cfg.EventInterval <= 0 {
		return errors.New("os intervalos de entrada e de evento precisam ser maiores que zero")
	}
	s.log.Printf("nova entrada a cada %s; um evento na última entrada a cada %s", cfg.EntryInterval, cfg.EventInterval)

	start := time.Now()
	s.report(ctx, s.SendEntry(ctx))
	nextEvent := start.Add(cfg.EventInterval)
	nextEntry := start.Add(cfg.EntryInterval)

	timer := time.NewTimer(time.Until(earliest(nextEvent, nextEntry)))
	defer timer.Stop()
	for {
		select {
		case <-ctx.Done():
			return nil
		case <-timer.C:
		}
		now := time.Now()
		if !nextEvent.After(now) {
			s.report(ctx, s.SendEvent(ctx))
			nextEvent = advance(nextEvent, cfg.EventInterval, now)
		}
		if !nextEntry.After(now) {
			s.report(ctx, s.SendEntry(ctx))
			nextEntry = advance(nextEntry, cfg.EntryInterval, now)
		}
		timer.Reset(time.Until(earliest(nextEvent, nextEntry)))
	}
}

func (s *Simulator) report(ctx context.Context, err error) {
	if err != nil && ctx.Err() == nil {
		s.log.Printf("falhou: %v", err)
	}
}

func earliest(a, b time.Time) time.Time {
	if a.Before(b) {
		return a
	}
	return b
}

// advance moves a due time to its next slot after now, keeping the grid: the
// event and entry slots keep coinciding however late a call ran.
func advance(due time.Time, every time.Duration, now time.Time) time.Time {
	for !due.After(now) {
		due = due.Add(every)
	}
	return due
}
