FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
# Dependencies are installed at container start (see docker-compose) into a named volume.
# This keeps image build fast and avoids flaky network issues during build.

COPY . .

EXPOSE 3000
CMD ["npm","run","dev"]
