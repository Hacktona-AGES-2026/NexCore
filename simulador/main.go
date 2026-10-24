// Simulador da ingestão do NexCore: manda entradas e eventos clínicos mockados
// para POST /v1/hospitais/<id>/fila/entradas e /fila/eventos, como um timer —
// uma entrada nova a cada ENTRY_INTERVAL e, desde a primeira, um evento para a
// última entrada a cada EVENT_INTERVAL. Configuração por ambiente (ver
// README.md); `-dump N` só imprime N entradas com seus eventos e sai.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"math/rand/v2"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"github.com/nexcore/simulador/internal/sim"
)

func env(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func envInt(key string, fallback int) int {
	value, err := strconv.Atoi(env(key, strconv.Itoa(fallback)))
	if err != nil {
		log.Fatalf("%s precisa ser um número inteiro: %v", key, err)
	}
	return value
}

func envDuration(key string, fallback time.Duration) time.Duration {
	value, err := time.ParseDuration(env(key, fallback.String()))
	if err != nil || value <= 0 {
		log.Fatalf("%s precisa ser uma duração positiva como 10s ou 1m: %q", key, os.Getenv(key))
	}
	return value
}

func main() {
	dump := flag.Int("dump", 0, "imprime N entradas e os eventos que cada uma recebe como JSON e sai")
	flag.Parse()

	reference, err := time.Parse(sim.DateLayout, env("REFERENCE_DATE", "2026-10-23"))
	if err != nil {
		log.Fatalf("REFERENCE_DATE precisa ser AAAA-MM-DD: %v", err)
	}
	cfg := sim.Config{
		EntryInterval: envDuration("ENTRY_INTERVAL", sim.DefaultConfig.EntryInterval),
		EventInterval: envDuration("EVENT_INTERVAL", sim.DefaultConfig.EventInterval),
	}
	seed := uint64(envInt("SIM_SEED", int(time.Now().UnixNano()&0x7fffffff)))
	rng := rand.New(rand.NewPCG(seed, seed^0x9e3779b97f4a7c15))
	gen := sim.NewGenerator(rng, reference)

	if *dump > 0 {
		if err := json.NewEncoder(os.Stdout).Encode(sim.Dump(gen, *dump, cfg.EventsPerEntry())); err != nil {
			log.Fatal(err)
		}
		return
	}

	logger := log.New(os.Stdout, "", log.Ltime)
	client := sim.NewClient(env("BACKEND_URL", "http://127.0.0.1:5000"), env("HOSPITAL_ID", "hsl"))
	simulator := sim.New(client, gen, logger)

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	logger.Printf("backend em %s, hospital %s, semente %d", client.BaseURL, client.Hospital, seed)
	if err := simulator.WaitForBackend(ctx, 3*time.Second); err != nil {
		return
	}
	if err := simulator.Bootstrap(ctx); err != nil {
		logger.Fatal(err)
	}
	if err := simulator.Run(ctx, cfg); err != nil {
		logger.Fatal(err)
	}
	fmt.Fprintf(os.Stdout, "encerrado: %d pacientes do simulador acompanhados\n", simulator.Roster().Len())
}
