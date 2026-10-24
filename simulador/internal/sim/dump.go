package sim

// Batch is what `-dump` prints: the entries and, after each, the events the
// running simulator would send it before the next entry arrives. The backend's
// suite posts it to a real app to prove the mock data passes the ingestion
// contract and moves each newcomer visibly.
type Batch struct {
	Entries []map[string]any `json:"entradas"`
	Events  []map[string]any `json:"eventos"`
}

// Dump generates n entries (sequence 1..n), each followed by eventsPerEntry
// events: its story in order, then Worsening steps if the story runs out.
func Dump(gen *Generator, n, eventsPerEntry int) Batch {
	var batch Batch
	for seq := 1; seq <= n; seq++ {
		patient, body := gen.NewEntry(seq)
		batch.Entries = append(batch.Entries, body)
		for range eventsPerEntry {
			_, scripted, event := gen.NextEvent(patient)
			batch.Events = append(batch.Events, event)
			if scripted {
				patient.Next++
			}
		}
	}
	return batch
}
