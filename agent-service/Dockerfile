FROM oven/bun:1

WORKDIR /app

COPY package.json ./
RUN bun install

COPY src ./src

ENV PORT=4096
ENV WORKSPACE_ROOT=/app/workspaces
ENV OPENCODE_DISABLE_FREE_MODELS=1
ENV ENABLE_BROWSER_TOOLS=0

RUN mkdir -p /app/workspaces

EXPOSE 4096

CMD ["bun", "src/index.ts"]
