---
name: webui-node-uid-pattern
description: services/webui/Dockerfile reuses node:*-bookworm-slim's shipped `node` user (UID/GID 1000) instead of creating one; k8s/helm/webui/values.yaml pins runAsUser/runAsGroup/fsGroup to match.
type: project
---

`services/webui/Dockerfile` runs as `USER 1000`, reusing the official
`node:*-bookworm-slim` image's built-in `node` user rather than
`groupadd`/`useradd` (a second GID 1000 would collide). The Helm chart
(`k8s/helm/webui/values.yaml`) hardcodes `runAsUser: 1000`,
`runAsGroup: 1000`, `fsGroup: 1000` to match.

**Why this matters:** a base-image bump (e.g. node:22 → node:26,
2026-08-21) can silently change the shipped user's UID. If the chart
isn't updated in the same change, the pod fails to start — and because
`readOnlyRootFilesystem: true` + `fsGroup` are both set, the failure
mode is a permission error on first write, not a clean startup error.
An earlier round of this exact migration shipped a chart/image UID
mismatch (999 vs 1000) caught only by cross-checking branches before
merge.

**How to apply:** never infer the UID from the Dockerfile or from
memory of a prior base image. Build the image and run
`docker run --rm <img> id -u` before touching the chart. As of the
22→26 bump, the UID stayed 1000 (verified), so no chart change was
needed that time — but treat that as coincidence, not a pattern to
assume on the next bump. See [[docker-base-image-digest-pinning]].
