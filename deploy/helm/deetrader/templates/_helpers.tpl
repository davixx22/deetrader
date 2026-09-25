{{- define "deetrader.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "deetrader.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else if contains (include "deetrader.name" .) .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "deetrader.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "deetrader.labels" -}}
app.kubernetes.io/name: {{ include "deetrader.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "deetrader.selectorLabels" -}}
app.kubernetes.io/name: {{ include "deetrader.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "deetrader.secretName" -}}
{{- default (printf "%s-secrets" (include "deetrader.fullname" .)) .Values.secrets.existingSecret -}}
{{- end -}}

{{- define "deetrader.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "deetrader.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}
