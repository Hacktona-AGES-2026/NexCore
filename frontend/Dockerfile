# Frontend NexCore: build do Vite e nginx servindo o resultado.
#
# As VITE_* são lidas no BUILD (ficam no bundle). O padrão aponta para caminhos
# relativos, servidos pelo mesmo nginx que faz proxy de /v1 e /api para o backend:
# o front e a API ficam na mesma origem, sem CORS e sem host fixo no bundle.
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .

ARG VITE_USE_MOCK=false
ARG VITE_API_URL=/v1
ARG VITE_WS_URL=/v1/ws
ARG VITE_HOSPITAL_ID=hsl
ENV VITE_USE_MOCK=$VITE_USE_MOCK \
    VITE_API_URL=$VITE_API_URL \
    VITE_WS_URL=$VITE_WS_URL \
    VITE_HOSPITAL_ID=$VITE_HOSPITAL_ID

RUN npm run build


FROM nginx:1.27-alpine

# O nginx da imagem oficial passa os *.template pelo envsubst na subida, trocando só
# as variáveis de ambiente definidas: $host, $http_upgrade etc. continuam do nginx.
ENV BACKEND_UPSTREAM=backend:5000
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
