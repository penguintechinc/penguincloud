#!/usr/bin/env bash
# run-k8s-checks.sh — Helm chart validation (BLOCKING, pre-push).
#
# For every k8s/helm/*/ chart and every alpha/beta/gamma/production.yml
# values file: `helm lint --strict`, then `helm template` (using the same
# --set placeholders devops uses locally to exercise the charts'
# deploy-time fail-fast guards without a real cluster/secret store), then
# kube-score + checkov against the RENDERED output.
#
# This intentionally never scans templates/*.yaml directly (Go template
# {{ }} syntax, not literal YAML — check-yaml/yamllint are excluded from
# those paths for the same reason, see .pre-commit-config.yaml) and never
# points checkov at a directory that doesn't contain rendered manifests (a
# prior version passed /dev/stdin to `checkov -d`, which expects a real
# directory and silently produced nothing to fail on).
#
# Ignore lists below mirror .checkov.yaml/.trivyignore at the repo root:
# reviewed, documented deviations from a generic scanner default in favor
# of an explicit PenguinTech house rule, not blanket suppression.
set -euo pipefail

[ -d k8s/helm ] || exit 0

REPO_ROOT="$(pwd)"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

FAILED=0

# Every suppression below is individually justified, not a blanket pass —
# each is a reviewed, documented deviation from a generic scanner default
# in favor of an explicit PenguinTech house rule or a known scanner
# limitation, adjudicated one at a time:
#
#   container-security-context-user-group-id (kube-score) -- bundles TWO
#     unrelated checks into one test ID: (a) UID/GID > 10000 (a style
#     preference devops-kubernetes.md deliberately overrides: runAsUser:
#     1000 explicitly, webui: 999 matching its Dockerfile's actual baked-in
#     UID), and (b) runAsNonRoot being set at all -- (b) is a REAL,
#     mandatory check this gate must not lose. Since kube-score's
#     --ignore-test is all-or-nothing per test ID with no way to keep only
#     (b), (a)+(b) are ignored here and (b) is re-implemented as its own
#     explicit, correctly-exit-status-tested check below (never repeat the
#     grep -qL inversion bug this script used to have) -- see the
#     "runAsNonRoot" step per chart/env, which is what actually closes this
#     gap rather than trusting kube-score to.
#   pod-networkpolicy (kube-score) -- every chart ships a
#     CiliumNetworkPolicy (cilium.io/v2), which kube-score's
#     plain-NetworkPolicy-only check does not recognise as satisfying the
#     requirement. checkov's equivalent (CKV2_K8S_6) has the identical
#     limitation and is baselined the same way in .checkov.yaml.
#   container-image-pull-policy (kube-score) -- IfNotPresent is
#     intentional in every environment: alpha/beta/gamma use a unique,
#     never-reused CI-built tag; production pins by SHA256 digest. Neither
#     needs "Always" to guarantee freshness.
#   deployment-replicas + service-type (kube-score, non-production only) --
#     devops-kubernetes.md's resource tier table mandates exactly 1 replica
#     for alpha/beta/gamma, and security.md's "No Direct External Access"
#     explicitly exempts alpha's NodePort. Scoped OUT of production below
#     (never ignored there), where either would be a real regression.
#   deployment-strategy (kube-score, valkey only) -- Recreate is
#     intentional (k8s/helm/valkey/templates/deployment.yaml's own
#     comment: avoids two valkey-server processes racing to write /data).
#   --framework kubernetes (checkov) -- the default (all frameworks) also
#     runs checkov's generic secrets/entropy scanner against rendered
#     ExternalSecret manifests, flagging Vault key-PATH strings like
#     "penguincloud/gamma/portal-api#LICENSE_KEY" as "Base64 High Entropy
#     String" (reviewed false positives: no actual secret VALUE is ever in
#     a committed values file or a template render). This does not leave
#     secret-leak detection uncovered: gitleaks and trufflehog are their
#     own separate, dedicated pre-commit/pre-push hooks (devops.md's hook
#     table) that scan the whole repo including these same files.
KUBE_SCORE_IGNORE_ALWAYS=(
  --ignore-test container-security-context-user-group-id
  --ignore-test pod-networkpolicy
  --ignore-test container-image-pull-policy
)

