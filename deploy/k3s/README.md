# C2XC-Agent on k3s (single-tenant, hostPath, pinned node)

This deployment matches the repo's current *single-instance* runtime model:

- One backend Pod (FastAPI + in-process worker thread)
- One frontend Pod (static WebUI)
- One Traefik Ingress (single domain, TLS)
- Persistence via **hostPath** on a specific node (no migration; "crash → restart on same node")

## 0) Pick a backend node (pinning)

1) List nodes:

```bash
kubectl get nodes -o wide
```

2) Pick exactly one node to host:
- SQLite + Chroma data directory
- The two LightRAG KB working dirs

3) In `deploy/k3s/c2xc-agent.yaml`, replace:
- `__REPLACE_NODE_NAME__`

## 1) Prepare directories on the pinned node

On the chosen node:

```bash
sudo mkdir -p /var/lib/c2xc/data
sudo mkdir -p /var/lib/c2xc/kb/kb_principles
sudo mkdir -p /var/lib/c2xc/kb/kb_modulation
```

### Copy KB working dirs (recommended)

Your repo already contains built LightRAG working dirs under:
- `data/lightrag/kb_principles`
- `data/lightrag/kb_modulation`

Copy those directories to the pinned node:
- `/var/lib/c2xc/kb/kb_principles`
- `/var/lib/c2xc/kb/kb_modulation`

If you prefer tar:

```bash
tar -C data/lightrag -czf kb_principles.tar.gz kb_principles
tar -C data/lightrag -czf kb_modulation.tar.gz kb_modulation
```

Then copy to the pinned node and extract into `/var/lib/c2xc/kb/`.

## 2) Build images (Python 3.13)

Backend:

```bash
docker build -t c2xc-agent-backend:__TAG__ .
```

Frontend (Vite env is build-time):

```bash
docker build -t c2xc-agent-frontend:__TAG__ -f frontend/Dockerfile frontend --build-arg VITE_API_BASE_URL=/api/v1
```

## 3) Offline image distribution (no registry)

Save tarballs:

```bash
docker save c2xc-agent-backend:__TAG__ | gzip > c2xc-agent-backend.tar.gz
docker save c2xc-agent-frontend:__TAG__ | gzip > c2xc-agent-frontend.tar.gz
```

Copy the two `*.tar.gz` files to **each** k3s node and import them (each node has its own containerd):

```bash
sudo k3s ctr images import c2xc-agent-backend.tar.gz
sudo k3s ctr images import c2xc-agent-frontend.tar.gz
```

## 4) Configure secrets + domain + TLS

Edit `deploy/k3s/c2xc-agent.yaml` and replace:

- `__REPLACE_DOMAIN__`
- `__REPLACE_TLS_SECRET__`
- `__REPLACE_OPENAI_API_KEY__`
- `__REPLACE_C2XC_EMBEDDING_API_KEY__` (if needed)
- all `__REPLACE_*__` env vars for your gateways/models

Create a TLS secret (example):

```bash
kubectl -n c2xc create secret tls __REPLACE_TLS_SECRET__ --cert=fullchain.pem --key=privkey.pem
```

## 5) Apply (helm-controller style vs kubectl)

### Option A (k3s manifests auto-apply)

Copy the yaml to the k3s server manifests directory:

```bash
sudo cp deploy/k3s/c2xc-agent.yaml /var/lib/rancher/k3s/server/manifests/c2xc-agent.yaml
```

### Option B (kubectl apply)

```bash
kubectl apply -f deploy/k3s/c2xc-agent.yaml
```

## 6) Smoke checks

Wait for pods:

```bash
kubectl -n c2xc get pods -owide
```

Check backend:

```bash
curl -k https://__REPLACE_DOMAIN__/api/v1/healthz
curl -k https://__REPLACE_DOMAIN__/api/v1/version
```

