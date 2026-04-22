# Sauron Helm Chart

A Helm chart for deploying the Sauron Content Aggregator to Kubernetes.

## Prerequisites

- Kubernetes 1.19+
- Helm 3.2.0+
- PV provisioner support in the underlying infrastructure

## Installing the Chart

### Quick Start

```bash
helm install sauron ./charts/sauron \
  --namespace sauron \
  --create-namespace \
  --set telegram.botToken="YOUR_BOT_TOKEN" \
  --set telegram.channelId="YOUR_CHANNEL_ID" \
  --set llm.apiKey="YOUR_API_KEY"
```

### With Custom Values File

Create a `values-override.yaml`:

```yaml
telegram:
  botToken: "YOUR_BOT_TOKEN"
  channelId: "YOUR_CHANNEL_ID"

llm:
  apiKey: "YOUR_API_KEY"
  model: "gpt-4"

persistence:
  storageClassName: "standard"
  size: 20Gi

resources:
  limits:
    memory: 1Gi
    cpu: 1000m
```

Install:

```bash
helm install sauron ./charts/sauron \
  --namespace sauron \
  --create-namespace \
  -f values-override.yaml
```

## Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `replicaCount` | Number of replicas | `1` |
| `image.repository` | Docker image repository | `sauron` |
| `image.tag` | Docker image tag | `""` (defaults to chart appVersion) |
| `image.pullPolicy` | Image pull policy | `IfNotPresent` |
| `telegram.botToken` | Telegram bot token (required) | `""` |
| `telegram.channelId` | Telegram channel ID (required) | `""` |
| `llm.provider` | LLM provider | `openai` |
| `llm.apiKey` | LLM API key (required) | `""` |
| `llm.baseUrl` | LLM base URL | `https://api.openai.com/v1` |
| `llm.model` | LLM model name | `qwen35-9b` |
| `llm.maxTokens` | Maximum tokens for LLM | `500` |
| `llm.temperature` | LLM temperature | `0.3` |
| `persistence.enabled` | Enable PVC | `true` |
| `persistence.size` | PVC storage size | `10Gi` |
| `persistence.storageClassName` | Storage class | `standard` |
| `resources.limits.memory` | Memory limit | `512Mi` |
| `resources.limits.cpu` | CPU limit | `500m` |
| `resources.requests.memory` | Memory request | `256Mi` |
| `resources.requests.cpu` | CPU request | `250m` |
| `config.logLevel` | Log level | `INFO` |
| `config.processingInterval` | Processing interval | `5` |

## Persistence

The chart creates a PersistentVolumeClaim to store:
- Extracted articles in `articles/` subdirectory
- Processing logs in `processing_log.json`

Data is stored at `/app/data` in the container.

## Upgrading

```bash
helm upgrade sauron ./charts/sauron \
  --namespace sauron \
  -f values-override.yaml
```

## Uninstalling

```bash
helm uninstall sauron --namespace sauron
```

Note: The PVC is not deleted by default. To remove it:

```bash
kubectl delete pvc -n sauron sauron-data
```

## Building the Docker Image

```bash
docker build -t sauron:latest .
docker tag sauron:latest your-registry/sauron:latest
docker push your-registry/sauron:latest
```

Then update `image.repository` in your values file.
