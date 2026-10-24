package sim

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// Entry is the part of the backend's QueueEntry the simulator reads.
type Entry struct {
	ID               string  `json:"id"`
	PatientID        string  `json:"patientId"`
	Name             string  `json:"name"`
	EnteredAt        string  `json:"enteredAt"`
	Position         int     `json:"position"`
	PreviousPosition *int    `json:"previousPosition"`
	UrgencyClass     string  `json:"urgencyClass"`
	Score            float64 `json:"score"`
}

// Snapshot is GET /fila.
type Snapshot struct {
	Total   int     `json:"total"`
	Entries []Entry `json:"entries"`
}

// APIError is a response the backend refused, with its Portuguese `detail`.
type APIError struct {
	Status int
	Detail string
}

func (e *APIError) Error() string { return fmt.Sprintf("HTTP %d: %s", e.Status, e.Detail) }

// API is what the simulator needs from the backend; tests pass a fake.
type API interface {
	Health(ctx context.Context) error
	Queue(ctx context.Context) (Snapshot, error)
	AddEntry(ctx context.Context, body map[string]any) (Entry, error)
	AddEvent(ctx context.Context, body map[string]any) (Entry, error)
}

// Client talks to the regulation API under /v1/hospitais/<hospital>.
type Client struct {
	BaseURL  string
	Hospital string
	HTTP     *http.Client
}

func NewClient(baseURL, hospital string) *Client {
	return &Client{
		BaseURL:  strings.TrimRight(baseURL, "/"),
		Hospital: hospital,
		HTTP:     &http.Client{Timeout: 15 * time.Second},
	}
}

func (c *Client) queuePath(suffix string) string {
	return fmt.Sprintf("%s/v1/hospitais/%s/fila%s", c.BaseURL, c.Hospital, suffix)
}

func (c *Client) Health(ctx context.Context) error {
	return c.do(ctx, http.MethodGet, c.BaseURL+"/api/health", nil, nil)
}

func (c *Client) Queue(ctx context.Context) (Snapshot, error) {
	var snapshot Snapshot
	err := c.do(ctx, http.MethodGet, c.queuePath(""), nil, &snapshot)
	return snapshot, err
}

func (c *Client) AddEntry(ctx context.Context, body map[string]any) (Entry, error) {
	var entry Entry
	err := c.do(ctx, http.MethodPost, c.queuePath("/entradas"), body, &entry)
	return entry, err
}

func (c *Client) AddEvent(ctx context.Context, body map[string]any) (Entry, error) {
	var entry Entry
	err := c.do(ctx, http.MethodPost, c.queuePath("/eventos"), body, &entry)
	return entry, err
}

func (c *Client) do(ctx context.Context, method, url string, body any, out any) error {
	var payload io.Reader
	if body != nil {
		raw, err := json.Marshal(body)
		if err != nil {
			return err
		}
		payload = bytes.NewReader(raw)
	}
	req, err := http.NewRequestWithContext(ctx, method, url, payload)
	if err != nil {
		return err
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}
	if resp.StatusCode >= 300 {
		var refused struct {
			Detail string `json:"detail"`
		}
		if json.Unmarshal(raw, &refused) != nil || refused.Detail == "" {
			refused.Detail = strings.TrimSpace(string(raw))
		}
		return &APIError{Status: resp.StatusCode, Detail: refused.Detail}
	}
	if out == nil {
		return nil
	}
	return json.Unmarshal(raw, out)
}
