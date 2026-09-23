# Crucible Skills

**Ingeniería de verificación para metodologías de agentes de IA.**

[English](README.md) · **Español** · [Technical README](TECHNICAL.md)

> **Estado: en progreso — primero el contrato arquitectónico y de evaluación.**

Las skills de agentes son metodología ejecutable: cambian qué detecta, prioriza, verifica y hace un agente de coding. Ya existen herramientas para validar su forma, buscar comportamiento malicioso y medir si un agente rinde mejor con ellas. Falta una pregunta más difícil:

> **¿La metodología es coherente, verificable, componible y realmente vale la pena agregarla al corpus?**

Crucible Skills busca responderla con evidencia estructurada, no con un puntaje opaco.

## La idea en un ejemplo

Dos skills pueden parecer razonables por separado y producir una composición incorrecta:

```text
Skill A: reintentar operaciones críticas hasta que tengan éxito.
Skill B: las operaciones irreversibles deben tener efectos acotados y revisables.

Plausibles por separado → composición insegura cuando el retry duplica un efecto irreversible.
```

Crucible extrae reglas declaradas, scopes, triggers, checks, referencias y aristas de composición; después audita contradicciones, verificaciones ausentes, redundancia, provenance rota y resistencia a mutaciones.

## Estado del documento

Esta versión es una adaptación de trabajo en español. La especificación pública y el roadmap canónico están en inglés; el plan operativo en español se mantiene local e ignorado por Git para poder iterarlo durante el hackathon.

Ver el detalle completo en el [Technical README](TECHNICAL.md) y el mapa de construcción en [ROADMAP.md](docs/ROADMAP.md).

## Principio de construcción

El destino es un sistema completo de verificación de metodología. El tiempo decide hasta qué nivel coherente llegamos; no convierte los niveles no alcanzados en prototipos descartables. Cada nivel debe ser útil, compatible con el siguiente y conservar los invariantes anteriores.

## Licencia

Apache-2.0. Ver [`LICENSE`](LICENSE).
