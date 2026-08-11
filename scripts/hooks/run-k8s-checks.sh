#!/usr/bin/env bash
# run-k8s-checks.sh — best-effort K8s/Helm security checks (advisory).
#
# Matches the old hand-written pre-push hook exactly: kube-score, helm
# lint + checkov-on-rendered-templates, and the runAsNonRoot /
# allowPrivilegeEscalation greps were all non-blocking there too (chained
# with `|| true`, or plain warnings with no nonzero exit). This repo's
# k8s/helm/*/ charts are currently stubs (no Chart.yaml/values.yaml, no
# rendered manifests) so every check below is a no-op until real charts
# land — preserved here rather than dropped so it activates automatically
# once they do.
set -uo pipefail

if [ -d k8s/helm ]; then
  for chart in k8s/helm/*/; do
    [ -f "${chart}Chart.yaml" ] || continue
    helm lint "$chart" 2>/dev/null || true
    helm template release "$chart" 2>/dev/null | checkov -d /dev/stdin --quiet --compact 2>/dev/null || true
  done
fi

if [ -d k8s/ ]; then
  manifests=$(find k8s/ -name "*.yaml" 2>/dev/null || true)
  if [ -n "$manifests" ]; then
    # shellcheck disable=SC2086
    kube-score score $manifests 2>/dev/null || true
    for manifest in $manifests; do
      grep -qL 'runAsNonRoot' "$manifest" && \
        echo "WARNING: $manifest — missing runAsNonRoot"
      grep -qL 'allowPrivilegeEscalation' "$manifest" && \
        echo "WARNING: $manifest — missing allowPrivilegeEscalation: false"
    done
  fi
fi

exit 0
