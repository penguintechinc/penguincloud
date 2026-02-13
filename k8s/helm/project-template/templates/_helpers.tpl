{{/*
Expand the name of the chart.
*/}}
{{- define "project-template.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "project-template.fullname" -}}
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
{{- define "project-template.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "project-template.labels" -}}
helm.sh/chart: {{ include "project-template.chart" . }}
{{ include "project-template.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "project-template.selectorLabels" -}}
app.kubernetes.io/name: {{ include "project-template.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "project-template.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "project-template.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Flask Backend fullname
*/}}
{{- define "project-template.flaskBackend.fullname" -}}
{{- printf "%s-flask-backend" (include "project-template.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Flask Backend labels
*/}}
{{- define "project-template.flaskBackend.labels" -}}
{{ include "project-template.labels" . }}
app.kubernetes.io/component: flask-backend
{{- end }}

{{/*
Flask Backend selector labels
*/}}
{{- define "project-template.flaskBackend.selectorLabels" -}}
{{ include "project-template.selectorLabels" . }}
app.kubernetes.io/component: flask-backend
{{- end }}

{{/*
Go Backend fullname
*/}}
{{- define "project-template.goBackend.fullname" -}}
{{- printf "%s-go-backend" (include "project-template.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Go Backend labels
*/}}
{{- define "project-template.goBackend.labels" -}}
{{ include "project-template.labels" . }}
app.kubernetes.io/component: go-backend
{{- end }}

{{/*
Go Backend selector labels
*/}}
{{- define "project-template.goBackend.selectorLabels" -}}
{{ include "project-template.selectorLabels" . }}
app.kubernetes.io/component: go-backend
{{- end }}

{{/*
WebUI fullname
*/}}
{{- define "project-template.webui.fullname" -}}
{{- printf "%s-webui" (include "project-template.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
WebUI labels
*/}}
{{- define "project-template.webui.labels" -}}
{{ include "project-template.labels" . }}
app.kubernetes.io/component: webui
{{- end }}

{{/*
WebUI selector labels
*/}}
{{- define "project-template.webui.selectorLabels" -}}
{{ include "project-template.selectorLabels" . }}
app.kubernetes.io/component: webui
{{- end }}

{{/*
ConfigMap name
*/}}
{{- define "project-template.configMapName" -}}
{{- printf "%s-config" (include "project-template.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Secret name
*/}}
{{- define "project-template.secretName" -}}
{{- printf "%s-secret" (include "project-template.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
PostgreSQL host
*/}}
{{- define "project-template.postgresql.host" -}}
{{- if .Values.postgresql.enabled }}
{{- printf "%s-postgresql" (include "project-template.fullname" .) }}
{{- else }}
{{- .Values.config.DB_HOST }}
{{- end }}
{{- end }}

{{/*
Redis host
*/}}
{{- define "project-template.redis.host" -}}
{{- if .Values.redis.enabled }}
{{- printf "%s-redis-master" (include "project-template.fullname" .) }}
{{- else }}
{{- .Values.config.REDIS_HOST }}
{{- end }}
{{- end }}
