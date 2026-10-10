{{/*
Expand the name of the chart.
*/}}
{{- define "portal-api.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "portal-api.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "portal-api.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "portal-api.labels" -}}
helm.sh/chart: {{ include "portal-api.chart" . }}
{{ include "portal-api.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "portal-api.selectorLabels" -}}
app.kubernetes.io/name: {{ include "portal-api.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "portal-api.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "portal-api.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
ConfigMap name
*/}}
{{- define "portal-api.configMapName" -}}
{{- printf "%s-config" (include "portal-api.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Secret name
*/}}
{{- define "portal-api.secretName" -}}
{{- printf "%s-secret" (include "portal-api.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
JWT keystore Secret name — deliberately separate from secretName above, so
its content is never pulled in by envFrom (see values.yaml
persistence.jwtKeystore comment).
*/}}
{{- define "portal-api.jwtKeystoreSecretName" -}}
{{- printf "%s-jwt-keystore" (include "portal-api.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Resolved license tier -- "community" is the wire value the licence server
and app/licensing.py use ("Free" is only the commercial display name).
Defaults to community (the most restrictive tier) when unset, never to a
permissive default -- an unrecognised/unset tier must not read as "grant
everything".
*/}}
{{- define "portal-api.licenseTier" -}}
{{- default "community" .Values.license.tier }}
{{- end }}

{{/*
Per-tier cap on THIS service type's backend node (replica) count --
docs/APP_STANDARDS.md "Backend nodes per service type": 1 each on
Free/Professional, multiple/HA on Enterprise. Absolute -- general.md
requires licence enforcement be a hard block, and a plain values field
(e.g. license.maxReplicasOverride, removed here) is not one: Helm
templates cannot verify a signed licence-server claim, so any
self-assertable override is a one-flag bypass of the entire cap, not an
enforcement mechanism. A specific negotiated Enterprise node count
(narrower than "unlimited") needs a real attestation path -- runtime
verification via penguin_licensing.LicenseClient, not a Helm value -- and
is not implemented by this chart.
*/}}
{{- define "portal-api.maxReplicas" -}}
{{- $tier := include "portal-api.licenseTier" . }}
{{- if eq $tier "enterprise" }}
{{- 999999 }}
{{- else }}
{{- 1 }}
{{- end }}
{{- end }}

{{/*
The replica count that actually governs the running pod count. When
autoscaling is on, spec.replicas is OMITTED from the Deployment (see
templates/deployment.yaml) and the HPA drives scale between
autoscaling.minReplicas and autoscaling.maxReplicas — so .Values.replicaCount
alone is not what controls behaviour and must never be the value the
license-cap/JWT-keystore guards test. This is max(replicaCount,
autoscaling.maxReplicas) when autoscaling is enabled (the ceiling the HPA can
actually reach), else replicaCount itself.
*/}}
{{- define "portal-api.effectiveReplicas" -}}
{{- if .Values.autoscaling.enabled -}}
{{- max (int .Values.replicaCount) (int .Values.autoscaling.maxReplicas) -}}
{{- else -}}
{{- int .Values.replicaCount -}}
{{- end -}}
{{- end -}}
