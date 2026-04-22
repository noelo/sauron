# Kubernetes Deployment for Sauron

This directory contains Kubernetes manifests for deploying the Sauron content aggregator.

## Components

- **namespace.yaml** - Creates the `sauron` namespace
- **pvc.yaml** - PersistentVolumeClaim for data storage (10Gi)
- **secret.yaml** - Configuration stored as Kubernetes secrets
- **deployment.yaml** - Main application deployment
- **kustomization.yaml** - Kustomize configuration for easy deployment

## Quick Start

### 1. Configure Secrets

Edit `secret.yaml` and replace placeholder values with actual configuration:

```yaml
stringData:
  TELEGRAM_BOT_TOKEN: "your-actual-bot-token"
  TELEGRAM_CHANNEL_ID: "your-channel-id"
  LLM_API_KEY: "your-llm-api-key"
  # ... other configs
```

### 2. Deploy

Using kubectl:
```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/deployment.yaml
```

Or using kustomize:
```bash
kubectl apply -k k8s/
```

### 3. Build and Push Image

```bash
docker build -t sauron:latest .
docker tag sauron:latest your-registry/sauron:latest
docker push your-registry/sauron:latest
```

Update the image in deployment.yaml if using a remote registry.

## Storage

Data is persisted to `/app/data` via a PVC. The application stores:
- Extracted articles in `articles/` subdirectory
- Processing logs in `processing_log.json`

## Configuration

All configuration is loaded from environment variables via the secret:
- `DATA_DIR` is set to `/app/data` (PVC mount point)
- Other settings match the `.env` file structure

## Verification

Check pod status:
```bash
kubectl get pods -n sauron
```

View logs:
```bash
kubectl logs -n sauron -l app=sauron
```

Check PVC:
```bash
kubectl get pvc -n sauron
```
