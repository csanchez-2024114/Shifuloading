"""Módulo de CRM de Shifu.

Un CRM por persona (colección `crm_workspaces`). La lógica vive en funciones puras sobre un diccionario
(`operaciones`), sin base de datos, para poder probarla sin servidor; `repositorio` es lo único que habla con Mongo y
`vista` convierte el documento interno en la forma que espera el frontend (ver `API.md` en la raíz del repositorio).
"""
