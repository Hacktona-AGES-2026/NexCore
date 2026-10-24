package sim

// Roster is the simulator's patients in the order they entered. Events go to
// the latest one: after each entry the next events walk its story, so the
// newcomer is the one that visibly jumps until the next entry takes its place.
type Roster struct {
	patients []*Patient
}

func (r *Roster) Add(p *Patient) { r.patients = append(r.patients, p) }

func (r *Roster) Len() int { return len(r.patients) }

// Get returns the patient with that request id, or nil.
func (r *Roster) Get(requestID string) *Patient {
	for _, p := range r.patients {
		if p.RequestID == requestID {
			return p
		}
	}
	return nil
}

// Remove drops a patient that left the queue (the regulation removed it).
func (r *Roster) Remove(requestID string) {
	for i, p := range r.patients {
		if p.RequestID == requestID {
			r.patients = append(r.patients[:i], r.patients[i+1:]...)
			return
		}
	}
}

// Latest is the last patient that entered; false when there is none yet.
func (r *Roster) Latest() (*Patient, bool) {
	if len(r.patients) == 0 {
		return nil, false
	}
	return r.patients[len(r.patients)-1], true
}
