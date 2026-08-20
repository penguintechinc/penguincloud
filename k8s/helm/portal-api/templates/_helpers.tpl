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
JWT FileKeyStore PVC name
*/}}
{{- define "portal-api.jwtKeystorePVCName" -}}
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
Per-tier default cap on THIS service type's backend node (replica) count --
docs/APP_STANDARDS.md "Backend nodes per service type": 1 each on
Free/Professional, multiple/HA on Enterprise. A licence-server-configured
override (.Values.license.maxReplicasOverride, > 0) always wins over the
tier default, matching the commercial model where every numeric wall is a
licence-configurable default, not a hardcoded constant.
*/}}
{{- define "portal-api.maxReplicas" -}}
{{- $tier := include "portal-api.licenseTier" . }}
{{- if gt (int .Values.license.maxReplicasOverride) 0 }}
{{- .Values.license.maxReplicasOverride }}
{{- else if eq $tier "enterprise" }}
{{- 999999 }}
{{- else }}
{{- 1 }}
{{- end }}
{{- end }}
