# Simulador da ingestão: binário Go estático numa imagem sem shell.
FROM golang:1.23-alpine AS build
WORKDIR /src
COPY go.mod ./
COPY . .
RUN go test ./... && CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/simulador .

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/simulador /simulador
ENTRYPOINT ["/simulador"]