for chart_dir in k8s/helm/*/; do
  chart="$(basename "$chart_dir")"
  [ -f "${chart_dir}Chart.yaml" ] || continue

  echo "== ${chart}: helm lint --strict =="
  if ! helm lint --strict "$chart_dir"; then
    echo "FAIL: helm lint --strict ${chart}"
    FAILED=1
  fi

  for env_name in alpha beta gamma production; do
    values_path="${chart_dir}${env_name}.yml"
    [ -f "$values_path" ] || continue

    extra_set=()
    # valkey's auth is mandatory (never anonymous) -- alpha.yml's
    # secrets.create path needs a real value at install time; static
    # validation supplies a throwaway placeholder, never committed
    # anywhere and never used outside this script's own temp render.
    if [ "$chart" = "valkey" ] && [ "$env_name" = "alpha" ]; then
      extra_set+=(--set secrets.data.VALKEY_PASSWORD=ci-placeholder-not-a-real-secret)
    fi
    # beta.yml/gamma.yml intentionally fail to render without CI having
    # injected image.tag (image.requireTag guard, M4) -- supply a
    # placeholder so static validation can still exercise the rest of the
    # chart.
    if { [ "$env_name" = "beta" ] || [ "$env_name" = "gamma" ]; } && { [ "$chart" = "portal-api" ] || [ "$chart" = "webui" ]; }; then
      extra_set+=(--set "image.tag=${env_name}-0000000000")
    fi
    # production.yml intentionally fails to render without operator-
    # supplied digests/hosts/storage class (fail-fast guards, by design)
    # -- supply placeholders so static validation can still run.
    if [ "$env_name" = "production" ]; then
      case "$chart" in
        portal-api)
          extra_set+=(
            --set image.digest=sha256:0000000000000000000000000000000000000000000000000000000000000
            --set ingress.host=ci.penguincloud.app
            --set config.BASE_URL=ci.penguincloud.app
            --set config.JWT_ISSUER=https://ci.penguincloud.app
            --set persistence.jwtKeystore.storageClassName=ci-placeholder
            --set "ingress.tls[0].hosts[0]=ci.penguincloud.app"
          )
          ;;
        webui)
          extra_set+=(
            --set image.digest=sha256:0000000000000000000000000000000000000000000000000000000000000
            --set ingress.host=ci.penguincloud.app
            --set "ingress.tls[0].hosts[0]=ci.penguincloud.app"
          )
          ;;
      esac
    fi

    out="${WORKDIR}/${chart}-${env_name}.yaml"
    echo "== ${chart}: helm template (${env_name}) =="
    if ! helm template "$chart" "$chart_dir" -n penguincloud --values "$values_path" "${extra_set[@]}" > "$out" 2>"${out}.err"; then
      echo "FAIL: helm template ${chart} ${env_name}"
      cat "${out}.err"
      FAILED=1
      continue
    fi

    # Re-enables what ignoring container-security-context-user-group-id
    # above gives up: devops-kubernetes.md mandates runAsNonRoot: true on
    # every container, no exceptions without explicit approval. Tested
    # directly with plain `grep -q` (0 = found) — no -L, no inversion, the
    # exact bug class a prior version of this script shipped
    # (grep -qL 'runAsNonRoot' ... && echo WARNING fired on COMPLIANT
    # manifests and stayed silent on non-compliant ones, because -q
    # overrides -L's exit-status semantics on GNU grep). Runs against the
    # RENDERED, already-verified-valid-YAML output, never the raw
    # Go-template source.
    if grep -q "kind: Deployment" "$out"; then
      if grep -q "runAsNonRoot: false" "$out"; then
        echo "FAIL: ${chart} ${env_name} — found runAsNonRoot: false (devops-kubernetes.md mandates true)"
        FAILED=1
      elif ! grep -q "runAsNonRoot: true" "$out"; then
        echo "FAIL: ${chart} ${env_name} — no runAsNonRoot: true found in a Deployment (devops-kubernetes.md mandates it)"
        FAILED=1
      fi
    fi

    ignore_tests=("${KUBE_SCORE_IGNORE_ALWAYS[@]}")
    if [ "$env_name" != "production" ]; then
      # devops-kubernetes.md: alpha/beta/gamma are intentionally 1
      # replica (resource tier table), and alpha intentionally uses
      # NodePort (security.md "No Direct External Access" explicitly
      # exempts alpha) -- both would be real regressions if seen in
      # production, so this branch never applies there.
      ignore_tests+=(--ignore-test deployment-replicas --ignore-test service-type)
    fi
    if [ "$chart" = "valkey" ]; then
      # Single-instance cache, Recreate strategy on purpose (see
      # k8s/helm/valkey/templates/deployment.yaml's own comment: avoids
      # two valkey-server processes racing to write /data).
      ignore_tests+=(--ignore-test deployment-strategy)
    fi

    echo "== ${chart}: kube-score (${env_name}) =="
    if ! kube-score score "$out" "${ignore_tests[@]}" > "${out}.kubescore.log" 2>&1; then
      echo "FAIL: kube-score ${chart} ${env_name}"
      cat "${out}.kubescore.log"
      FAILED=1
    fi

    echo "== ${chart}: checkov (${env_name}) =="
    # --framework kubernetes: the default (all frameworks) also runs
    # checkov's generic secrets/entropy scanner against the rendered
    # ExternalSecret manifests, which flags Vault key-PATH strings like
    # "penguincloud/gamma/portal-api#LICENSE_KEY" as "Base64 High Entropy
    # String" -- reviewed false positives (no actual secret VALUE is ever
    # in a committed values file or a helm template render; gitleaks/
    # trufflehog own real secret-leak detection per devops.md's hook
    # table, not this chart-correctness check).
    if ! checkov -f "$out" --framework kubernetes --config-file "${REPO_ROOT}/.checkov.yaml" --quiet --compact > "${out}.checkov.log" 2>&1; then
      echo "FAIL: checkov ${chart} ${env_name}"
      cat "${out}.checkov.log"
      FAILED=1
    fi
  done
done

exit "$FAILED"
