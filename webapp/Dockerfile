# Multi-stage build for optimized images
FROM node:24-alpine AS dependencies

WORKDIR /app

# Copy package files for better caching
COPY package*.json ./

# Install dependencies
RUN npm ci --only=production && npm cache clean --force

# Development stage
FROM node:24-alpine AS development

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install all dependencies including dev
RUN npm ci && npm cache clean --force

# Copy source code
COPY . .

EXPOSE 80

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "80"]

# Production build stage
FROM dependencies AS builder

WORKDIR /app

# Copy source code
COPY . .

# Install dev dependencies for build
RUN npm ci

# Build the application
RUN npm run build

# Production stage
FROM nginx:alpine AS production

# Copy built assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf

# Fix permissions so nginx user can read files
RUN chmod -R 755 /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
