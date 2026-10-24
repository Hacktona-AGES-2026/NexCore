package sim

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
)

type recorded struct {
	method, path, contentType string
	body                      map[string]any
}

func server(t *testing.T, status int, response string) (*Client, *recorded) {
	t.Helper()
	got := &recorded{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		got.method, got.path, got.contentType = r.Method, r.URL.Path, r.Header.Get("Content-Type")
		raw, _ := io.ReadAll(r.Body)
		if len(raw) > 0 {
			if err := json.Unmarshal(raw, &got.body); err != nil {
				t.Errorf("corpo não é JSON: %s", raw)
			}
		}
		w.WriteHeader(status)
		io.WriteString(w, response)
	}))
	t.Cleanup(srv.Close)
	return NewClient(srv.URL+"/", "hsl"), got
}

func TestEntradaVaiParaARotaDaRegulacao(t *testing.T) {
	client, got := server(t, http.StatusCreated, `{"id":"SOL-2026-90001","position":812,"urgencyClass":"D","score":12.5}`)
	entry, err := client.AddEntry(context.Background(), map[string]any{"solicitacao_id": "SOL-2026-90001"})
	if err != nil {
		t.Fatal(err)
	}
	if got.method != http.MethodPost || got.path != "/v1/hospitais/hsl/fila/entradas" {
		t.Fatalf("%s %s", got.method, got.path)
	}
	if got.contentType != "application/json" || got.body["solicitacao_id"] != "SOL-2026-90001" {
		t.Fatalf("content-type %q, corpo %v", got.contentType, got.body)
	}
	if entry.Position != 812 || entry.UrgencyClass != "D" || entry.PreviousPosition != nil {
		t.Fatalf("entrada %+v", entry)
	}
}

func TestEventoLeAPosicaoAnterior(t *testing.T) {
	client, got := server(t, http.StatusAccepted, `{"id":"SOL-2026-90001","position":300,"previousPosition":812,"urgencyClass":"C"}`)
	entry, err := client.AddEvent(context.Background(), map[string]any{"tipo_evento": "pronto_socorro"})
	if err != nil {
		t.Fatal(err)
	}
	if got.path != "/v1/hospitais/hsl/fila/eventos" || entry.PreviousPosition == nil || *entry.PreviousPosition != 812 {
		t.Fatalf("%s %+v", got.path, entry)
	}
}

func TestRecusaViraAPIErrorComODetail(t *testing.T) {
	client, _ := server(t, http.StatusConflict, `{"detail":"Entrada: a solicitação SOL-2026-90001 já existe."}`)
	_, err := client.AddEntry(context.Background(), map[string]any{})
	var refused *APIError
	if !errors.As(err, &refused) || refused.Status != 409 || refused.Detail != "Entrada: a solicitação SOL-2026-90001 já existe." {
		t.Fatalf("erro %v", err)
	}
}

func TestRecusaSemJSONGuardaOTexto(t *testing.T) {
	client, _ := server(t, http.StatusBadGateway, "<html>bad gateway</html>")
	err := client.Health(context.Background())
	var refused *APIError
	if !errors.As(err, &refused) || refused.Status != 502 || refused.Detail != "<html>bad gateway</html>" {
		t.Fatalf("erro %v", err)
	}
}

func TestFilaEHealth(t *testing.T) {
	client, got := server(t, http.StatusOK, `{"total":2,"entries":[{"id":"SOL-1","position":1},{"id":"SOL-2","position":2}]}`)
	snapshot, err := client.Queue(context.Background())
	if err != nil || snapshot.Total != 2 || snapshot.Entries[1].ID != "SOL-2" {
		t.Fatalf("%+v %v", snapshot, err)
	}
	if got.method != http.MethodGet || got.path != "/v1/hospitais/hsl/fila" || got.body != nil {
		t.Fatalf("%s %s %v", got.method, got.path, got.body)
	}
	if err := client.Health(context.Background()); err != nil || got.path != "/api/health" {
		t.Fatalf("health: %v em %s", err, got.path)
	}
}

func TestBackendForaDoAr(t *testing.T) {
	client := NewClient("http://127.0.0.1:1", "hsl")
	if err := client.Health(context.Background()); err == nil {
		t.Fatal("esperava erro de conexão")
	}
}
