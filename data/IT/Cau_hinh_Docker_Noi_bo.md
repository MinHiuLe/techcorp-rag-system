# Cấu hình Docker Nội bộ - TechCorp

## 1. Mục tiêu

Tài liệu này quy định tiêu chuẩn cấu hình Docker trong toàn bộ hệ thống TechCorp nhằm đảm bảo:

- Tính nhất quán giữa các môi trường (development, staging, production)
- Bảo mật container runtime và image lifecycle
- Tối ưu hiệu năng triển khai microservices
- Chuẩn hóa CI/CD pipeline và hệ thống orchestration

---

## 2. Kiến trúc Docker tiêu chuẩn

Hệ thống Docker của TechCorp được thiết kế theo mô hình:

- Microservices-based architecture
- Container orchestration:
  - Docker Compose (development, staging)
  - Kubernetes (production)
- Private Container Registry nội bộ (TechCorp Registry)

---

## 3. Quy chuẩn Docker Image

### 3.1 Base Image Policy

Chỉ được phép sử dụng base image an toàn:

- alpine
- debian:slim
- ubuntu LTS

Quy định bắt buộc:
- Không dùng image không rõ nguồn gốc
- Không dùng tag `latest` trong production
- Phải cố định version image

---

### 3.2 Image Naming Convention

Format:

techcorp/<service-name>:<version>

Ví dụ:

techcorp/auth-service:1.2.0  
techcorp/payment-service:2.0.5  
techcorp/user-service:0.9.3  

---

### 3.3 Versioning Policy

Semantic Versioning:

MAJOR.MINOR.PATCH

- MAJOR: breaking changes
- MINOR: feature mới
- PATCH: bug fix

---

## 4. Dockerfile Standards

### 4.1 Template chuẩn

FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
EXPOSE 3000
CMD ["node", "server.js"]

---

### 4.2 Multi-stage Build (Production)

FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM node:18-alpine
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY package*.json ./
RUN npm ci --only=production
EXPOSE 3000
CMD ["node", "dist/index.js"]

---

### 4.3 Quy tắc bắt buộc

- Không hardcode secrets
- Giảm số layer Docker
- Clean cache sau install
- Không chạy root user

---

## 5. Docker Compose (Development)

version: "3.9"

services:
  app:
    build: .
    container_name: techcorp_app
    ports:
      - "3000:3000"
    environment:
      NODE_ENV: development
      DB_HOST: db
    depends_on:
      - db
    networks:
      - backend

  db:
    image: postgres:15
    container_name: techcorp_db
    environment:
      POSTGRES_USER: admin
      POSTGRES_PASSWORD: secure_password
      POSTGRES_DB: techcorp
    ports:
      - "5432:5432"
    networks:
      - backend

networks:
  backend:
    driver: bridge

---

## 6. Networking Policy

- API Gateway là entry point duy nhất ra ngoài
- Database không được expose public
- Service-to-service chỉ qua internal network
- Mỗi domain có network riêng

---

## 7. Security Configuration

### 7.1 Container Security

- chạy non-root user
- read-only filesystem nếu có thể
- disable privileged mode
- drop unnecessary Linux capabilities

---

### 7.2 Secrets Management

Cấm:
- .env trong production image
- hardcode API key
- commit credential vào git

Chỉ dùng:
- Docker Secrets
- Vault
- Cloud KMS

---

### 7.3 Vulnerability Scan

- Scan bằng Trivy / Snyk
- Block nếu CVE HIGH hoặc CRITICAL

---

## 8. Logging & Monitoring

- logs: stdout / stderr
- không ghi file trong container
- centralized logging: ELK / Loki

Monitoring:
- Prometheus
- Grafana
- Alert Slack / PagerDuty

---

## 9. CI/CD Pipeline

1. Build image
2. Run tests
3. Security scan
4. Push registry
5. Deploy staging
6. Manual approval
7. Deploy production

---

## 10. Performance Optimization

- dùng alpine image
- enable cache layer
- set CPU/memory limit
- scale horizontal (HPA)

---

## 11. Incident Handling

### Crash Loop
- check logs
- validate config
- restart container

### High CPU
- scale service
- optimize code
- check memory leak

### Image pull error
- re-auth registry
- check tag/version

---

## 12. Compliance

- audit tất cả image
- log retention ≥ 30 ngày
- không deploy chưa qua staging
- security baseline v2.1

---

## 13. Exception Rule

Chỉ cho phép exception nếu:

- có DevOps Lead approval
- có Security approval
- có thời hạn rõ ràng
- có audit log

---
