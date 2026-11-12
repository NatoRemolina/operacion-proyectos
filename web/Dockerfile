# Imagen de producción de la web: compilación con next build y salida standalone.
# Node 26 es la LTS vigente (activa desde octubre de 2026); coincide con .nvmrc.
ARG NODE_IMAGE=node:26-alpine

FROM ${NODE_IMAGE} AS dependencias
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM ${NODE_IMAGE} AS compilacion
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# Se incrusta en el JavaScript del navegador al compilar; no admite secretos.
ARG NEXT_PUBLIC_API_BASE=/api/v1
ENV NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE}
COPY --from=dependencias /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM ${NODE_IMAGE} AS ejecucion
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    FUENTE_DATOS=http
# Usuario sin privilegios que ya trae la imagen oficial de Node.
COPY --from=compilacion --chown=node:node /app/.next/standalone ./
COPY --from=compilacion --chown=node:node /app/.next/static ./.next/static
COPY --from=compilacion --chown=node:node /app/public ./public
USER node
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD node -e "fetch('http://127.0.0.1:3000/entrar').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server.js"]
