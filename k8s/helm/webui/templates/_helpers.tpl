{{/*
Expand the name of the chart.
*/}}
{{- define "webui.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "webui.fullname" -}}
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
{{- define "webui.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "webui.labels" -}}
helm.sh/chart: {{ include "webui.chart" . }}
{{ include "webui.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "webui.selectorLabels" -}}
app.kubernetes.io/name: {{ include "webui.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "webui.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "webui.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
ConfigMap name
*/}}
{{- define "webui.configMapName" -}}
{{- printf "%s-config" (include "webui.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Secret name — webui has no secret config today (FLASK_API_URL is a plain
in-cluster DNS name); templates/secret.yaml + externalsecret.yaml exist for
parity with portal-api's pattern, gated off by default.
*/}}
{{- define "webui.secretName" -}}
{{- printf "%s-secret" (include "webui.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Per-tier default cap on THIS service type's backend node (replica) count —
same model as portal-api (docs/APP_STANDARDS.md "Backend nodes per service
type"): 1 each on Free/Professional, multiple/HA on Enterprise.
*/}}
{{- define "webui.licenseTier" -}}
{{- default "community" .Values.license.tier }}
{{- end }}

{{/*
Absolute -- see portal-api's identical comment. license.maxReplicasOverride
was removed: a self-assertable Helm value is a one-flag bypass of the
entire cap, not enforcement (general.md requires a hard block).
*/}}
{{- define "webui.maxReplicas" -}}
{{- $tier := include "webui.licenseTier" . }}
{{- if eq $tier "enterprise" }}
{{- 999999 }}
{{- else }}
{{- 1 }}
{{- end }}
{{- end }}

{{/*
The replica count that actually governs the running pod count — see
portal-api's identical helper/comment. .Values.replicaCount alone is not
what controls behaviour once autoscaling is on (spec.replicas is omitted
from the Deployment and the HPA drives scale up to autoscaling.maxReplicas).
*/}}
{{- define "webui.effectiveReplicas" -}}
{{- if .Values.autoscaling.enabled -}}
{{- max (int .Values.replicaCount) (int .Values.autoscaling.maxReplicas) -}}
{{- else -}}
{{- int .Values.replicaCount -}}
{{- end -}}
{{- end -}}
